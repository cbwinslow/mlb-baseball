"""Port of the parts of Chadwick's ``src/cwtools/cwtools.c`` that every tool shares.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice.

``cwtools.c`` is the driver of ``cwevent``, ``cwgame`` and the other tools: it reads the
team file and rosters, reads each event file as a scorebook, picks the games the options
select, and hands each game with its two rosters to the tool. Reading files from disk
and the command line are left to the caller; these functions take bytes.
"""

import re
from collections.abc import Callable, Iterator

from retrosheetpy.cw.book import scorebook_read
from retrosheetpy.cw.game import Game
from retrosheetpy.cw.roster import League, Roster


def read_rosters(team_file: bytes, year: str, roster_file: Callable[[str], bytes | None]) -> League:
    """``cwtools_read_rosters``: the team file, then each team's ``<team><year>.ROS`` if present.

    ``roster_file`` is given a file name and returns its contents, or ``None`` where Chadwick's
    ``fopen`` fails; a missing roster file is silently skipped, as in Chadwick.
    """
    league = League()
    league.read(team_file)
    for roster in league.rosters:
        data = roster_file(f"{roster.team_id}{year}.ROS")
        if data is None:
            continue
        roster.read(data)
    return league


_SSCANF_DATE = re.compile(r"\s*([+-]?\d+)/\s*([+-]?\d+)/\s*([+-]?\d+)")


def game_in_range(game: Game, first: str, last: str) -> bool:
    """``cwtools_game_in_range``: is the game's month and day between ``first`` and ``last``"""
    date = game.info_lookup("date")
    if date is None:
        raise ValueError(f"game {game.game_id} has no date (Chadwick would crash)")
    found = _SSCANF_DATE.match(date)
    if found is None:
        raise ValueError(f"unreadable date {date!r} in {game.game_id} (undefined in Chadwick)")
    month, day = int(found.group(2)), int(found.group(3))
    date_string = f"{month:02d}{day:02d}"
    return first <= date_string <= last


def select_game(game: Game, game_id: str = "", first: str = "0101", last: str = "1231") -> bool:
    """``cwtools_select_game``"""
    return (game_id == "" or game_id == game.game_id) and game_in_range(game, first, last)


def iterate_games(
    data: bytes,
    league: League | None = None,
    game_id: str = "",
    first: str = "0101",
    last: str = "1231",
) -> Iterator[tuple[Game, Roster | None, Roster | None]]:
    """``cwtools_process_scorebook`` + ``cwtools_iterate_games``: the selected games of one event
    file with the visiting and home rosters (``None`` where the team is not in the team file).

    An empty file yields nothing (Chadwick prints "could not open file").
    """
    games = scorebook_read(data)
    if games is None:
        return
    league = league if league is not None else League()
    for game in games:
        if select_game(game, game_id, first, last):
            yield (
                game,
                league.roster_find(game.info_lookup("visteam")),
                league.roster_find(game.info_lookup("hometeam")),
            )
