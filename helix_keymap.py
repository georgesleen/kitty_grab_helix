# Key dispatch for the helix-style grab kitten: helix bindings, multi-key
# sequences and counts.
#
# Pure python, driven by normalised key names rather than kitty key events, so
# the whole table and the pending-sequence state machine run under the test
# suite. Kitty's own kitten shortcut table matches one chord at a time and has
# no notion of a pending prefix, which is why goto mode lives here.
#
# Names follow helix: `C-`, `A-` and `S-` prefixes, a shifted letter written as
# the capital, functional keys lowercased (`escape`, `page_up`), and a sequence
# written as space-separated chords (`g g`).

from typing import Any, NamedTuple, Optional

# Helix commands, named as helix names them. Everything here is read-only:
# there is nothing to edit in a terminal scrollback, so the map covers motion,
# selection and yanking only.
DEFAULT_BINDINGS = {
    'h': 'move_char_left',
    'left': 'move_char_left',
    'j': 'move_line_down',
    'down': 'move_line_down',
    'k': 'move_line_up',
    'up': 'move_line_up',
    'l': 'move_char_right',
    'right': 'move_char_right',
    'w': 'move_next_word_start',
    'b': 'move_prev_word_start',
    'e': 'move_next_word_end',
    'W': 'move_next_long_word_start',
    'B': 'move_prev_long_word_start',
    'E': 'move_next_long_word_end',
    'C-b': 'move_page_up',
    'page_up': 'move_page_up',
    'C-f': 'move_page_down',
    'page_down': 'move_page_down',
    'C-u': 'move_half_page_up',
    'C-d': 'move_half_page_down',
    'g g': 'goto_file_start',
    'g e': 'goto_last_line',
    'g h': 'goto_line_start',
    'home': 'goto_line_start',
    'g l': 'goto_line_end',
    'end': 'goto_line_end',
    'g s': 'goto_first_nonwhitespace',
    'G': 'goto_line',
    'v': 'select_mode',
    'C-v': 'columnar_mode',
    ';': 'collapse_selection',
    'A-;': 'flip_selections',
    'x': 'extend_line_below',
    'X': 'extend_to_line_bounds',
    '%': 'select_all',
    'C-e': 'scroll_down',
    'C-y': 'scroll_up',
    'y': 'yank',
    'enter': 'yank',
    'escape': 'normal_mode',
    'q': 'quit',
}

# A config file may only map a command this kitten implements, which is
# exactly the set the default map names.
COMMANDS = frozenset(DEFAULT_BINDINGS.values())

# Modifier prefixes, in the order they are written. Shift is folded into the
# shifted character where there is one, so `X` rather than `S-x`.
MODIFIER_PREFIXES = (
    ('ctrl', 'C-'),
    ('alt', 'A-'),
    ('super', 'D-'),
    ('hyper', 'H-'),
    ('meta', 'M-'),
)


def key_name(event: Any) -> str:
    """
    Return the helix spelling of a kitty key event.

    Duck typed on purpose: anything with kitty's KeyEvent fields works, so the
    naming is testable without a terminal.
    """
    # Space is spelled out, as helix spells it, so a space can separate the
    # chords of a sequence without ambiguity.
    name = 'space' if event.key == ' ' else event.key
    modifiers = ''.join(prefix for attribute, prefix in MODIFIER_PREFIXES
                        if getattr(event, attribute, False))
    if getattr(event, 'shift', False):
        shifted = getattr(event, 'shifted_key', '')
        if len(shifted) == 1:
            name = shifted
        else:
            modifiers += 'S-'
    if len(name) > 1:
        name = name.lower()
    return modifiers + name


# Modifier names a config file may use, kitty's spelling and helix's short
# form both. The value is the internal prefix.
MODIFIER_ALIASES = {
    'ctrl': 'C-', 'control': 'C-', 'c': 'C-',
    'alt': 'A-', 'opt': 'A-', 'option': 'A-', 'a': 'A-',
    'shift': 'S-', 's': 'S-',
    'super': 'D-', 'cmd': 'D-', 'command': 'D-', 'd': 'D-',
    'hyper': 'H-', 'h': 'H-',
    'meta': 'M-', 'm': 'M-',
}

# Key names kitty accepts as synonyms of the name it reports.
KEY_ALIASES = {
    'esc': 'escape',
    'return': 'enter',
    'spc': 'space',
    'pgup': 'page_up',
    'pgdn': 'page_down',
    'del': 'delete',
    'ins': 'insert',
}

CANONICAL_MODIFIER_ORDER = ('C-', 'A-', 'D-', 'H-', 'M-', 'S-')


def normalise_chord(chord: str) -> str:
    """
    Return one config-file chord in the spelling key_name produces.

    Both kitty's `ctrl+shift+x` and helix's `C-X` are accepted, so a
    grab.conf reads like the kitty.conf beside it.
    """
    modifiers, key = _split_chord(chord)
    key = KEY_ALIASES.get(key.lower(), key)
    if len(key) > 1:
        key = key.lower()
    if 'S-' in modifiers and len(key) == 1 and key.isalpha():
        modifiers.discard('S-')
        key = key.upper()
    return ''.join(prefix for prefix in CANONICAL_MODIFIER_ORDER
                   if prefix in modifiers) + key


def _split_chord(chord: str) -> tuple[set[str], str]:
    if chord in ('+', '-'):
        return set(), chord
    if chord.endswith('+'):
        parts = chord[:-1].split('+') + ['+']
    else:
        parts = chord.split('+')
    if len(parts) > 1:
        return ({MODIFIER_ALIASES.get(part.strip().lower(), '')
                 for part in parts[:-1]} - {''}, parts[-1])
    modifiers = set()
    while len(chord) > 2 and chord[1] == '-' and chord[0] in 'CASDHM':
        modifiers.add(chord[0] + '-')
        chord = chord[2:]
    return modifiers, chord


COMMAND = 'command'
PENDING = 'pending'
CANCELLED = 'cancelled'
UNBOUND = 'unbound'


class Dispatch(NamedTuple):
    """Result of feeding one key to the keymap."""

    kind: str
    command: Optional[str] = None
    count: int = 1
    pending: str = ''


class Keymap:
    """
    Key sequence resolver with helix counts.

    Feed it one normalised key name at a time. A key that begins a bound
    sequence is held as a prefix; digits accumulate into a count that is
    handed to the command they precede.
    """

    def __init__(self, bindings: Optional[dict[str, str]] = None) -> None:
        self.bindings = dict(DEFAULT_BINDINGS if bindings is None else bindings)
        self.prefixes = {
            ' '.join(chords[:length])
            for sequence in self.bindings
            for chords in [sequence.split(' ')]
            for length in range(1, len(chords))
        }
        self.pending: list[str] = []
        self.count = 0

    @property
    def pending_text(self) -> str:
        """The keys held so far, as the status line shows them."""
        return ''.join(
            (str(self.count) if self.count else '', *self.pending))

    def reset(self) -> None:
        self.pending = []
        self.count = 0

    def feed(self, key: str) -> Dispatch:
        if key == 'escape' and (self.pending or self.count):
            self.reset()
            return Dispatch(CANCELLED)
        if not self.pending and key.isdigit() and (key != '0' or self.count):
            self.count = self.count * 10 + int(key)
            return Dispatch(PENDING, count=self.count)
        sequence = ' '.join(self.pending + [key])
        command = self.bindings.get(sequence)
        if command is not None:
            count = max(1, self.count)
            self.reset()
            return Dispatch(COMMAND, command, count)
        if sequence in self.prefixes:
            self.pending.append(key)
            return Dispatch(PENDING, count=max(1, self.count), pending=sequence)
        self.reset()
        return Dispatch(UNBOUND)
