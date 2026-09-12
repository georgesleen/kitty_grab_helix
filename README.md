# kitty_grab_helix

Keyboard-driven text selection for [kitty][kitty], with [helix][helix] keys and
the helix selection model. A fork of [kitty_grab][upstream], whose screen
handling it keeps and whose vim-flavoured modal editing it replaces.

[kitty]: https://sw.kovidgoyal.net/kitty/
[helix]: https://helix-editor.com/
[upstream]: https://github.com/yurikhan/kitty_grab

kitty can select text with the mouse. This adds a copy mode you drive from the
keyboard: press a key, move the selection around the scrollback, press `y`.

## The selection model

There is always a selection, and it is never empty. The cell under the cursor
is part of it, a motion replaces it, and `v` switches to extending it. That is
helix, not vim: in vim you are outside a selection until you press `v`, and the
two models diverge from the first keypress.

Concretely:

- `w` selects the word it travels over, rather than moving a bare cursor.
- `h j k l` and the goto motions leave a one-cell selection behind them.
- `v` enters select mode, where every motion extends instead of replacing.
- `;` collapses the selection onto the cursor, `Alt+;` flips its ends.
- `x` takes whole lines, one more on each press.

## Keys

| Key | Command |
| --- | --- |
| `h` `j` `k` `l`, arrows | move by cell and line |
| `w` `b` `e` | word start forwards, word start backwards, word end |
| `W` `B` `E` | the same, treating punctuation as part of the word |
| `g g` / `g e` | buffer start / last line |
| `g h` / `g l` / `g s` | line start / line end / first non-whitespace |
| `<count>G` | go to that line |
| `Ctrl+u` / `Ctrl+d` | half page up / down |
| `Ctrl+b` / `Ctrl+f`, page keys | page up / down |
| `Ctrl+y` / `Ctrl+e` | scroll the view up / down |
| `v` | select (extend) mode |
| `Ctrl+v` | columnar selection |
| `;` / `Alt+;` | collapse selection / flip its ends |
| `x` / `X` | select line below / extend to line bounds |
| `%` | select the whole buffer |
| `y`, `Enter` | copy the selection and exit |
| `q` | exit |
| `Escape` | leave select mode, cancel a pending key, or exit |

A count typed before a command repeats it, so `5j` and `3x` do what you expect.

`Ctrl+v` is the one key here helix does not have: helix has no columnar
selection, and a terminal scrollback full of columns is exactly where you want
one. It starts extending as it switches, since a rectangle that collapses on
every motion would only ever be one cell.

## Install

Map a key in `kitty.conf` to run the kitten:

    map ctrl+shift+x kitten /path/to/kitty_grab_helix/grab.py

Any checkout works; kitty adds the kitten's own directory to `sys.path`, so the
sibling modules resolve without copying anything into your kitty config
directory.

With Nix, the flake exposes the kitten as a package:

    inputs.kitty_grab_helix.url = "github:georgesleen/kitty_grab_helix";

    programs.kitty.keybindings."ctrl+shift+x" =
      "kitten ${inputs.kitty_grab_helix.packages.${pkgs.system}.default}/grab.py";

## Configuration

Optional, and read fresh every time the kitten starts: `grab.conf` beside your
`kitty.conf`. `grab.conf.example` lists every option and the whole default map.

    selection_background #5294e2
    map ctrl+shift+p     select_all
    map g>t              goto_file_start
    unmap q

Keys are written as in `kitty.conf` (`ctrl+u`, `alt+;`, `shift+x`) or as in
helix (`C-u`, `A-;`, `X`); a sequence is chords joined with `>`. A `map` naming
a command that does not exist, an unknown option or a malformed colour is
reported in the kitten's title bar rather than ignored.

Selecting into the primary or secondary buffer instead of the clipboard:

    map ctrl+shift+x kitten /path/to/kitty_grab_helix/grab.py --copy-to primary

## Development

    nix develop      # or direnv allow
    make check       # ruff, nixfmt, pytest
    nix flake check  # the same, hermetically

The kitten is split so that the part with the bugs in it can be tested without
a terminal. `helix_motions.py` (motions, selection model, what a yank
produces), `helix_keymap.py` (key naming, sequences, counts) and
`helix_config.py` (the config file) import no kitty code and take their text
metrics as functions; `_grab_ui.py` is the kitty half and holds the drawing,
the key events and the clipboard.

## License

GPL-3.0-or-later, as upstream. Copyright of the original kitty_grab code
remains with Yuri Khan and its contributors.
