"""Motions, the selection model and what a yank produces."""

import pytest
from conftest import ASCII_METRICS, COLS, WIDE_METRICS, at, position, where

from helix_motions import (
    COLLAPSING,
    SPANNING,
    ColumnarRegion,
    Motions,
    Position,
    Selection,
    StreamRegion,
    apply_motion,
    collapse_selection,
    flip_selections,
    ordered,
    selected_text,
    string_slice,
    unstyled,
)

# --- coordinates ---------------------------------------------------------

def test_locate_keeps_the_view_when_the_line_is_visible(motions):
    point = motions.locate((2, 0), 1)
    assert (point.top_line, point.y) == (1, 1)


def test_locate_scrolls_down_the_minimum_to_show_the_line(motions):
    point = motions.locate((5, 0), 1)
    assert (point.top_line, point.y) == (3, 2)


def test_locate_scrolls_up_to_show_a_line_above_the_view(motions):
    point = motions.locate((1, 0), 4)
    assert (point.top_line, point.y) == (1, 0)


def test_locate_clamps_a_line_past_the_end_of_the_buffer(motions):
    assert motions.locate((99, 0), 1).line == 6


def test_locate_clamps_a_line_before_the_start_of_the_buffer(motions):
    assert motions.locate((0, 0), 1).line == 1


def test_locate_clamps_the_index_to_the_last_character(motions):
    point = motions.locate((1, 99), 1)
    assert point.x == len('hello world') - 1


def test_locate_clamps_the_column_to_the_window_width():
    motions = Motions(['x' * 100], ASCII_METRICS, 3, COLS)
    assert motions.locate((1, 99), 1).x == COLS - 1


def test_locate_never_scrolls_past_the_last_screenful(motions):
    assert motions.locate((6, 0), 9).top_line == 4


def test_locate_does_not_scroll_a_buffer_shorter_than_the_window(tall_motions):
    point = tall_motions.locate((6, 0), 1)
    assert (point.top_line, point.y) == (1, 5)


def test_cursor_round_trips_a_position(motions):
    point = at(motions, 4, 5)
    assert motions.cursor(point) == (4, 5)


# --- character and line motions ------------------------------------------

def test_move_char_right_advances_one_cell(motions):
    assert where(motions, motions.move_char_right(at(motions, 1, 0))) == (1, 1)


def test_move_char_right_stops_at_the_last_character(motions):
    end = at(motions, 1, len('hello world') - 1)
    assert where(motions, motions.move_char_right(end)) == (1, 10)


def test_move_char_left_retreats_one_cell(motions):
    assert where(motions, motions.move_char_left(at(motions, 1, 4))) == (1, 3)


def test_move_char_left_stops_at_the_line_start(motions):
    assert where(motions, motions.move_char_left(at(motions, 1, 0))) == (1, 0)


def test_move_line_down_keeps_the_column(motions):
    assert where(motions, motions.move_line_down(at(motions, 1, 4))) == (2, 4)


def test_move_line_down_clamps_the_column_on_a_shorter_line(motions):
    assert where(motions, motions.move_line_down(at(motions, 2, 12))) == (3, 0)


def test_move_line_down_at_the_last_line_stays_put(motions):
    bottom = at(motions, 6, 0, top_line=4)
    assert where(motions, motions.move_line_down(bottom)) == (6, 0)


def test_move_line_up_at_the_first_line_stays_put(motions):
    assert where(motions, motions.move_line_up(at(motions, 1, 2))) == (1, 2)


def test_move_line_down_past_the_view_scrolls_by_one(motions):
    bottom = at(motions, 3, 0)
    assert bottom.y == 2
    moved = motions.move_line_down(bottom)
    assert (moved.line, moved.top_line, moved.y) == (4, 2, 2)


def test_move_line_up_above_the_view_scrolls_by_one(motions):
    top = at(motions, 4, 0, top_line=4)
    moved = motions.move_line_up(top)
    assert (moved.line, moved.top_line, moved.y) == (3, 3, 0)


def test_an_empty_line_puts_the_head_at_column_zero(motions):
    assert motions.move_line_down(at(motions, 2, 5)).x == 0


# --- paging and scrolling ------------------------------------------------

def test_move_page_down_advances_by_a_window(motions):
    assert motions.move_page_down(at(motions, 1, 0)).line == 4


def test_move_page_up_clamps_at_the_first_line(motions):
    assert motions.move_page_up(at(motions, 2, 0)).line == 1


def test_move_half_page_down_advances_by_half_a_window(motions):
    assert motions.move_half_page_down(at(motions, 1, 0)).line == 2


def test_move_half_page_up_retreats_by_half_a_window(motions):
    assert motions.move_half_page_up(at(motions, 5, 0, top_line=4)).line == 4


def test_scroll_moves_the_view_and_carries_the_head(motions):
    scrolled = motions.scroll(at(motions, 1, 0), 1)
    assert (scrolled.top_line, scrolled.y, scrolled.line) == (2, 0, 2)


def test_scroll_stops_at_the_top(motions):
    assert motions.scroll(at(motions, 1, 0), -1).top_line == 1


def test_scroll_stops_at_the_bottom(motions):
    assert motions.scroll(at(motions, 6, 0, top_line=4), 5).top_line == 4


# --- goto ----------------------------------------------------------------

def test_goto_line_start(motions):
    assert where(motions, motions.goto_line_start(at(motions, 1, 7))) == (1, 0)


def test_goto_line_end_lands_on_the_last_character(motions):
    assert where(motions, motions.goto_line_end(at(motions, 1, 0))) == (1, 10)


def test_goto_line_end_on_an_empty_line_stays_at_zero(motions):
    assert where(motions, motions.goto_line_end(at(motions, 3, 0))) == (3, 0)


def test_goto_first_nonwhitespace_skips_the_indent(motions):
    assert where(motions, motions.goto_first_nonwhitespace(at(motions, 2, 0))) == (2, 2)


def test_goto_first_nonwhitespace_on_an_empty_line(motions):
    assert where(motions, motions.goto_first_nonwhitespace(at(motions, 3, 0))) == (3, 0)


def test_goto_file_start_scrolls_back_to_the_top(motions):
    point = motions.goto_file_start(at(motions, 6, 0, top_line=4))
    assert (point.line, point.top_line, point.x) == (1, 1, 0)


def test_goto_last_line_lands_on_the_last_line_start(motions):
    point = motions.goto_last_line(at(motions, 1, 3))
    assert (point.line, point.x) == (6, 0)


def test_goto_line_jumps_to_an_absolute_line(motions):
    assert motions.goto_line(at(motions, 1, 0), 4).line == 4


def test_goto_line_clamps_past_the_buffer(motions):
    assert motions.goto_line(at(motions, 1, 0), 99).line == 6


# --- word motions --------------------------------------------------------

def test_next_word_start_stops_before_the_following_word(motions):
    # "hello world": the head lands on the space, so the selection is
    # "hello " once the anchor stays behind.
    assert where(motions, motions.move_next_word_start(at(motions, 1, 0))) == (1, 5)


def test_next_word_start_repeated_walks_word_by_word(motions):
    point = motions.move_next_word_start(at(motions, 1, 0))
    point = motions.move_next_word_start(point)
    assert where(motions, point) == (1, 10)


def test_next_word_start_stops_at_punctuation(motions):
    # "foo(bar) baz": ( is neither a word character nor whitespace.
    assert where(motions, motions.move_next_word_start(at(motions, 4, 0))) == (4, 2)


def test_next_long_word_start_runs_through_punctuation(motions):
    point = motions.move_next_long_word_start(at(motions, 4, 0))
    assert where(motions, point) == (4, 8)


def test_next_word_start_crosses_into_the_following_line(motions):
    point = motions.move_next_word_start(at(motions, 1, 6))
    assert where(motions, point) == (1, 10)
    assert where(motions, motions.move_next_word_start(point)) == (2, 1)


def test_next_word_start_at_the_end_of_the_buffer_stays(motions):
    end = at(motions, 6, 3, top_line=4)
    assert where(motions, motions.move_next_word_start(end)) == (6, 3)


def test_next_word_end_lands_on_the_last_character_of_the_word(motions):
    assert where(motions, motions.move_next_word_end(at(motions, 1, 0))) == (1, 4)


def test_next_word_end_from_a_word_end_takes_the_following_word(motions):
    assert where(motions, motions.move_next_word_end(at(motions, 1, 4))) == (1, 10)


def test_next_word_end_stops_at_punctuation(motions):
    assert where(motions, motions.move_next_word_end(at(motions, 4, 0))) == (4, 2)


def test_next_long_word_end_runs_through_punctuation(motions):
    assert where(motions, motions.move_next_long_word_end(at(motions, 4, 0))) == (4, 7)


def test_prev_word_start_from_mid_word_reaches_its_start(motions):
    assert where(motions, motions.move_prev_word_start(at(motions, 1, 8))) == (1, 6)


def test_prev_word_start_from_a_word_start_takes_the_previous_word(motions):
    assert where(motions, motions.move_prev_word_start(at(motions, 1, 6))) == (1, 0)


def test_prev_word_start_crosses_into_the_previous_line(motions):
    assert where(motions, motions.move_prev_word_start(at(motions, 2, 2))) == (1, 6)


def test_prev_word_start_at_the_buffer_start_stays(motions):
    assert where(motions, motions.move_prev_word_start(at(motions, 1, 0))) == (1, 0)


def test_prev_long_word_start_runs_through_punctuation(motions):
    point = motions.move_prev_long_word_start(at(motions, 4, 9))
    assert where(motions, point) == (4, 0)


def test_default_word_characters_keep_a_dotted_path_together():
    motions = Motions(['src/main.py rest'], ASCII_METRICS, 3, 40)
    assert where(motions, motions.move_next_word_start(at(motions, 1, 0))) == (1, 11)


def test_word_characters_are_configurable():
    motions = Motions(['src/main.py rest'], ASCII_METRICS, 3, 40,
                      word_characters='')
    assert where(motions, motions.move_next_word_start(at(motions, 1, 0))) == (1, 2)


@pytest.mark.parametrize('motion', [
    'move_next_word_start',
    'move_prev_word_start',
    'move_next_word_end',
    'move_next_long_word_start',
    'move_prev_long_word_start',
    'move_next_long_word_end',
])
def test_word_motions_stay_inside_the_buffer(motions, motion):
    for line in range(1, 7):
        for index in range(0, len(motions.text(line)) + 1):
            point = getattr(motions, motion)(at(motions, line, index))
            assert 1 <= point.line <= 6
            assert 0 <= point.x < COLS


# --- anchor placement ----------------------------------------------------

def test_a_collapsing_motion_leaves_a_single_cell_selection(motions):
    start = Selection(at(motions, 1, 0), at(motions, 1, 0))
    head = motions.move_char_right(start.head)
    updated = apply_motion(start, head, COLLAPSING, select_mode=False)
    assert updated.anchor == updated.head


def test_a_spanning_motion_keeps_the_cells_travelled_over(motions):
    start = Selection(at(motions, 1, 0), at(motions, 1, 0))
    head = motions.move_next_word_start(start.head)
    updated = apply_motion(start, head, SPANNING, select_mode=False)
    assert (where(motions, updated.anchor), where(motions, updated.head)) == \
        ((1, 0), (1, 5))


def test_select_mode_keeps_the_anchor_for_a_collapsing_motion(motions):
    start = Selection(at(motions, 1, 0), at(motions, 1, 3))
    head = motions.move_char_right(start.head)
    updated = apply_motion(start, head, COLLAPSING, select_mode=True)
    assert where(motions, updated.anchor) == (1, 0)


def test_select_mode_keeps_the_anchor_for_a_spanning_motion(motions):
    start = Selection(at(motions, 1, 0), at(motions, 1, 3))
    head = motions.move_next_word_start(start.head)
    updated = apply_motion(start, head, SPANNING, select_mode=True)
    assert where(motions, updated.anchor) == (1, 0)


def test_collapse_selection_drops_the_anchor_onto_the_head(motions):
    selection = Selection(at(motions, 1, 0), at(motions, 1, 4))
    assert collapse_selection(selection) == Selection(selection.head, selection.head)


def test_flip_selections_swaps_the_ends(motions):
    selection = Selection(at(motions, 1, 0), at(motions, 1, 4))
    assert flip_selections(selection) == Selection(selection.head, selection.anchor)


def test_ordered_sorts_by_buffer_order_not_by_column(motions):
    later_line = at(motions, 2, 0)
    earlier_line = at(motions, 1, 9)
    assert ordered(later_line, earlier_line) == (earlier_line, later_line)


# --- whole-selection commands --------------------------------------------

def test_select_all_covers_the_whole_buffer(motions):
    selection = motions.select_all(at(motions, 1, 0))
    start, end = ordered(selection.anchor, selection.head)
    assert (start.line, start.x) == (1, 0)
    assert (end.line, end.x) == (6, len('tail') - 1)


def test_extend_to_line_bounds_grows_a_partial_selection(motions):
    selection = Selection(at(motions, 1, 3), at(motions, 1, 6))
    bounded = motions.extend_to_line_bounds(selection)
    assert (where(motions, bounded.anchor), where(motions, bounded.head)) == \
        ((1, 0), (1, 10))


def test_extend_to_line_bounds_spans_every_touched_line(motions):
    selection = Selection(at(motions, 1, 3), at(motions, 2, 4))
    bounded = motions.extend_to_line_bounds(selection)
    assert (bounded.anchor.line, bounded.head.line) == (1, 2)


def test_extend_line_below_first_selects_the_current_line(motions):
    selection = Selection(at(motions, 1, 3), at(motions, 1, 3))
    extended = motions.extend_line_below(selection, 1)
    assert (where(motions, extended.anchor), where(motions, extended.head)) == \
        ((1, 0), (1, 10))


def test_extend_line_below_then_grows_by_a_line(motions):
    selection = Selection(at(motions, 1, 3), at(motions, 1, 3))
    extended = motions.extend_line_below(selection, 1)
    extended = motions.extend_line_below(extended, 1)
    assert (extended.anchor.line, extended.head.line) == (1, 2)


def test_extend_line_below_with_a_count_takes_that_many_lines(motions):
    selection = Selection(at(motions, 1, 3), at(motions, 1, 3))
    extended = motions.extend_line_below(selection, 3)
    assert (extended.anchor.line, extended.head.line) == (1, 3)


def test_extend_line_below_clamps_at_the_last_line(motions):
    selection = Selection(at(motions, 6, 0, 4), at(motions, 6, 0, 4))
    extended = motions.extend_line_below(selection, 5)
    assert extended.head.line == 6


def test_extend_line_below_keeps_a_backwards_selection_bounded(motions):
    selection = Selection(at(motions, 3, 0), at(motions, 1, 4))
    extended = motions.extend_line_below(selection, 1)
    assert (extended.anchor.line, extended.head.line) == (1, 3)


# --- region geometry -----------------------------------------------------

def test_a_one_cell_selection_spans_one_column(motions):
    point = at(motions, 1, 4)
    start, end = motions.span(Selection(point, point), StreamRegion)
    assert (start.x, end.x) == (4, 5)


def test_a_backwards_selection_spans_the_same_cells(motions):
    forwards = Selection(at(motions, 1, 2), at(motions, 1, 6))
    backwards = Selection(at(motions, 1, 6), at(motions, 1, 2))
    assert motions.span(forwards, StreamRegion) == motions.span(backwards, StreamRegion)


def test_a_columnar_selection_normalises_its_columns(motions):
    selection = Selection(at(motions, 1, 8), at(motions, 2, 3))
    start, end = motions.span(selection, ColumnarRegion)
    assert (start.x, end.x) == (3, 9)


def test_stream_region_covers_whole_intermediate_lines(motions):
    selection = Selection(at(motions, 1, 4), at(motions, 4, 2))
    start, end = motions.span(selection, StreamRegion)
    assert StreamRegion.selection_in_line(2, start, end, 15) == (0, 15)
    assert StreamRegion.line_inside_region(2, start, end)


def test_stream_region_excludes_lines_outside_the_selection(motions):
    selection = Selection(at(motions, 2, 0), at(motions, 2, 4))
    start, end = motions.span(selection, StreamRegion)
    assert StreamRegion.selection_in_line(1, start, end, 11) == (None, None)
    assert StreamRegion.line_outside_region(5, start, end)


def test_columnar_region_uses_the_same_columns_on_every_line(motions):
    selection = Selection(at(motions, 1, 2), at(motions, 4, 5))
    start, end = motions.span(selection, ColumnarRegion)
    assert ColumnarRegion.selection_in_line(2, start, end, 15) == (2, 6)
    assert ColumnarRegion.selection_in_line(4, start, end, 12) == (2, 6)


def test_selection_lines_lists_the_rows_it_touches(motions):
    selection = Selection(at(motions, 4, 0), at(motions, 2, 0))
    assert list(selection.lines) == [2, 3, 4]


# --- yanked text ---------------------------------------------------------

def test_yanking_a_single_cell_takes_one_character(motions, buffer_lines):
    point = at(motions, 1, 4)
    selection = Selection(point, point)
    assert selected_text(buffer_lines, selection, StreamRegion, ASCII_METRICS) == 'o'


def test_yanking_a_word_takes_the_head_cell_too(motions, buffer_lines):
    selection = Selection(at(motions, 1, 0), at(motions, 1, 4))
    assert selected_text(buffer_lines, selection, StreamRegion,
                         ASCII_METRICS) == 'hello'


def test_yanking_backwards_takes_the_same_text(motions, buffer_lines):
    selection = Selection(at(motions, 1, 4), at(motions, 1, 0))
    assert selected_text(buffer_lines, selection, StreamRegion,
                         ASCII_METRICS) == 'hello'


def test_yanking_across_lines_joins_with_newlines(motions, buffer_lines):
    selection = Selection(at(motions, 1, 6), at(motions, 2, 8))
    assert selected_text(buffer_lines, selection, StreamRegion,
                         ASCII_METRICS) == 'world\n  indente'


def test_yanking_a_line_selection_takes_the_whole_line(motions, buffer_lines):
    selection = motions.extend_line_below(
        Selection(at(motions, 1, 3), at(motions, 1, 3)), 1)
    assert selected_text(buffer_lines, selection, StreamRegion,
                         ASCII_METRICS) == 'hello world'


def test_yanking_an_empty_line_yields_an_empty_piece(motions, buffer_lines):
    selection = Selection(at(motions, 2, 14), at(motions, 4, 2))
    assert selected_text(buffer_lines, selection, StreamRegion,
                         ASCII_METRICS) == 'e\n\nfoo'


def test_yanking_a_columnar_selection_takes_a_rectangle(motions, buffer_lines):
    selection = Selection(at(motions, 4, 0), at(motions, 5, 2))
    assert selected_text(buffer_lines, selection, ColumnarRegion,
                         ASCII_METRICS) == 'foo\none'


def test_yanking_covers_a_wide_character_whole():
    lines = ['a東b']
    motions = Motions(lines, WIDE_METRICS, 3, COLS)
    selection = Selection(motions.locate((1, 1), 1), motions.locate((1, 1), 1))
    assert selected_text(lines, selection, StreamRegion, WIDE_METRICS) == '東'


def test_string_slice_reports_landing_inside_a_wide_character():
    text = 'a東b'
    piece, half = string_slice(text, 2, 3, WIDE_METRICS)
    assert (piece, half) == ('東', True)


def test_string_slice_takes_a_plain_range():
    assert string_slice('hello', 1, 4, ASCII_METRICS) == ('ell', False)


# --- styled input --------------------------------------------------------

def test_unstyled_drops_sgr_sequences():
    assert unstyled('\x1b[31mred\x1b[m') == 'red'


def test_unstyled_drops_osc_sequences():
    assert unstyled('\x1b]8;;http://example.com\x1b\\link\x1b]8;;\x1b\\') == 'link'


def test_unstyled_leaves_plain_text_alone():
    assert unstyled('plain text') == 'plain text'


def test_positions_sort_by_line_then_column():
    assert position(9, 0, 1).sort_key < position(0, 1, 1).sort_key


def test_moved_offsets_every_axis():
    assert position(1, 2, 3).moved(dx=1, dy=2, dtop=3) == Position(2, 4, 6)
