#!/usr/bin/env python3
"""Play-by-play cross-check gate for the 2026-onward MLB box-score backbone.

Spec: ``openspec/specs/statistic-backbone/spec.md`` -- "Each relation is
deterministic and validated against a published figure", the
**Play-by-play cross-check** part. This is the 2026 analogue of
``scripts/verify_baseball_reference_tie_out.py``: Baseball-Reference has no
page for the in-progress season, so an independent reconstruction from
``raw.mlb_playbyplay`` events stands in for the official published line.

Read-only against ``DATABASE_URL`` (or ``TEST_DATABASE_URL``): safe against
production ``mlb``. Runs against a fully-built database, not CI.

What it does:

1. Sample **complete** 2026 regular-season games -- games whose play-by-play
   plate-appearance count is inside an expected band, so the ~180 games with
   partial play-by-play (< 60 PA) are excluded.
2. For each sampled game, group ``raw.mlb_playbyplay`` by
   ``(game_pk, batter_id)`` and classify each ``event_type`` via the explicit
   ``EVENT_TYPE_MAP`` into PA / AB / H / BB / SO / HBP / SF / SH / HR. An
   ``event_type`` the map does not know fails LOUDLY (``UnmappedEventType``) --
   it is never silently counted as zero, so a new or renamed StatsAPI event
   trips the gate instead of undercounting.
3. Compare the reconstruction field-by-field against the
   ``mlb_boxscore``-sourced ``gold.batting_game`` rows for the same game.
4. Fail (exit non-zero) if any counting stat is outside its documented
   tolerance on more than ``MAX_FAIL_PCT`` of the sampled player-games.

Tolerance rationale: ``event_type`` maps cleanly for the common cases.
``field_error`` (AB, no H), ``fielders_choice`` / ``fielders_choice_out`` /
``force_out`` (AB), ``catcher_interf`` (PA, not AB), the empty-``event_type``
rows, and the multi-out events (``grounded_into_double_play``,
``strikeout_double_play``) are the edge cases that justify a small non-zero
tolerance rather than an exact match.
"""

from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass

import psycopg

# --- event_type -> counting-stat contribution -------------------------------
# Every value is the increment to (pa, ab, h, bb, so, hbp, sf, sh, hr) for the
# batter of that plate appearance. A plate-appearance-ending event has pa = 1.
# Events that are NOT a plate appearance for the batter (a baserunner is
# caught, a pitcher is substituted, an inning-ending advisory) map to
# NON_PA -- counted as nothing, deliberately and explicitly.

# (pa, ab, h, bb, so, hbp, sf, sh, hr)
_HIT = (1, 1, 1, 0, 0, 0, 0, 0, 0)
_HR = (1, 1, 1, 0, 0, 0, 0, 0, 1)
_K = (1, 1, 0, 0, 1, 0, 0, 0, 0)
_BB = (1, 0, 0, 1, 0, 0, 0, 0, 0)
_HBP = (1, 0, 0, 0, 0, 1, 0, 0, 0)
_SF = (1, 0, 0, 0, 0, 0, 1, 0, 0)
_SH = (1, 0, 0, 0, 0, 0, 0, 1, 0)
_OUT = (1, 1, 0, 0, 0, 0, 0, 0, 0)  # batter out / reached, an at-bat, no hit
_PA_ONLY = (1, 0, 0, 0, 0, 0, 0, 0, 0)  # catcher's interference: PA, not an AB
NON_PA = (0, 0, 0, 0, 0, 0, 0, 0, 0)

EVENT_TYPE_MAP: dict[str, tuple[int, ...]] = {
    # hits
    "single": _HIT,
    "double": _HIT,
    "triple": _HIT,
    "home_run": _HR,
    # strikeouts
    "strikeout": _K,
    "strikeout_double_play": _K,
    "strike_out": _K,
    # walks
    "walk": _BB,
    "intent_walk": _BB,
    # hit by pitch
    "hit_by_pitch": _HBP,
    # sacrifices
    "sac_fly": _SF,
    "sac_fly_double_play": _SF,
    "sac_bunt": _SH,
    "sac_bunt_double_play": _SH,
    # batter out / reached on a fielding play -- an at-bat, no hit
    "field_out": _OUT,
    "force_out": _OUT,
    "grounded_into_double_play": _OUT,
    "double_play": _OUT,
    "triple_play": _OUT,
    "fielders_choice": _OUT,
    "fielders_choice_out": _OUT,
    "field_error": _OUT,
    "other_out": _OUT,
    # PA but not an AB
    "catcher_interf": _PA_ONLY,
    "batter_interference": _PA_ONLY,
    # not a plate appearance for the batter
    "caught_stealing_2b": NON_PA,
    "caught_stealing_3b": NON_PA,
    "caught_stealing_home": NON_PA,
    "pickoff_1b": NON_PA,
    "pickoff_2b": NON_PA,
    "pickoff_3b": NON_PA,
    "pickoff_caught_stealing_2b": NON_PA,
    "pickoff_caught_stealing_3b": NON_PA,
    "pickoff_caught_stealing_home": NON_PA,
    "pickoff_error_1b": NON_PA,
    "pickoff_error_2b": NON_PA,
    "pickoff_error_3b": NON_PA,
    "stolen_base_2b": NON_PA,
    "stolen_base_3b": NON_PA,
    "stolen_base_home": NON_PA,
    "wild_pitch": NON_PA,
    "passed_ball": NON_PA,
    "balk": NON_PA,
    "defensive_indiff": NON_PA,
    "other_advance": NON_PA,
    "runner_double_play": NON_PA,
    "pitching_substitution": NON_PA,
    "offensive_substitution": NON_PA,
    "defensive_substitution": NON_PA,
    "defensive_switch": NON_PA,
    "umpire_substitution": NON_PA,
    "mound_visit": NON_PA,
    "no_pitch": NON_PA,
    "game_advisory": NON_PA,
    "batter_timeout": NON_PA,
    "ejection": NON_PA,
    "injury": NON_PA,
    "stolen_base": NON_PA,
    "caught_stealing": NON_PA,
    "pickoff": NON_PA,
    # an empty event_type is a known, small edge case (inning-ending or
    # placeholder plays) -- counted as nothing, covered by the tolerance.
    "": NON_PA,
}

FIELDS = ("pa", "ab", "h", "bb", "so", "hbp", "sf", "sh", "hr")

# per-field tolerance for one player-game; a stat outside this on more than
# MAX_FAIL_PCT of the sampled player-games fails the gate.
TOLERANCE = {"pa": 1, "ab": 1, "h": 1, "bb": 0, "so": 0, "hbp": 0, "sf": 1, "sh": 1, "hr": 0}
MAX_FAIL_PCT = 2.0

# a "complete" game: play-by-play PA count inside this band. Full 9-inning
# games run ~66-96 PA; < 60 is a partial-data game, > 110 an extra-innings
# marathon whose reconstruction is still valid but rare enough to skip for a
# clean sample.
PA_BAND = (60, 110)
SAMPLE_SIZE = 60


class UnmappedEventType(RuntimeError):
    """Raised when raw.mlb_playbyplay carries an event_type EVENT_TYPE_MAP does
    not know -- a loud failure, never a silent zero."""


def classify(event_type: str | None) -> tuple[int, ...]:
    key = event_type or ""
    try:
        return EVENT_TYPE_MAP[key]
    except KeyError as exc:
        raise UnmappedEventType(
            f"raw.mlb_playbyplay event_type {event_type!r} is not in EVENT_TYPE_MAP -- "
            "add it (with its PA/AB/H/... contribution) before this gate can pass"
        ) from exc


@dataclass
class Line:
    pa: int = 0
    ab: int = 0
    h: int = 0
    bb: int = 0
    so: int = 0
    hbp: int = 0
    sf: int = 0
    sh: int = 0
    hr: int = 0

    def add(self, contrib: tuple[int, ...]) -> None:
        self.pa += contrib[0]
        self.ab += contrib[1]
        self.h += contrib[2]
        self.bb += contrib[3]
        self.so += contrib[4]
        self.hbp += contrib[5]
        self.sf += contrib[6]
        self.sh += contrib[7]
        self.hr += contrib[8]

    def as_dict(self) -> dict[str, int]:
        return {f: getattr(self, f) for f in FIELDS}


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL (or TEST_DATABASE_URL) is required and must point at a "
            "database with the 2026 backbone built (`mlb report`)."
        )
    return url


def _sample_games(conn: psycopg.Connection) -> list[str]:
    """game_pk of 2026 regular-season games with a complete play-by-play PA
    count, capped at SAMPLE_SIZE (ordered by game_pk for determinism)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.game_pk
            FROM raw.mlb_playbyplay p
            JOIN core.game g ON g.game_pk = p.game_pk
                AND g.season = 2026 AND lower(g.game_type) = 'regular'
            WHERE p.event_type IS NOT NULL AND p.event_type <> ''
            GROUP BY p.game_pk
            HAVING count(*) FILTER (
                WHERE p.event_type <> ALL(%(non_pa)s::text[])
            ) BETWEEN %(lo)s AND %(hi)s
            ORDER BY p.game_pk
            LIMIT %(n)s
            """,
            {
                "non_pa": [k for k, v in EVENT_TYPE_MAP.items() if v == NON_PA],
                "lo": PA_BAND[0],
                "hi": PA_BAND[1],
                "n": SAMPLE_SIZE,
            },
        )
        return [r[0] for r in cur.fetchall()]


def _reconstruct(conn: psycopg.Connection, game_pks: list[str]) -> dict[tuple[str, str], Line]:
    lines: dict[tuple[str, str], Line] = defaultdict(Line)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT game_pk, batter_id, event_type FROM raw.mlb_playbyplay WHERE game_pk = ANY(%s)",
            (game_pks,),
        )
        for game_pk, batter_id, event_type in cur.fetchall():
            if not batter_id:
                continue
            lines[(game_pk, batter_id)].add(classify(event_type))
    return {k: v for k, v in lines.items() if v.pa > 0}


def _box_lines(
    conn: psycopg.Connection, game_pks: list[str]
) -> dict[tuple[str, str], dict[str, int]]:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT g.game_pk, p.mlbam_id, {", ".join("bg." + f for f in FIELDS)}
            FROM gold.batting_game bg
            JOIN core.game g ON g.id = bg.game_id
            JOIN core.player p ON p.id = bg.player_id
            WHERE bg.source = 'mlb_boxscore' AND g.game_pk = ANY(%s)
            """,  # noqa: S608 -- FIELDS is a module constant
            (game_pks,),
        )
        rows = cur.fetchall()
    return {(r[0], r[1]): dict(zip(FIELDS, r[2:], strict=True)) for r in rows}


def main() -> None:
    url = _database_url()
    with psycopg.connect(url) as conn:
        game_pks = _sample_games(conn)
        if not game_pks:
            raise SystemExit(
                "no complete 2026 play-by-play games found -- is raw.mlb_playbyplay "
                "ingested and gold.batting_game built for 2026?"
            )
        recon = _reconstruct(conn, game_pks)
        box = _box_lines(conn, game_pks)

    # The gate is symmetric: a key present in only one source is a real
    # defect (a partial play-by-play ingest, or a gold.batting_game row the
    # builder failed to write), not something to skip past.
    recon_only = sorted(set(recon) - set(box))
    box_only = sorted(set(box) - set(recon))

    compared = 0
    field_fail: dict[str, int] = dict.fromkeys(FIELDS, 0)
    worst: list[str] = []

    for key in sorted(set(recon) & set(box)):
        line = recon[key]
        box_line = box[key]
        compared += 1
        recon_d = line.as_dict()
        for f in FIELDS:
            if abs(recon_d[f] - box_line[f]) > TOLERANCE[f]:
                field_fail[f] += 1
                if len(worst) < 15:
                    worst.append(
                        f"    game {key[0]} player {key[1]} {f}: "
                        f"pbp {recon_d[f]} vs box {box_line[f]}"
                    )

    print(f"sampled {len(game_pks)} complete 2026 games")
    print(f"compared {compared} player-games (pbp reconstruction vs mlb_boxscore batting_game)")

    any_failed = False
    if recon_only:
        any_failed = True
        print(f"  <-- FAIL: {len(recon_only)} pbp-reconstructed player-games have no box-score row")
        for k in recon_only[:15]:
            print(f"      game {k[0]} player {k[1]}")
    if box_only:
        any_failed = True
        print(f"  <-- FAIL: {len(box_only)} box-score player-games have no pbp reconstruction")
        for k in box_only[:15]:
            print(f"      game {k[0]} player {k[1]}")

    for f in FIELDS:
        bad = field_fail[f]
        pct = 100.0 * bad / compared if compared else 0.0
        flag = "  <-- FAIL" if pct > MAX_FAIL_PCT else ""
        print(f"  {f:>3}: {bad:>4} outside tolerance {TOLERANCE[f]}  ({pct:.2f}%){flag}")
        if pct > MAX_FAIL_PCT:
            any_failed = True

    if worst:
        print("  sample mismatches:")
        print("\n".join(worst))

    if compared == 0:
        raise SystemExit("no player-games could be compared -- gate cannot pass")
    if any_failed:
        raise SystemExit("MLB box-score play-by-play tie-out FAILED -- see above.")
    print(f"OK -- every counting stat within tolerance on <= {MAX_FAIL_PCT}% of player-games.")


if __name__ == "__main__":
    main()  # raises SystemExit on failure; a clean run exits 0
