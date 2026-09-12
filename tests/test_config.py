"""grab.conf parsing, and the shipped example staying true to the defaults."""

from pathlib import Path

import pytest

from helix_config import (
    DEFAULT_CURSOR,
    DEFAULT_SELECTION_BACKGROUND,
    DEFAULT_SELECTION_FOREGROUND,
    normalise_sequence,
    parse_config,
)
from helix_keymap import COMMANDS, DEFAULT_BINDINGS

EXAMPLE = Path(__file__).resolve().parent.parent / 'grab.conf.example'


def parse(text):
    return parse_config(text.splitlines(), DEFAULT_BINDINGS, COMMANDS)


# --- defaults ------------------------------------------------------------

def test_an_empty_file_leaves_every_default():
    config = parse('')
    assert config.selection_foreground == DEFAULT_SELECTION_FOREGROUND
    assert config.selection_background == DEFAULT_SELECTION_BACKGROUND
    assert config.cursor == DEFAULT_CURSOR
    assert config.select_by_word_characters == ''
    assert config.bindings == DEFAULT_BINDINGS
    assert config.errors == []


def test_parsing_does_not_mutate_the_default_map():
    parse('clear_all_shortcuts')
    assert DEFAULT_BINDINGS['h'] == 'move_char_left'


# --- colours -------------------------------------------------------------

@pytest.mark.parametrize('value', ['#fff', '#FFFFFF', '#5294e2'])
def test_a_colour_is_accepted_in_either_length(value):
    assert parse('selection_background ' + value).selection_background == value


@pytest.mark.parametrize('option', [
    'selection_foreground', 'selection_background', 'cursor'])
def test_every_colour_option_is_settable(option):
    assert getattr(parse(option + ' #010203'), option) == '#010203'


def test_a_bad_colour_is_reported_and_the_default_kept():
    config = parse('cursor rebeccapurple')
    assert config.cursor == DEFAULT_CURSOR
    assert config.errors == ['line 1: rebeccapurple is not a colour']


def test_an_unknown_option_is_reported():
    assert parse('selection_colour #fff').errors == \
        ['line 1: unknown option selection_colour']


def test_errors_carry_the_line_number():
    config = parse('\n# comment\ncursor nonsense\n')
    assert config.errors == ['line 3: nonsense is not a colour']


# --- lines ---------------------------------------------------------------

def test_blank_lines_and_comments_are_ignored():
    assert parse('\n\n# a comment\n   \n').errors == []


def test_a_hash_inside_a_value_is_not_a_comment():
    config = parse('select_by_word_characters @-./_~?&=%+#')
    assert config.select_by_word_characters == '@-./_~?&=%+#'


def test_surrounding_whitespace_is_ignored():
    assert parse('   cursor   #010203   ').cursor == '#010203'


# --- bindings ------------------------------------------------------------

def test_a_map_line_binds_a_key():
    assert parse('map z yank').bindings['z'] == 'yank'


def test_a_map_line_accepts_kitty_key_spelling():
    assert parse('map ctrl+shift+p select_all').bindings['C-P'] == 'select_all'


def test_a_map_line_accepts_a_sequence():
    assert parse('map g>t goto_file_start').bindings['g t'] == 'goto_file_start'


def test_a_map_line_can_rebind_a_default():
    assert parse('map j move_line_up').bindings['j'] == 'move_line_up'


def test_a_map_line_naming_an_unknown_command_is_reported():
    config = parse('map z frobnicate')
    assert config.errors == ['line 1: unknown command frobnicate']
    assert 'z' not in config.bindings


def test_a_map_line_without_a_command_is_reported():
    assert parse('map z').errors == \
        ['line 1: map needs a key sequence and a command']


def test_unmap_drops_a_binding():
    config = parse('unmap q')
    assert 'q' not in config.bindings
    assert config.errors == []


def test_unmap_accepts_kitty_key_spelling():
    assert 'C-u' not in parse('unmap ctrl+u').bindings


def test_unmap_of_an_unbound_key_is_reported():
    assert parse('unmap z').errors == ['line 1: z is not bound']


def test_clear_all_shortcuts_empties_the_map():
    assert parse('clear_all_shortcuts').bindings == {}


def test_clear_all_shortcuts_can_be_followed_by_a_fresh_map():
    config = parse('clear_all_shortcuts\nmap y yank')
    assert config.bindings == {'y': 'yank'}


def test_later_lines_win():
    assert parse('map z yank\nmap z quit').bindings['z'] == 'quit'


@pytest.mark.parametrize('written, internal', [
    ('g>g', 'g g'),
    ('ctrl+u', 'C-u'),
    ('g>ctrl+l', 'g C-l'),
    ('escape', 'escape'),
])
def test_normalise_sequence_spells_a_sequence_the_keymap_way(written, internal):
    assert normalise_sequence(written) == internal


# --- the shipped example -------------------------------------------------

def test_the_example_file_documents_exactly_the_default_map():
    lines = [line[2:] for line in EXAMPLE.read_text().splitlines()
             if line.startswith('# map ')]
    config = parse_config(['clear_all_shortcuts'] + lines, DEFAULT_BINDINGS,
                          COMMANDS)
    assert config.bindings == DEFAULT_BINDINGS
    assert config.errors == []


def test_the_example_file_is_inert_as_shipped():
    config = parse_config(EXAMPLE.read_text().splitlines(), DEFAULT_BINDINGS,
                          COMMANDS)
    assert config.bindings == DEFAULT_BINDINGS
    assert config.errors == []
