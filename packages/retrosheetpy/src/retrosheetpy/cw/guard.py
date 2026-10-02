"""New-season guard: say loudly when an event file is not read completely and cleanly.

Chadwick keeps going past things it does not understand: an unparseable play leaves a
half-filled row, an unknown record type is skipped with a warning on stderr, and a file
that stops being readable simply ends. A new season's files can contain notation the port
(or Chadwick 0.10.0) has never seen, so this lists every such case instead of letting a
run look clean. An empty list means: every ``id`` line became a game, every play parsed,
and the reader logged no warning.
"""

import logging

from retrosheetpy.cw.book import scorebook_read
from retrosheetpy.cw.gameiter import GameIter


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage().replace("\n", " ").strip())


def check_event_file(data: bytes, source: str = "") -> list[str]:
    """Problems found reading one event file's bytes (empty if none)."""
    where = f"{source}: " if source else ""
    problems: list[str] = []
    handler = _Collect()
    log = logging.getLogger("retrosheetpy.cw")
    log.addHandler(handler)
    try:
        games = scorebook_read(data)
        if games is None:
            return [f"{where}file is empty or unreadable"]
        ids = sum(1 for line in data.split(b"\n") if line.startswith(b"id,"))
        if ids != len(games):
            problems.append(f"{where}{ids} id records but {len(games)} games were read")
        for game in games:
            gi = GameIter(game)
            while gi.event is not None:
                ev = gi.event
                if ev.event_text != "NP" and not gi.parse_ok:
                    problems.append(f"{where}{game.game_id}: unparsed play {ev.event_text!r}")
                gi.next()
    finally:
        log.removeHandler(handler)
    problems.extend(f"{where}{m}" for m in handler.messages)
    return problems
