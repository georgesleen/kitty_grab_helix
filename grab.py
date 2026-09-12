# Entry point kitty loads. It hands the window's full scrollback to the real
# kitten in _grab_ui, which runs as an overlay.

from typing import Any, Dict, List

from kittens.tui.handler import result_handler
from kitty.typing_compat import BossType

import _grab_ui


def main(args: List[str]) -> None:
    pass


@result_handler(no_ui=True)
def handle_result(args: List[str], data: Dict[str, Any], target_window_id: int,
                  boss: BossType) -> None:
    window = boss.window_id_map.get(target_window_id)
    if window is None:
        return
    if window.tabref() is None:
        return
    content = window.as_text(as_ansi=True, add_history=True,
                             add_wrap_markers=True)
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    n_lines = content.count('\n')
    top_line = (n_lines - (window.screen.lines - 1) - window.screen.scrolled_by)
    boss._run_kitten(_grab_ui.__file__, args=[
        *args[1:],
        '--title={}'.format(window.title),
        '--cursor-x={}'.format(window.screen.cursor.x),
        '--cursor-y={}'.format(window.screen.cursor.y),
        '--top-line={}'.format(top_line)],
        input_data=content.encode('utf-8'),
        window=window)
