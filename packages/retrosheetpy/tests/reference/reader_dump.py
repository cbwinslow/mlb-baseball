"""Dump what ``cw_game_read`` produced from an event file, in the format of ``reader_dump.c``.

Used to compare the port's reader with Chadwick's own: the C harness prints the same
text from the real ``CWGame`` structures, and the two outputs must be identical.
"""

import sys
from pathlib import Path

from retrosheetpy.cw.game import Appearance, Comment, Game, read_games


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
    out: list[str] = []
    for g in read_games(data):
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


if __name__ == "__main__":
    for line in dump(Path(sys.argv[1]).read_bytes()):
        print(line)
