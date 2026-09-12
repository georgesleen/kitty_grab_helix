import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helix_motions import Motions, Position, TextMetrics  # noqa: E402

# Display metrics for a terminal where every character is one cell wide.
ASCII_METRICS = TextMetrics(
    width=len,
    truncate=lambda text, column: min(max(column, 0), len(text)))


def _wide_width(text):
    return sum(2 if ord(character) > 0x2e80 else 1 for character in text)


def _wide_truncate(text, column):
    used = 0
    for index, character in enumerate(text):
        step = 2 if ord(character) > 0x2e80 else 1
        if used + step > column:
            return index
        used += step
    return len(text)


# Metrics for a terminal where CJK characters take two cells.
WIDE_METRICS = TextMetrics(width=_wide_width, truncate=_wide_truncate)

BUFFER = [
    'hello world',
    '  indented line',
    '',
    'foo(bar) baz',
    'one two three',
    'tail',
]

ROWS = 3
COLS = 20


@pytest.fixture
def buffer_lines():
    return list(BUFFER)


@pytest.fixture
def motions(buffer_lines):
    """A three-row window onto a six-line buffer."""
    return Motions(buffer_lines, ASCII_METRICS, ROWS, COLS)


@pytest.fixture
def tall_motions():
    """A window taller than its buffer, so nothing ever scrolls."""
    return Motions(list(BUFFER), ASCII_METRICS, 10, COLS)


def at(motions, line, index, top_line=1):
    """Position of a (1-based line, 0-based character index) pair."""
    return motions.locate((line, index), top_line)


def where(motions, point):
    """Inverse of `at`, for readable assertions."""
    return (point.line, motions.cursor(point)[1])


def position(x, y, top_line):
    return Position(x, y, top_line)
