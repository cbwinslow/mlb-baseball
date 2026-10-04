"""Port of the writing functions of Chadwick's ``game.c``, ``book.c``, ``roster.c``, ``league.c``.

Chadwick is Copyright (c) 2002-2023 Dr T L Turocy and the Chadwick Baseball
Bureau, licensed GPL-2.0-or-later; this module is a derivative of it and keeps
that notice. Each function returns the text the C writes to its ``FILE *``
(encode it as ``latin-1``; text is held one byte per character, as in C).

``%s`` of a NULL pointer prints ``(null)`` as glibc does. Where the C would
dereference NULL (``strstr`` of missing info data) a ``ValueError`` is raised.
Like the C, ``cw_game_write`` does not write the ``evdata`` records.
"""

from retrosheetpy.cw.book import Scorebook
from retrosheetpy.cw.game import Game
from retrosheetpy.cw.roster import League, Roster

# info labels always written with quotes, "to be output-compatible with existing tools"
_QUOTED_INFO = frozenset(
    (
        "inputprogvers",
        "umphome",
        "ump1b",
        "ump2b",
        "ump3b",
        "umplf",
        "umprf",
        "scorer",
        "translator",
        "inputter",
    )
)


def _s(value: str | None) -> str:
    """``%s``"""
    return "(null)" if value is None else value


def game_write_header(game: Game) -> str:
    """``cw_game_write_header``"""
    out = [f"id,{_s(game.game_id)}\n", f"version,{_s(game.version)}\n"]
    for label, data in game.info:
        if data is None:
            raise ValueError("info record without data (Chadwick would crash)")
        if "," in data or label in _QUOTED_INFO:
            out.append(f'info,{label},"{data}"\n')
        else:
            out.append(f"info,{label},{data}\n")
    return "".join(out)


def game_write_starters(game: Game) -> str:
    """``cw_game_write_starters``"""
    return "".join(
        f'start,{_s(s.player_id)},"{_s(s.name)}",{s.team},{s.slot},{s.pos}\n' for s in game.starters
    )


def game_write_comments(game: Game) -> str:
    """``cw_game_write_comments``"""
    return "".join(f'com,"{_s(c.text)}"\n' for c in game.comments)


def game_write_events(game: Game) -> str:
    """``cw_game_write_events``"""
    out: list[str] = []
    for event in game.events:
        if event.batter_hand != " ":
            out.append(f"badj,{_s(event.batter)},{event.batter_hand}\n")
        if event.pitcher_hand != " ":
            out.append(f"padj,{_s(event.pitcher_hand_id)},{event.pitcher_hand}\n")
        if event.ladj_slot != 0:
            out.append(f"ladj,{event.ladj_align},{event.ladj_slot}\n")
        if event.auto_base != 0:
            out.append(f"radj,{_s(event.auto_runner_id)},{event.auto_base}\n")
        out.append(
            f"play,{event.inning},{event.batting_team},{_s(event.batter)},"
            f"{_s(event.count)},{_s(event.pitches)},{_s(event.event_text)}\n"
        )
        for sub in event.subs:
            out.append(
                f'sub,{_s(sub.player_id)},"{_s(sub.name)}",{sub.team},{sub.slot},{sub.pos}\n'
            )
        for comment in event.comments:
            out.append(f'com,"{_s(comment.text)}"\n')
    return "".join(out)


def _write_records(kind: str, records: list[tuple[str | None, ...]]) -> str:
    return "".join(kind + "".join(f",{_s(item)}" for item in rec) + "\n" for rec in records)


def game_write(game: Game) -> str:
    """``cw_game_write``"""
    return (
        game_write_header(game)
        + game_write_starters(game)
        + game_write_comments(game)
        + game_write_events(game)
        + _write_records("stat", game.stat)
        + _write_records("line", game.line)
        + _write_records("data", game.data)
    )


def scorebook_write(book: Scorebook) -> str:
    """``cw_scorebook_write``: the book's leading comments, then every game"""
    return "".join(f'com,"{c}"\n' for c in book.comments) + "".join(
        game_write(g) for g in book.games
    )


def roster_write(roster: Roster) -> str:
    """``cw_roster_write``"""
    return "".join(
        f'"{p.player_id}","{p.last_name}","{p.first_name}",{p.bats},{p.throws}\n'
        for p in roster.players
    )


def league_write(league: League) -> str:
    """``cw_league_write``"""
    return "".join(f"{r.team_id},{r.league},{r.city},{r.nickname}\n" for r in league.rosters)
