# Selection model and motions for the helix-style grab kitten.
#
# Pure python: no kitty imports and text metrics injected, so the deciding half
# runs under the test suite without a terminal. Forked from yurikhan/kitty_grab
# (GPL-3.0-or-later); Position and the region geometry are upstream's, the
# helix selection model is not.
#
# A selection is an anchor and a head, both always set, and the head cell is
# part of it. Rendering therefore wants half-open bounds, which is what
# Selection.span returns.

import re
import unicodedata
from itertools import takewhile
from typing import Callable, NamedTuple, Optional

AbsoluteLine = int
ScreenLine = int
ScreenColumn = int
CharIndex = int
LineCursor = tuple[AbsoluteLine, CharIndex]
SelectionInLine = tuple[Optional[ScreenColumn], Optional[ScreenColumn]]

# Kitty's own default for what counts as part of a word beyond letters/digits.
DEFAULT_WORD_CHARACTERS = '@-./_~?&=%+#'

SGR_PATTERN = re.compile(r'\x1b\[[0-9;:]*m')
OSC_PATTERN = re.compile(r'\x1b\](?:[^\x07\x1b]+|\x1b[^\\])*(?:\x1b\\|\x07)')


def unstyled(line: str) -> str:
    """Return line with SGR and OSC escape sequences removed."""
    return OSC_PATTERN.sub('', SGR_PATTERN.sub('', line))


class Position(NamedTuple):
    """
    Coordinates of a cell.

    :param x: 0-based, left of window, to the right
    :param y: 0-based, top of window, down
    :param top_line: 1-based, start of scrollback, down
    """

    x: ScreenColumn
    y: ScreenLine
    top_line: AbsoluteLine

    @property
    def line(self) -> AbsoluteLine:
        return self.y + self.top_line

    @property
    def sort_key(self) -> tuple[AbsoluteLine, ScreenColumn]:
        return (self.line, self.x)

    def moved(self, dx: int = 0, dy: int = 0, dtop: int = 0) -> 'Position':
        return self._replace(x=self.x + dx, y=self.y + dy,
                             top_line=self.top_line + dtop)


def ordered(first: Position, second: Position) -> tuple[Position, Position]:
    """Return the pair sorted by buffer order."""
    return ((first, second) if first.sort_key <= second.sort_key
            else (second, first))


class Region:
    """Shape of a selection: how anchor and head bound the highlighted cells."""

    name = ''

    @staticmethod
    def adjust(start: Position, end: Position,
               width: ScreenColumn) -> tuple[Position, Position]:
        """Return half-open bounds covering both end cells, where the cell
        under the later end is `width` columns wide."""
        raise NotImplementedError

    @staticmethod
    def line_inside_region(current_line: AbsoluteLine,
                           start: Position, end: Position) -> bool:
        raise NotImplementedError

    @staticmethod
    def line_outside_region(current_line: AbsoluteLine,
                            start: Position, end: Position) -> bool:
        return current_line < start.line or end.line < current_line

    @staticmethod
    def selection_in_line(current_line: AbsoluteLine, start: Position,
                          end: Position, maxx: ScreenColumn) -> SelectionInLine:
        raise NotImplementedError


class StreamRegion(Region):
    """Everything between the two ends, wrapping at line boundaries."""

    name = 'stream'

    @staticmethod
    def adjust(start: Position, end: Position,
               width: ScreenColumn) -> tuple[Position, Position]:
        return start, end.moved(dx=width)

    @staticmethod
    def line_inside_region(current_line: AbsoluteLine,
                           start: Position, end: Position) -> bool:
        return start.line < current_line < end.line

    @staticmethod
    def selection_in_line(current_line: AbsoluteLine, start: Position,
                          end: Position, maxx: ScreenColumn) -> SelectionInLine:
        if StreamRegion.line_outside_region(current_line, start, end):
            return None, None
        return (start.x if current_line == start.line else 0,
                end.x if current_line == end.line else maxx)


class ColumnarRegion(Region):
    """The rectangle spanned by the two ends."""

    name = 'columnar'

    @staticmethod
    def adjust(start: Position, end: Position,
               width: ScreenColumn) -> tuple[Position, Position]:
        return (start._replace(x=min(start.x, end.x)),
                end._replace(x=max(start.x, end.x) + width))

    @staticmethod
    def line_inside_region(current_line: AbsoluteLine,
                           start: Position, end: Position) -> bool:
        return False

    @staticmethod
    def selection_in_line(current_line: AbsoluteLine, start: Position,
                          end: Position, maxx: ScreenColumn) -> SelectionInLine:
        if ColumnarRegion.line_outside_region(current_line, start, end):
            return None, None
        return start.x, end.x


class Selection(NamedTuple):
    anchor: Position
    head: Position

    @property
    def lines(self) -> range:
        start, end = ordered(self.anchor, self.head)
        return range(start.line, end.line + 1)


class TextMetrics(NamedTuple):
    """Display-width functions, injected so the core stays kitty-free."""

    width: Callable[[str], int]
    truncate: Callable[[str, ScreenColumn], CharIndex]


# How a motion updates the anchor when not in select mode. A collapsing motion
# leaves a one-cell selection; a spanning motion keeps the cells travelled over.
COLLAPSING = 'collapsing'
SPANNING = 'spanning'

MOTION_KINDS = {
    'move_char_left': COLLAPSING,
    'move_char_right': COLLAPSING,
    'move_line_up': COLLAPSING,
    'move_line_down': COLLAPSING,
    'move_page_up': COLLAPSING,
    'move_page_down': COLLAPSING,
    'move_half_page_up': COLLAPSING,
    'move_half_page_down': COLLAPSING,
    'goto_line_start': COLLAPSING,
    'goto_line_end': COLLAPSING,
    'goto_first_nonwhitespace': COLLAPSING,
    'goto_file_start': COLLAPSING,
    'goto_last_line': COLLAPSING,
    'move_next_word_start': SPANNING,
    'move_prev_word_start': SPANNING,
    'move_next_word_end': SPANNING,
    'move_next_long_word_start': SPANNING,
    'move_prev_long_word_start': SPANNING,
    'move_next_long_word_end': SPANNING,
}

# Character classes a word motion travels through. A line ending is its own
# class, as in helix: a motion that reaches one stops there, and only a motion
# that starts on one crosses into the next line.
WORD = 'word'
PUNCTUATION = 'punctuation'
SPACE = 'space'
EOL = 'eol'


class Motions:
    """
    Motions over a fixed buffer of plain-text lines.

    Lines are 1-based absolute buffer lines; indices are 0-based character
    offsets into a line. Every motion takes and returns a Position, so the
    caller never deals with scrolling.
    """

    def __init__(self, lines: list[str], metrics: TextMetrics,
                 rows: ScreenLine, cols: ScreenColumn,
                 word_characters: str = DEFAULT_WORD_CHARACTERS) -> None:
        self.lines = lines
        self.metrics = metrics
        self.rows = rows
        self.cols = cols
        self.word_characters = word_characters

    # --- coordinates -----------------------------------------------------

    def text(self, line: AbsoluteLine) -> str:
        return self.lines[line - 1]

    def cursor(self, point: Position) -> LineCursor:
        return (point.line, self.metrics.truncate(self.text(point.line), point.x))

    def locate(self, cursor: LineCursor, top_line: AbsoluteLine) -> Position:
        """Return the on-screen position of a cursor, scrolling the least."""
        line = min(max(cursor[0], 1), len(self.lines))
        text = self.text(line)
        index = min(max(cursor[1], 0), max(0, len(text) - 1))
        x = min(self.metrics.width(text[:index]), self.cols - 1)
        top = top_line
        if line < top:
            top = line
        elif line > top + self.rows - 1:
            top = line - self.rows + 1
        top = min(max(top, 1), max(1, len(self.lines) - self.rows + 1))
        return Position(x, line - top, top)

    def _moved_to(self, point: Position, cursor: Optional[LineCursor]) -> Position:
        return point if cursor is None else self.locate(cursor, point.top_line)

    def _vertical(self, point: Position, dlines: int) -> Position:
        line = min(max(point.line + dlines, 1), len(self.lines))
        return self.locate((line, self.metrics.truncate(self.text(line), point.x)),
                           point.top_line)

    # --- character and line motions --------------------------------------

    def move_char_left(self, point: Position) -> Position:
        line, index = self.cursor(point)
        return self.locate((line, index - 1), point.top_line)

    def move_char_right(self, point: Position) -> Position:
        line, index = self.cursor(point)
        return self.locate((line, index + 1), point.top_line)

    def move_line_up(self, point: Position) -> Position:
        return self._vertical(point, -1)

    def move_line_down(self, point: Position) -> Position:
        return self._vertical(point, 1)

    def move_page_up(self, point: Position) -> Position:
        return self._vertical(point, -self.rows)

    def move_page_down(self, point: Position) -> Position:
        return self._vertical(point, self.rows)

    def move_half_page_up(self, point: Position) -> Position:
        return self._vertical(point, -(self.rows // 2))

    def move_half_page_down(self, point: Position) -> Position:
        return self._vertical(point, self.rows // 2)

    def goto_line_start(self, point: Position) -> Position:
        return self.locate((point.line, 0), point.top_line)

    def goto_line_end(self, point: Position) -> Position:
        return self.locate((point.line, len(self.text(point.line))), point.top_line)

    def goto_first_nonwhitespace(self, point: Position) -> Position:
        text = self.text(point.line)
        index = len(list(takewhile(str.isspace, text)))
        return self.locate((point.line, index), point.top_line)

    def goto_file_start(self, point: Position) -> Position:
        return self.locate((1, 0), 1)

    def goto_last_line(self, point: Position) -> Position:
        return self.locate((len(self.lines), 0), point.top_line)

    def goto_line(self, point: Position, line: AbsoluteLine) -> Position:
        return self.locate((line, 0), point.top_line)

    def scroll(self, point: Position, dtop: int) -> Position:
        """Scroll the view, carrying the head along with it."""
        top = min(max(point.top_line + dtop, 1),
                  max(1, len(self.lines) - self.rows + 1))
        line = min(point.y + top, len(self.lines))
        return self.locate((line, self.metrics.truncate(self.text(line), point.x)),
                           top)

    # --- word motions ----------------------------------------------------

    def _character(self, cursor: LineCursor) -> str:
        text = self.text(cursor[0])
        return text[cursor[1]] if cursor[1] < len(text) else '\n'

    def _class_of(self, cursor: LineCursor, long_words: bool) -> str:
        character = self._character(cursor)
        if character == '\n':
            return EOL
        if character.isspace():
            return SPACE
        if long_words:
            return WORD
        if (unicodedata.category(character)[0] in 'LN'
                or character in self.word_characters):
            return WORD
        return PUNCTUATION

    def _advance(self, cursor: LineCursor) -> Optional[LineCursor]:
        line, index = cursor
        if index < len(self.text(line)):
            return (line, index + 1)
        if line < len(self.lines):
            return (line + 1, 0)
        return None

    def _retreat(self, cursor: LineCursor) -> Optional[LineCursor]:
        line, index = cursor
        if index > 0:
            return (line, index - 1)
        if line > 1:
            return (line - 1, len(self.text(line - 1)))
        return None

    def _skip(self, cursor: LineCursor, classes: tuple[str, ...],
              long_words: bool, backwards: bool = False) -> LineCursor:
        step = self._retreat if backwards else self._advance
        while self._class_of(cursor, long_words) in classes:
            following = step(cursor)
            if following is None:
                break
            cursor = following
        return cursor

    def _next_word_start(self, point: Position, long_words: bool) -> Position:
        # Helix keeps the head one past the last selected cell, so the search
        # for the next word starts one cell further along than it looks.
        cursor = self.cursor(point)
        following = self._advance(cursor)
        if following is None:
            return point
        current = self._class_of(following, long_words)
        if current == EOL:
            following = self._advance(following) or following
        elif current != SPACE:
            following = self._skip(following, (current,), long_words)
        following = self._skip(following, (SPACE,), long_words)
        # The head then stops one cell short of the word it found, so repeated
        # presses walk word by word with the trailing whitespace selected.
        landing = self._retreat(following) or following
        return self._moved_to(point, max(landing, cursor))

    def _next_word_end(self, point: Position, long_words: bool) -> Position:
        cursor = self._advance(self.cursor(point))
        if cursor is None:
            return point
        cursor = self._skip(cursor, (SPACE, EOL), long_words)
        current = self._class_of(cursor, long_words)
        while True:
            following = self._advance(cursor)
            if following is None or self._class_of(following, long_words) != current:
                return self._moved_to(point, cursor)
            cursor = following

    def _prev_word_start(self, point: Position, long_words: bool) -> Position:
        cursor = self._retreat(self.cursor(point))
        if cursor is None:
            return point
        cursor = self._skip(cursor, (SPACE, EOL), long_words, backwards=True)
        current = self._class_of(cursor, long_words)
        while True:
            preceding = self._retreat(cursor)
            if preceding is None or self._class_of(preceding, long_words) != current:
                return self._moved_to(point, cursor)
            cursor = preceding

    def move_next_word_start(self, point: Position) -> Position:
        return self._next_word_start(point, long_words=False)

    def move_next_word_end(self, point: Position) -> Position:
        return self._next_word_end(point, long_words=False)

    def move_prev_word_start(self, point: Position) -> Position:
        return self._prev_word_start(point, long_words=False)

    def move_next_long_word_start(self, point: Position) -> Position:
        return self._next_word_start(point, long_words=True)

    def move_next_long_word_end(self, point: Position) -> Position:
        return self._next_word_end(point, long_words=True)

    def move_prev_long_word_start(self, point: Position) -> Position:
        return self._prev_word_start(point, long_words=True)

    def span(self, selection: Selection,
             region: type[Region]) -> tuple[Position, Position]:
        """Return half-open bounds of the cells a selection highlights."""
        return inclusive_span(self.lines, selection, region, self.metrics)

    # --- whole-selection commands ----------------------------------------

    def select_all(self, point: Position) -> Selection:
        last = len(self.lines)
        return Selection(self.locate((1, 0), 1),
                         self.locate((last, len(self.text(last))), point.top_line))

    def extend_to_line_bounds(self, selection: Selection) -> Selection:
        start, end = ordered(selection.anchor, selection.head)
        return Selection(self.locate((start.line, 0), selection.head.top_line),
                         self.locate((end.line, len(self.text(end.line))),
                                     selection.head.top_line))

    def extend_line_below(self, selection: Selection, count: int) -> Selection:
        """Select whole lines, growing downwards once already line-bounded."""
        bounded = self.extend_to_line_bounds(selection)
        start, end = ordered(selection.anchor, selection.head)
        bounded_start, bounded_end = ordered(bounded.anchor, bounded.head)
        if (start.sort_key, end.sort_key) != (bounded_start.sort_key,
                                              bounded_end.sort_key):
            count -= 1
        last = min(end.line + count, len(self.lines))
        return Selection(self.locate((start.line, 0), selection.head.top_line),
                         self.locate((last, len(self.text(last))),
                                     selection.head.top_line))


def apply_motion(selection: Selection, head: Position, kind: str,
                 select_mode: bool) -> Selection:
    """Place the anchor for a motion that just moved the head."""
    if select_mode:
        return Selection(selection.anchor, head)
    if kind == SPANNING:
        return Selection(selection.head, head)
    return Selection(head, head)


def collapse_selection(selection: Selection) -> Selection:
    return Selection(selection.head, selection.head)


def flip_selections(selection: Selection) -> Selection:
    return Selection(selection.head, selection.anchor)


def string_slice(text: str, start_x: ScreenColumn, end_x: ScreenColumn,
                 metrics: TextMetrics) -> tuple[str, bool]:
    """
    Return the part of text between two display columns.

    The flag says the start column landed inside a wide character, so the
    caller has to draw one cell further left.
    """
    previous = metrics.truncate(text, start_x - 1) if start_x > 0 else 0
    start = metrics.truncate(text, start_x)
    end = metrics.truncate(text, end_x)
    return text[start:end], previous == start


def inclusive_span(lines: list[str], selection: Selection,
                   region: type[Region],
                   metrics: TextMetrics) -> tuple[Position, Position]:
    """
    Return half-open bounds of the cells a selection highlights.

    The cell under the head belongs to the selection, and it is two columns
    wide for a wide character, so the end is grown by that cell's own width.
    """
    start, end = ordered(selection.anchor, selection.head)
    text = lines[end.line - 1]
    index = metrics.truncate(text, end.x)
    width = metrics.width(text[index]) if index < len(text) else 1
    return region.adjust(start, end, width)


def selected_text(lines: list[str], selection: Selection, region: type[Region],
                  metrics: TextMetrics) -> str:
    """Return the text a yank would put on the clipboard."""
    start, end = inclusive_span(lines, selection, region, metrics)
    pieces = []
    for line in range(start.line, end.line + 1):
        text = lines[line - 1]
        start_x, end_x = region.selection_in_line(line, start, end,
                                                  metrics.width(text))
        if start_x is None or end_x is None:
            continue
        pieces.append(string_slice(text, start_x, end_x, metrics)[0])
    return '\n'.join(pieces)
