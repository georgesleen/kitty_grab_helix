"""Key naming, config-file chord spelling and the dispatch state machine."""

from typing import NamedTuple

import pytest

from helix_keymap import (
    CANCELLED,
    COMMAND,
    COMMANDS,
    DEFAULT_BINDINGS,
    PENDING,
    UNBOUND,
    Keymap,
    key_name,
    normalise_chord,
)
from helix_motions import MOTION_KINDS


class Event(NamedTuple):
    """Stand-in for kitty's KeyEvent, same field names."""

    key: str
    shifted_key: str = ''
    ctrl: bool = False
    alt: bool = False
    shift: bool = False
    super: bool = False
    hyper: bool = False
    meta: bool = False


# --- key naming ----------------------------------------------------------

def test_a_plain_letter_names_itself():
    assert key_name(Event(key='j')) == 'j'


def test_a_shifted_letter_names_the_capital():
    assert key_name(Event(key='x', shifted_key='X', shift=True)) == 'X'


def test_a_shifted_symbol_names_the_symbol():
    assert key_name(Event(key='5', shifted_key='%', shift=True)) == '%'


def test_ctrl_prefixes_the_name():
    assert key_name(Event(key='u', ctrl=True)) == 'C-u'


def test_alt_prefixes_the_name():
    assert key_name(Event(key=';', alt=True)) == 'A-;'


def test_a_functional_key_is_lowercased():
    assert key_name(Event(key='ESCAPE')) == 'escape'


def test_a_multi_word_functional_key_keeps_its_underscore():
    assert key_name(Event(key='PAGE_UP')) == 'page_up'


def test_shift_on_a_functional_key_stays_a_modifier():
    assert key_name(Event(key='LEFT', shift=True)) == 'S-left'


def test_ctrl_and_shift_combine():
    assert key_name(Event(key='x', shifted_key='X', ctrl=True, shift=True)) == 'C-X'


def test_hyper_is_named_so_it_cannot_pass_for_a_plain_key():
    # Left Alt is Hyper on some keyboard layouts; hyper+j must not fire j.
    assert key_name(Event(key='j', hyper=True)) == 'H-j'


def test_modifiers_are_written_in_a_fixed_order():
    assert key_name(Event(key='k', ctrl=True, alt=True, meta=True)) == 'C-A-M-k'


# --- config file chord spelling ------------------------------------------

@pytest.mark.parametrize('chord, expected', [
    ('h', 'h'),
    ('ctrl+u', 'C-u'),
    ('CTRL+u', 'C-u'),
    ('control+u', 'C-u'),
    ('C-u', 'C-u'),
    ('shift+x', 'X'),
    ('S-x', 'X'),
    ('alt+;', 'A-;'),
    ('A-;', 'A-;'),
    ('ctrl+shift+left', 'C-S-left'),
    ('esc', 'escape'),
    ('escape', 'escape'),
    ('return', 'enter'),
    ('pgup', 'page_up'),
    ('PAGE_DOWN', 'page_down'),
    ('space', 'space'),
    ('-', '-'),
    ('A--', 'A--'),
    ('+', '+'),
    ('ctrl++', 'C-+'),
    ('%', '%'),
])
def test_normalise_chord_matches_the_name_a_key_event_gets(chord, expected):
    assert normalise_chord(chord) == expected


def test_modifier_order_is_normalised():
    assert normalise_chord('alt+ctrl+k') == 'C-A-k'


# --- vocabulary ----------------------------------------------------------

def test_every_bound_command_is_a_motion_or_a_handler_command():
    handler_commands = {
        'goto_line', 'select_mode', 'normal_mode', 'columnar_mode',
        'collapse_selection', 'flip_selections', 'extend_line_below',
        'extend_to_line_bounds', 'select_all', 'scroll_up', 'scroll_down',
        'yank', 'quit',
    }
    assert COMMANDS == set(MOTION_KINDS) | handler_commands


def test_the_default_map_binds_the_helix_keys_a_user_expects():
    for key in 'hjklwbeGxXv%;y':
        assert key in DEFAULT_BINDINGS


# --- dispatch ------------------------------------------------------------

@pytest.mark.parametrize('key, command', [
    ('h', 'move_char_left'),
    ('j', 'move_line_down'),
    ('k', 'move_line_up'),
    ('l', 'move_char_right'),
    ('w', 'move_next_word_start'),
    ('b', 'move_prev_word_start'),
    ('e', 'move_next_word_end'),
    ('W', 'move_next_long_word_start'),
    ('x', 'extend_line_below'),
    ('X', 'extend_to_line_bounds'),
    ('v', 'select_mode'),
    ('%', 'select_all'),
    (';', 'collapse_selection'),
    ('A-;', 'flip_selections'),
    ('C-u', 'move_half_page_up'),
    ('C-d', 'move_half_page_down'),
    ('C-e', 'scroll_down'),
    ('C-y', 'scroll_up'),
    ('y', 'yank'),
    ('enter', 'yank'),
    ('q', 'quit'),
    ('escape', 'normal_mode'),
])
def test_a_bound_key_resolves_to_its_command(key, command):
    assert Keymap().feed(key) == (COMMAND, command, 1, '')


def test_an_unbound_key_is_reported():
    assert Keymap().feed('z').kind == UNBOUND


def test_a_prefix_key_waits_for_the_rest_of_the_sequence():
    keymap = Keymap()
    assert keymap.feed('g').kind == PENDING
    assert keymap.feed('g').command == 'goto_file_start'


@pytest.mark.parametrize('second, command', [
    ('g', 'goto_file_start'),
    ('e', 'goto_last_line'),
    ('h', 'goto_line_start'),
    ('l', 'goto_line_end'),
    ('s', 'goto_first_nonwhitespace'),
])
def test_goto_mode_sequences(second, command):
    keymap = Keymap()
    keymap.feed('g')
    assert keymap.feed(second).command == command


def test_an_unbound_second_key_abandons_the_sequence():
    keymap = Keymap()
    keymap.feed('g')
    assert keymap.feed('z').kind == UNBOUND
    assert keymap.feed('j').command == 'move_line_down'


def test_a_count_is_handed_to_the_next_command():
    keymap = Keymap()
    assert keymap.feed('3').kind == PENDING
    assert keymap.feed('j') == (COMMAND, 'move_line_down', 3, '')


def test_a_count_can_be_more_than_one_digit():
    keymap = Keymap()
    for digit in '124':
        keymap.feed(digit)
    assert keymap.feed('k').count == 124


def test_zero_continues_a_count():
    keymap = Keymap()
    keymap.feed('1')
    keymap.feed('0')
    assert keymap.feed('j').count == 10


def test_zero_alone_is_not_a_count():
    assert Keymap().feed('0').kind == UNBOUND


def test_a_count_applies_to_a_sequence_too():
    keymap = Keymap()
    keymap.feed('2')
    keymap.feed('g')
    assert keymap.feed('g') == (COMMAND, 'goto_file_start', 2, '')


def test_a_count_does_not_survive_the_command_it_counted():
    keymap = Keymap()
    keymap.feed('5')
    keymap.feed('j')
    assert keymap.feed('j').count == 1


def test_escape_cancels_a_pending_sequence_instead_of_quitting():
    keymap = Keymap()
    keymap.feed('g')
    assert keymap.feed('escape').kind == CANCELLED
    assert keymap.feed('g').kind == PENDING


def test_escape_cancels_a_pending_count():
    keymap = Keymap()
    keymap.feed('7')
    assert keymap.feed('escape').kind == CANCELLED
    assert keymap.feed('j').count == 1


def test_escape_on_its_own_is_the_normal_mode_command():
    assert Keymap().feed('escape').command == 'normal_mode'


def test_pending_text_shows_what_is_held():
    keymap = Keymap()
    keymap.feed('1')
    keymap.feed('2')
    keymap.feed('g')
    assert keymap.pending_text == '12g'


def test_pending_text_is_empty_once_a_command_fires():
    keymap = Keymap()
    keymap.feed('4')
    keymap.feed('j')
    assert keymap.pending_text == ''


def test_custom_bindings_replace_the_defaults():
    keymap = Keymap({'z': 'yank'})
    assert keymap.feed('z').command == 'yank'
    assert keymap.feed('y').kind == UNBOUND


def test_custom_sequences_become_prefixes():
    keymap = Keymap({'space y': 'yank'})
    assert keymap.feed('space').kind == PENDING
    assert keymap.feed('y').command == 'yank'


def test_feeding_a_keymap_does_not_mutate_the_default_map():
    Keymap({'z': 'yank'})
    assert 'z' not in DEFAULT_BINDINGS
