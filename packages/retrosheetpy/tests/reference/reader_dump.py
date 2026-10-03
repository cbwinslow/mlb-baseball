"""Dump what ``cw_game_read`` produced from an event file, in the format of ``reader_dump.c``.

Used to compare the port's reader with Chadwick's own: the C harness prints the same
text from the real ``CWGame`` structures, and the two outputs must be identical.
"""

import sys
from collections.abc import Iterable
from pathlib import Path

from retrosheetpy.cw.book import scorebook_read
from retrosheetpy.cw.game import Appearance, Comment, Game, read_games
from retrosheetpy.cw.roster import League, Roster, roster_batting_hand, roster_throwing_hand


def s(p: str | None) -> str:
    if p is None:
        return "~"
    return "".join(
        f"\\x{ord(c):02x}" if ord(c) < 32 or ord(c) > 126 or c in "\\|" else c for c in p
    )


def f(label: str, p: str | None) -> str:
    return f"{label}={s(p)}|"


def app(kind: str, apps: list[Appearance]) -> list[str]:
    return [
        f"{kind} " + f("id", a.player_id) + f("n", a.name) + f"t={a.team}|s={a.slot}|p={a.pos}"
        for a in apps
    ]


def com(comments: list[Comment]) -> list[str]:
    out = []
    for c in comments:
        e = c.ejection or (None,) * 4
        u = c.umpchange or (None,) * 3
        out.append(
            "com "
            + f("t", c.text)
            + "".join(f(f"e{i}", v) for i, v in enumerate(e))
            + "".join(f(f"u{i}", v) for i, v in enumerate(u))
        )
    return out


def dat(kind: str, rows: list[tuple[str | None, ...]]) -> list[str]:
    return [f"{kind} n={len(r)} " + "".join(s(x) + "," for x in r) for r in rows]


def dump(data: bytes) -> list[str]:
    """``cw_game_read`` called until it returns NULL"""
    return _games(read_games(data))


def dump_book(data: bytes) -> list[str]:
    """``cw_scorebook_read``"""
    games = scorebook_read(data)
    if games is None:
        return ["read=-1"]
    return [f"read={len(games)}", *_games(games)]


def dump_roster(data: bytes) -> list[str]:
    roster = Roster("T", "L", "C", "N")
    roster.read(data)
    return [
        "player "
        + f("id", p.player_id)
        + f("l", p.last_name)
        + f("f", p.first_name)
        + f"b={ord(p.bats)}|t={ord(p.throws)}|"
        + f"bh={ord(roster_batting_hand(roster, p.player_id))}|"
        + f"th={ord(roster_throwing_hand(roster, p.player_id))}"
        for p in roster.players
    ]


def dump_league(data: bytes) -> list[str]:
    league = League()
    league.read(data)
    return [
        "team " + f("id", r.team_id) + f("lg", r.league) + f("c", r.city) + f("n", r.nickname)
        for r in league.rosters
    ]


def _games(games: Iterable[Game]) -> list[str]:
    out: list[str] = []
    for g in games:
        out.append("GAME " + f("id", g.game_id) + f("v", g.version))
        out += [f"info {f('l', k)}{f('d', v)}" for k, v in g.info]
        out += app("start", g.starters) + com(g.comments)
        out += dat("data", g.data) + dat("stat", g.stat) + dat("evdata", g.evdata)
        out += dat("line", g.line)
        out += _events(g)
    return out


def _events(g: Game) -> list[str]:
    out = []
    for e in g.events:
        out.append(
            f"ev {e.inning} {e.batting_team} "
            + f("b", e.batter)
            + f("c", e.count)
            + f("p", e.pitches)
            + f("e", e.event_text)
            + f"bh={ord(e.batter_hand)}|ph={ord(e.pitcher_hand)}|"
            + f("phid", e.pitcher_hand_id)
            + f"la={e.ladj_align}|ls={e.ladj_slot}|ab={e.auto_base}|"
            + f("ar", e.auto_runner_id)
            + "".join(f("pa", p) for p in e.presadj)
        )
        out += app("sub", e.subs) + com(e.comments)
    return out


MODES = {"game": dump, "book": dump_book, "roster": dump_roster, "league": dump_league}

if __name__ == "__main__":
    mode = sys.argv[2] if len(sys.argv) > 2 else "game"
    for line in MODES[mode](Path(sys.argv[1]).read_bytes()):
        print(line)
