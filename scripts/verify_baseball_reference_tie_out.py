#!/usr/bin/env python3
"""Baseball-Reference tie-out gate for the grain-complete statistic backbone.

Spec: ``openspec/specs/statistic-backbone/spec.md`` -- "Each relation is
deterministic and validated against a published figure". Read-only against
``DATABASE_URL``: safe against production ``mlb``.

Two parts:

1. **Cited cases** -- a small set of documented player-seasons whose every
   ``expected`` value was read from the exact Baseball-Reference page named in
   the case's ``source_url`` (never typed from memory). Counting stats must
   match exactly; rate stats must match Baseball-Reference's displayed
   precision (3 decimals). The ``TieOutCase`` shape supports the game, season,
   team-season, and career grains.

2. **Bulk cross-check** -- for the seasons where ``gold.player_season``
   (Baseball-Reference lineage, via pybaseball) is trustworthy (2008-2019),
   the event-derived ``gold.batting_season`` / ``gold.pitching_season`` are
   compared against it field-by-field for every qualified player-season, and
   the gate fails if any field is outside tolerance on more than a small
   fraction of them. 2020 (COVID) and 2021+ are excluded: from 2021
   ``gold.player_season`` folds in postseason games (see the honest-limitations
   doc / ADR).

Known limits, documented, not gated: exact tie-out is not achievable at the
career grain or for seasons much before ~2000 -- Retrosheet's event record and
Baseball-Reference's official record have each absorbed decades of independent
scoring corrections.

Exits non-zero if a cited case fails or the cross-check exceeds tolerance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import psycopg

_SEASON_TABLES = {"batting_season", "pitching_season"}
_GAME_TABLES = {"batting_game", "pitching_game"}
_TEAM_TABLES = {"batting_team", "pitching_team"}
_CAREER_TABLES = {"batting_career", "pitching_career"}
_ALL_TABLES = _SEASON_TABLES | _GAME_TABLES | _TEAM_TABLES | _CAREER_TABLES


@dataclass(frozen=True)
class TieOutCase:
    description: str
    table: str  # one of _ALL_TABLES
    source_url: str
    expected: dict[str, Any]
    rate_fields: frozenset[str] = field(default_factory=frozenset)
    # Grain selectors -- set the ones this grain needs:
    retro_id: str | None = None  # player: game / season / career
    season: int | None = None  # season / team-season
    game_retro_id: str | None = None  # game grain (core.game.retro_game_id)
    team_retro_id: str | None = None  # team grain (core.team.retro_team_id)

    def __post_init__(self) -> None:
        if self.table not in _ALL_TABLES:
            raise ValueError(f"{self.description}: unknown table {self.table!r}")
        need = {
            **dict.fromkeys(_GAME_TABLES, ("game_retro_id", "retro_id")),
            **dict.fromkeys(_SEASON_TABLES, ("retro_id", "season")),
            **dict.fromkeys(_TEAM_TABLES, ("team_retro_id", "season")),
            **dict.fromkeys(_CAREER_TABLES, ("retro_id",)),
        }[self.table]
        missing = [f for f in need if getattr(self, f) is None]
        if missing:
            raise ValueError(f"{self.description}: {self.table} case needs {missing}")


# fmt: off
CASES: tuple[TieOutCase, ...] = (
    # --- Season grain --------------------------------------------------------
    TieOutCase(
        description="Aaron Judge 2022 AL MVP season (62 HR, AL single-season HR record)",
        table="batting_season", retro_id="judga001", season=2022,
        source_url="https://www.baseball-reference.com/players/j/judgeaa01.shtml",
        expected={
            "g": 157, "ab": 570, "r": 133, "h": 177, "hr": 62, "rbi": 131, "bb": 111,
            "avg": 0.311, "obp": 0.425, "slg": 0.686, "ops": 1.111,
        },
        rate_fields=frozenset({"avg", "obp", "slg", "ops"}),
    ),
    TieOutCase(
        description="Gerrit Cole 2023 AL Cy Young season (unanimous)",
        table="pitching_season", retro_id="coleg001", season=2023,
        source_url="https://www.baseball-reference.com/players/c/colege01.shtml",
        expected={
            "g": 33, "gs": 33, "bf": 821, "h": 157, "r": 64, "bb": 48, "ibb": 0,
            "so": 222, "hr": 20, "hbp": 7, "wp": 4, "bk": 1, "w": 15, "l": 4, "sv": 0,
            "ip": 209.0, "whip": 0.981,
        },
        rate_fields=frozenset({"ip", "whip"}),
    ),
    # More cited game / team / career cases can be added here as their figures
    # are read from Baseball-Reference. Broad season-grain validation is the
    # bulk cross-check below, so the cited set stays deliberately small.
)
# fmt: on


def _fetch_row(conn: psycopg.Connection, case: TieOutCase) -> dict[str, Any] | None:
    table = f"gold.{case.table}"  # noqa: S608 helpers below -- table is a checked literal
    params: dict[str, Any]
    if case.table in _GAME_TABLES:
        sql = f"""
            SELECT t.* FROM {table} t
            JOIN core.game g   ON g.id = t.game_id
            JOIN core.player p ON p.id = t.player_id
            WHERE g.retro_game_id = %(game)s AND p.retro_id = %(player)s
        """
        params = {"game": case.game_retro_id, "player": case.retro_id}
    elif case.table in _SEASON_TABLES:
        sql = f"""
            SELECT t.* FROM {table} t
            JOIN core.player p ON p.id = t.player_id
            WHERE p.retro_id = %(player)s AND t.season = %(season)s AND t.is_combined = true
        """
        params = {"player": case.retro_id, "season": case.season}
    elif case.table in _TEAM_TABLES:
        sql = f"""
            SELECT t.* FROM {table} t
            JOIN core.team ct ON ct.id = t.team_id
            WHERE ct.retro_team_id = %(team)s AND t.season = %(season)s
        """
        params = {"team": case.team_retro_id, "season": case.season}
    else:  # career
        sql = f"""
            SELECT t.* FROM {table} t
            JOIN core.player p ON p.id = t.player_id
            WHERE p.retro_id = %(player)s
        """
        params = {"player": case.retro_id}

    with conn.cursor() as cur:
        cur.execute(sql, params)
        columns = [d.name for d in cur.description or []]
        row = cur.fetchone()
    return dict(zip(columns, row, strict=True)) if row is not None else None


def _check_case(conn: psycopg.Connection, case: TieOutCase) -> list[str]:
    """Return a list of mismatch descriptions; empty means the case passed."""
    row = _fetch_row(conn, case)
    if row is None:
        return [
            f"no {case.table} row found for this case "
            "(is the backbone built against this database, and does it cover this era?)"
        ]

    if "ip" in case.expected and "outs" in row:
        row = {**row, "ip": row["outs"] / 3}

    mismatches = []
    for field_name, expected_value in case.expected.items():
        actual_value = row.get(field_name)
        if field_name in case.rate_fields:
            ok = actual_value is not None and round(float(actual_value), 3) == expected_value
        else:
            ok = actual_value == expected_value
        if not ok:
            mismatches.append(f"{field_name}: got {actual_value!r}, expected {expected_value!r}")
    return mismatches


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL (or TEST_DATABASE_URL) is required and must point at a "
            "database with the backbone gold tables already built (`mlb report`)."
        )
    return url


# Bulk cross-check: for the seasons where gold.player_season (Baseball-Reference
# lineage, via pybaseball) is trustworthy -- 2008-2019 -- the event-derived
# gold.batting_season / gold.pitching_season must agree with it within a small
# tolerance. 2020 (COVID short season) and 2021+ are EXCLUDED: from 2021 on,
# gold.player_season silently folds in postseason games (pybaseball's
# batting_stats_bref queries a Mar 1 - Nov 30 Baseball-Reference range that
# Baseball-Reference now populates with playoff game-logs). That contamination
# is tracked and fixed separately; here it would only add noise.
_XCHECK_MIN_SEASON = 2008
_XCHECK_MAX_SEASON = 2019
# tolerance per field: 0 = must match exactly. Small non-zero allowances cover
# the handful of decades-old official-scoring corrections Baseball-Reference and
# Retrosheet each absorbed independently (see the honest-limitations doc). PA/AB
# carry the widest tolerance because the two sources classify a few edge events
# (catcher interference, protested-game resolutions) differently -- +/-3 over a
# 600+ PA season is well under 0.5%.
_XCHECK_BATTING = {"pa": 3, "ab": 3, "h": 1, "hr": 0, "bb": 1, "so": 2, "r": 2, "rbi": 1}
_XCHECK_PITCHING = {"gs": 0, "w": 0, "l": 0, "sv": 0, "so": 3, "bb": 2, "h": 3, "hr": 1}
_XCHECK_MAX_FAIL_PCT = 2.0  # a field failing on >2% of player-seasons fails the gate
# qualifier per plan: batters by PA, pitchers by batters faced (they don't bat).
_XCHECK_QUALIFIER = {"batting": "ps.pa >= 300", "pitching": "t.bf >= 400"}


def _cross_check(conn: psycopg.Connection) -> list[str]:
    """Compare the event backbone against gold.player_season for the clean
    years. Return a list of failure lines (empty = passed)."""
    failures: list[str] = []
    plans = (
        ("batting", "gold.batting_season", "false", _XCHECK_BATTING),
        ("pitching", "gold.pitching_season", "true", _XCHECK_PITCHING),
    )
    for label, table, is_pitcher, tol in plans:
        checks = ", ".join(
            f"count(*) FILTER (WHERE abs(t.{f} - ps.{f}) > {t}) AS {f}_bad" for f, t in tol.items()
        )
        sql = f"""
            SELECT count(*) AS n, {checks}
            FROM {table} t
            JOIN gold.player_season ps
              ON ps.player_id = t.player_id AND ps.season = t.season
             AND ps.is_pitcher = {is_pitcher}
            WHERE t.is_combined
              AND t.season BETWEEN %(lo)s AND %(hi)s
              AND {_XCHECK_QUALIFIER[label]}
        """  # noqa: S608 -- field names come from the hardcoded tolerance dicts
        with conn.cursor() as cur:
            cur.execute(sql, {"lo": _XCHECK_MIN_SEASON, "hi": _XCHECK_MAX_SEASON})
            columns = [d.name for d in cur.description or []]
            fetched = cur.fetchone()
        assert fetched is not None  # count(*) always returns one row  # noqa: S101
        row = dict(zip(columns, fetched, strict=True))
        n = row["n"]
        print(f"  {label}: {n} player-seasons compared ({_XCHECK_MIN_SEASON}-{_XCHECK_MAX_SEASON})")
        for f in tol:
            bad = row[f"{f}_bad"]
            pct = 100.0 * bad / n if n else 0.0
            flag = "  <-- FAIL" if pct > _XCHECK_MAX_FAIL_PCT else ""
            print(f"    {f:>4}: {bad:>4} outside tolerance {tol[f]}  ({pct:.1f}%){flag}")
            if pct > _XCHECK_MAX_FAIL_PCT:
                failures.append(
                    f"{label}.{f}: {pct:.1f}% of player-seasons outside tolerance {tol[f]}"
                )
    return failures


def main() -> None:
    database_url = _database_url()
    any_failed = False

    with psycopg.connect(database_url) as conn:
        for case in CASES:
            print(f"[{case.table}] {case.description}\n    {case.source_url}")
            mismatches = _check_case(conn, case)
            if mismatches:
                any_failed = True
                print(f"  FAIL ({len(mismatches)} mismatch(es)):")
                for m in mismatches:
                    print(f"    - {m}")
            else:
                print(f"  OK -- {len(case.expected)} field(s) matched Baseball-Reference")
            print()

        print("[cross-check] event backbone vs gold.player_season, clean years")
        xfails = _cross_check(conn)
        if xfails:
            any_failed = True
            for f in xfails:
                print(f"  FAIL: {f}")
        else:
            print("  OK -- every field within tolerance on <=2% of player-seasons")
        print()

    if any_failed:
        raise SystemExit("Baseball-Reference tie-out FAILED -- see above.")
    print(f"All {len(CASES)} cited case(s) + the bulk cross-check passed.")


if __name__ == "__main__":
    main()  # raises SystemExit on failure; a clean run exits 0
