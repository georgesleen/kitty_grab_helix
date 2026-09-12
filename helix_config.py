# Configuration for the helix-style grab kitten: colours and key bindings read
# from grab.conf in kitty's configuration directory.
#
# Pure python, hand written rather than generated from a kitty option
# definition, so the parser is a plain function over lines and the whole thing
# is covered by the test suite. Unknown options and unknown commands are
# reported rather than ignored; the kitten shows them in its title bar.

import re
from typing import Container, Iterable, NamedTuple, Optional

from helix_keymap import normalise_chord

COLOR_PATTERN = re.compile(r'#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})\Z')

# Sequences are written kitty style in the config file (`map g>g ...`) and kept
# space separated internally, matching how helix writes them.
CONFIG_CHORD_SEPARATOR = '>'
CHORD_SEPARATOR = ' '

DEFAULT_SELECTION_FOREGROUND = '#ffffff'
DEFAULT_SELECTION_BACKGROUND = '#5294e2'
DEFAULT_CURSOR = '#ad7fa8'

COLOR_OPTIONS = ('selection_foreground', 'selection_background', 'cursor')


class Config(NamedTuple):
    selection_foreground: str
    selection_background: str
    cursor: str
    # Empty means "take kitty's own select_by_word_characters".
    select_by_word_characters: str
    bindings: dict[str, str]
    errors: list[str]


def default_config(bindings: dict[str, str]) -> Config:
    return Config(selection_foreground=DEFAULT_SELECTION_FOREGROUND,
                  selection_background=DEFAULT_SELECTION_BACKGROUND,
                  cursor=DEFAULT_CURSOR,
                  select_by_word_characters='',
                  bindings=dict(bindings),
                  errors=[])


def normalise_sequence(sequence: str) -> str:
    """Return a config file key sequence in the keymap's own spelling."""
    return CHORD_SEPARATOR.join(
        normalise_chord(chord)
        for chord in sequence.split(CONFIG_CHORD_SEPARATOR) if chord)


def parse_config(lines: Iterable[str], default_bindings: dict[str, str],
                 commands: Container[str]) -> Config:
    """
    Parse grab.conf.

    :param default_bindings: the built-in keymap, which the file amends
    :param commands: command names a `map` line is allowed to name
    """
    values = default_config(default_bindings)._asdict()
    bindings: dict[str, str] = values.pop('bindings')
    errors: list[str] = values.pop('errors')

    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        # Whole-line comments only, like kitty's own parser: a value may
        # legitimately contain #, as select_by_word_characters does.
        if not line or line.startswith('#'):
            continue
        option, _, rest = line.partition(' ')
        rest = rest.strip()
        if option == 'clear_all_shortcuts':
            bindings.clear()
        elif option == 'map':
            sequence, _, command = rest.partition(' ')
            error = _bind(bindings, sequence, command.strip(), commands)
            if error:
                errors.append('line {}: {}'.format(number, error))
        elif option == 'unmap':
            sequence = normalise_sequence(rest)
            if bindings.pop(sequence, None) is None:
                errors.append('line {}: {} is not bound'.format(number, rest))
        elif option in COLOR_OPTIONS:
            if COLOR_PATTERN.match(rest):
                values[option] = rest
            else:
                errors.append('line {}: {} is not a colour'.format(number, rest))
        elif option == 'select_by_word_characters':
            values['select_by_word_characters'] = rest
        else:
            errors.append('line {}: unknown option {}'.format(number, option))

    return Config(bindings=bindings, errors=errors, **values)


def _bind(bindings: dict[str, str], sequence: str, command: str,
          commands: Container[str]) -> Optional[str]:
    sequence = normalise_sequence(sequence)
    if not sequence or not command:
        return 'map needs a key sequence and a command'
    if command not in commands:
        return 'unknown command {}'.format(command)
    bindings[sequence] = command
    return None
