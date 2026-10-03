"""Dump the boxscores the port builds for an event file, in the format of ``box_dump.c``."""

import dataclasses
from collections.abc import Iterator
from typing import Any

from retrosheetpy.cw.box import BoxEvent, BoxPlayer, Boxscore, box_create
from retrosheetpy.cw.game import read_games


def s(p: str | None) -> str:
    if p is None:
        return "~"
    return "".join(
        f"\\x{ord(c):02x}" if ord(c) < 32 or ord(c) > 126 or c in "\\|" else c for c in p
    )


def nums(obj: Any) -> str:
    return "".join(f"{getattr(obj, f.name)} " for f in dataclasses.fields(obj))


def player(p: BoxPlayer) -> list[str]:
    pos = "".join(f"{x}," for x in p.positions[: min(p.num_positions, 40)])
    out = [
        f"player {s(p.player_id)}|{s(p.name)}|{s(p.date)}|ph={p.ph_inn} pr={p.pr_inn} "
        f"np={p.num_positions} sp={p.start_position} pos={pos}",
        " bat " + nums(p.batting),
    ]
    out += [" fld " + ("~" if f is None else nums(f)) for f in p.fielding]
    return out


def evlist(kind: str, events: list[BoxEvent]) -> list[str]:
    out = []
    for e in events:
        players = (e.players + [None] * 20)[:20]
        out.append(
            f"{kind} in={e.inning} h={e.half_inning} r={e.runners} po={e.pickoff} o={e.outs} "
            f"m={e.mark} loc={s(e.location)} pl=" + "".join(s(x) + "," for x in players)
        )
    return out


def box(b: Boxscore) -> list[str]:
    out: list[str] = []
    for t in (0, 1):
        for i in range(10):
            p = b.slots[i][t]
            if p is None:
                continue
            while p.prev is not None:
                p = p.prev
            out.append(f"slot {i} {t}")
            node: BoxPlayer | None = p
            while node is not None:
                out += player(node)
                node = node.next
        q = b.pitchers[t]
        if q is not None:
            while q.prev is not None:
                q = q.prev
            pit: Any = q
            while pit is not None:
                out.append(f"pitcher {t} {s(pit.player_id)}|{s(pit.name)}")
                out.append(" pit " + nums(pit.pitching))
                pit = pit.next
        rows = (b.linescore + [[-1, -1]] * 50)[:50]
        out.append(f"line {t}:" + "".join(f"{r[t]}," for r in rows))
        out.append(
            f"tot {t} score={b.score[t]} hits={b.hits[t]} err={b.errors[t]} dp={b.dp[t]} "
            f"tp={b.tp[t]} lob={b.lob[t]} er={b.er[t]} ra={b.risp_ab[t]} rh={b.risp_h[t]}"
        )
    out.append(f"end outs={b.outs_at_end} walkoff={b.walk_off}")
    for kind, lst in (
        ("b2", b.b2_list), ("b3", b.b3_list), ("hr", b.hr_list), ("sb", b.sb_list),
        ("cs", b.cs_list), ("po", b.po_list), ("sh", b.sh_list), ("sf", b.sf_list),
        ("hp", b.hp_list), ("ibb", b.ibb_list), ("wp", b.wp_list), ("bk", b.bk_list),
        ("err", b.err_list), ("pb", b.pb_list), ("dp", b.dp_list), ("tp", b.tp_list),
    ):  # fmt: skip
        out += evlist(kind, lst)
    return out


def dump(data: bytes) -> tuple[list[str], bool]:
    """Lines for every game, and whether the port raised (Chadwick exits or crashes there)."""
    lines: list[str] = []
    try:
        for game in read_games(data):
            lines.append(f"BOX {s(game.game_id)}")
            lines += box(box_create(game))
    except (ValueError, AssertionError, IndexError, KeyError, TypeError, AttributeError):
        return lines, True
    return lines, False


def games(data: bytes) -> Iterator[str]:
    yield from dump(data)[0]
