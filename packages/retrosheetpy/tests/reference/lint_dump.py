"""Run the port's ``game_lint`` on an event file and print what ``lint_dump.c`` prints.

Chadwick writes straight to stderr; here each log record is one stderr write. The "invalid
record" warning echoes the record with whatever end-of-line it had (none when the line was cut at
the buffer size), so it gets no newline added; every other message ends in one.
"""

import logging

from retrosheetpy.cw.game import read_games
from retrosheetpy.cw.lint import game_lint


class _Stream(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.text = ""

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if msg.startswith("WARNING: reading stopped"):
            return  # the port's own diagnostic; Chadwick prints nothing here
        raw = "skipping invalid record" in msg  # echoes the record as read, EOL (if any) included
        self.text += msg if raw or msg.endswith("\n") else msg + "\n"


def dump(data: bytes) -> tuple[list[str], bool]:
    """(lines, crashed): C ``exit``/NULL cases surface as ``ValueError`` in the port."""
    log = logging.getLogger("retrosheetpy.cw")
    stream = _Stream()
    log.addHandler(stream)
    crashed = False
    try:
        for game in read_games(data):
            stream.text += f"GAME {game.game_id}\n"
            ok = game_lint(game)
            stream.text += f"lint={int(ok)}\n"
    except ValueError:
        crashed = True
    finally:
        log.removeHandler(stream)
    text = stream.text
    return (text[:-1] if text.endswith("\n") else text).split("\n") if text else [], crashed
