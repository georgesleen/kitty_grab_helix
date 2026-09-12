# Kitty-facing half of the helix-style grab kitten: screen drawing, key events
# and the clipboard.
#
# Forked from yurikhan/kitty_grab (GPL-3.0-or-later). The drawing is upstream's;
# the selection model, the keymap and the config parser live in the sibling
# helix_* modules, which import no kitty code and are unit tested.

import os
import sys
from base64 import b64encode
from typing import TYPE_CHECKING, Any, Iterable, List, Optional, Type

import kitty.key_encoding as kk
from kittens.tui.handler import Handler
from kittens.tui.loop import Loop
from kitty.cli import parse_args
from kitty.constants import config_dir
from kitty.fast_data_types import truncate_point_for_length, wcswidth
from kitty.rgb import color_as_sgr, to_color

from helix_config import Config, default_config, parse_config
from helix_keymap import COMMANDS, DEFAULT_BINDINGS, Keymap, key_name
from helix_motions import (
    MOTION_KINDS,
    ColumnarRegion,
    Motions,
    Position,
    Region,
    Selection,
    StreamRegion,
    TextMetrics,
    apply_motion,
    collapse_selection,
    flip_selections,
    selected_text,
    string_slice,
    unstyled,
)

if TYPE_CHECKING:
    from typing_extensions import TypedDict
    ResultDict = TypedDict('ResultDict', {'copy': str})

Namespace = Any  # kitty.cli.Namespace

CONFIG_NAME = 'grab.conf'

# Kitty measures display width and truncates to a column itself; the pure core
# takes both as functions so it can be tested with plain ASCII arithmetic.
KITTY_METRICS = TextMetrics(width=wcswidth, truncate=truncate_point_for_length)


def load_config(path: str) -> Config:
    try:
        with open(path, encoding='utf-8') as config_file:
            lines = config_file.read().splitlines()
    except FileNotFoundError:
        return default_config(DEFAULT_BINDINGS)
    return parse_config(lines, DEFAULT_BINDINGS, COMMANDS)


class GrabHandler(Handler):
    def __init__(self, args: Namespace, config: Config,
                 lines: List[str]) -> None:
        super().__init__()
        self.args = args
        self.config = config
        self.lines = lines
        self.plain = [unstyled(line) for line in lines]
        self.keymap = Keymap(config.bindings)
        head = Position(args.x, args.y, args.top_line)
        self.selection = Selection(head, head)
        self.select_mode = False
        self.region: Type[Region] = StreamRegion
        self.status = ' '.join(config.errors)
        self.result: Optional['ResultDict'] = None
        self.motions = Motions([''], KITTY_METRICS, 1, 1)
        # OSC 52 target: c clipboard, p primary, s secondary.
        self.copy_to = {'primary': b'p', 'secondary': b's'}.get(args.copy_to, b'c')
        self.selection_sgr = '\x1b[38{};48{}m'.format(
            color_as_sgr(to_color(config.selection_foreground)),
            color_as_sgr(to_color(config.selection_background)))
        unimplemented = sorted(
            command for command in set(config.bindings.values())
            if command not in MOTION_KINDS and not hasattr(self, '_' + command))
        if unimplemented:
            raise ValueError('unimplemented commands: {}'.format(
                ', '.join(unimplemented)))

    # --- lifecycle -------------------------------------------------------

    def initialize(self) -> None:
        self._build_motions()
        self.cmd.set_default_colors(cursor=to_color(self.config.cursor))
        self._redraw()

    def on_resize(self, screen_size: Any) -> None:
        self._build_motions()
        self._redraw()

    def _build_motions(self) -> None:
        self.motions = Motions(
            self.plain, KITTY_METRICS,
            self.screen_size.rows, self.screen_size.cols,
            self.config.select_by_word_characters or self._kitty_word_characters())

    def _kitty_word_characters(self) -> str:
        import json
        return (json.loads(os.getenv('KITTY_COMMON_OPTS', '{}'))
                .get('select_by_word_characters', ''))

    # --- drawing ---------------------------------------------------------

    @property
    def head(self) -> Position:
        return self.selection.head

    def _draw_line(self, current_line: int) -> None:
        y = current_line - self.head.top_line
        if not 0 <= y < self.screen_size.rows:
            return
        line = self.lines[current_line - 1]
        plain = self.plain[current_line - 1]
        clear_eol = '\x1b[m\x1b[K'
        start, end = self.motions.span(self.selection, self.region)

        # anti-flicker optimization
        if self.region.line_inside_region(current_line, start, end):
            self.cmd.set_cursor_position(0, y)
            self.print('{}{}'.format(self.selection_sgr, plain), end=clear_eol)
            return

        self.cmd.set_cursor_position(0, y)
        self.print('\x1b[m{}'.format(line), end=clear_eol)

        if self.region.line_outside_region(current_line, start, end):
            return

        start_x, end_x = self.region.selection_in_line(
            current_line, start, end, wcswidth(plain))
        if start_x is None or end_x is None:
            return

        line_slice, half = string_slice(plain, start_x, end_x, KITTY_METRICS)
        self.cmd.set_cursor_position(start_x - (1 if half else 0), y)
        self.print('{}{}'.format(self.selection_sgr, line_slice), end='')

    def _update_title(self) -> None:
        mode = 'SEL' if self.select_mode else 'NOR'
        if self.region is ColumnarRegion:
            mode += ' COL'
        self.cmd.set_window_title('Grab [{}]{}{} - {}'.format(
            mode,
            ' ' + self.keymap.pending_text if self.keymap.pending_text else '',
            ' ' + self.status if self.status else '',
            self.args.title))
        self.cmd.set_cursor_position(self.head.x, self.head.y)

    def _redraw_lines(self, lines: Iterable[int]) -> None:
        for line in lines:
            self._draw_line(line)
        self._update_title()

    def _redraw(self) -> None:
        self._redraw_lines(range(
            self.head.top_line,
            min(self.head.top_line + self.screen_size.rows, len(self.lines) + 1)))

    def _apply(self, selection: Selection) -> None:
        """Install a new selection and repaint what it touched."""
        previous, self.selection = self.selection, selection
        if previous.head.top_line != self.head.top_line:
            self._redraw()
            return
        start = min(previous.lines.start, selection.lines.start)
        stop = max(previous.lines.stop, selection.lines.stop)
        self._redraw_lines(range(start, stop))

    # --- keys ------------------------------------------------------------

    def perform_default_key_action(self, key_event: kk.KeyEvent) -> bool:
        return False

    def on_key_event(self, key_event: kk.KeyEvent,
                     in_bracketed_paste: bool = False) -> None:
        if key_event.type not in (kk.PRESS, kk.REPEAT):
            return
        dispatch = self.keymap.feed(key_name(key_event))
        if dispatch.command is not None:
            self.status = ''
            self.perform(dispatch.command, dispatch.count)
        self._update_title()

    def perform(self, command: str, count: int) -> None:
        kind = MOTION_KINDS.get(command)
        if kind is not None:
            head = self.head
            for _ in range(count):
                head = getattr(self.motions, command)(head)
            self._apply(apply_motion(self.selection, head, kind,
                                     self.select_mode))
            return
        getattr(self, '_' + command)(count)

    # --- commands --------------------------------------------------------

    def _goto_line(self, count: int) -> None:
        head = (self.motions.goto_line(self.head, count) if count > 1
                else self.motions.goto_last_line(self.head))
        self._apply(apply_motion(self.selection, head, 'collapsing',
                                 self.select_mode))

    def _select_mode(self, count: int) -> None:
        self.select_mode = not self.select_mode

    def _normal_mode(self, count: int) -> None:
        if self.select_mode:
            self.select_mode = False
            return
        self.quit_loop(1)

    def _columnar_mode(self, count: int) -> None:
        self.region = (StreamRegion if self.region is ColumnarRegion
                       else ColumnarRegion)
        # A rectangle that collapses on every motion is no use, so entering
        # columnar selection also starts extending.
        self.select_mode = self.select_mode or self.region is ColumnarRegion
        self._redraw()

    def _collapse_selection(self, count: int) -> None:
        self._apply(collapse_selection(self.selection))

    def _flip_selections(self, count: int) -> None:
        self._apply(flip_selections(self.selection))

    def _extend_line_below(self, count: int) -> None:
        self._apply(self.motions.extend_line_below(self.selection, count))

    def _extend_to_line_bounds(self, count: int) -> None:
        self._apply(self.motions.extend_to_line_bounds(self.selection))

    def _select_all(self, count: int) -> None:
        self._apply(self.motions.select_all(self.head))

    def _scroll_up(self, count: int) -> None:
        self._scroll(-count)

    def _scroll_down(self, count: int) -> None:
        self._scroll(count)

    def _scroll(self, delta: int) -> None:
        head = self.motions.scroll(self.head, delta)
        self.selection = self.selection._replace(head=head)
        if not self.select_mode:
            self.selection = collapse_selection(self.selection)
        self._redraw()

    def _quit(self, count: int) -> None:
        self.quit_loop(1)

    def _yank(self, count: int) -> None:
        self.result = {'copy': selected_text(self.plain, self.selection,
                                             self.region, KITTY_METRICS)}
        self.quit_loop(0)


def option_spec() -> str:
    return '''
--copy-to
dest=copy_to
type=str
default=clipboard
Copy to: 'clipboard' or 'primary'/selection or 'secondary' buffer


--config
dest=config
type=str
default=
Path to the configuration file. Defaults to grab.conf in kitty's config dir.


--cursor-x
dest=x
type=int
(Internal) Starting cursor column, 0-based.


--cursor-y
dest=y
type=int
(Internal) Starting cursor line, 0-based.


--top-line
dest=top_line
type=int
(Internal) Window scroll offset, 1-based.


--title
(Internal)'''


def main(args: List[str]) -> Optional['ResultDict']:
    try:
        args, _rest = parse_args(args[1:], option_spec)
        tty = open(os.ctermid())
        # The last line ends with a newline too, hence the trailing drop.
        lines = sys.stdin.buffer.read().decode('utf-8').split('\n')[:-1]
        sys.stdin = tty
        config = load_config(args.config or os.path.join(config_dir, CONFIG_NAME))
        handler = GrabHandler(args, config, lines)
        loop = Loop()
        loop.loop(handler)
        if loop.return_code == 0 and handler.result is not None:
            sys.stdout.buffer.write(b''.join((
                b'\x1b]52;', handler.copy_to, b';',
                b64encode(handler.result['copy'].encode('utf-8')), b'\x1b\\')))
        return {}
    except Exception:
        from traceback import format_exc

        from kittens.tui.loop import debug
        debug(format_exc())
        raise
