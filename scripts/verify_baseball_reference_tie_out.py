#!/usr/bin/env python3
"""Baseball-Reference tie-out gate for the grain-complete statistic backbone.

openspec/project.md's NEXT milestone item: "Baseball-Reference tie-out tests
(2023 Judge / Cole)". Read-only against DATABASE_URL -- safe against
production `mlb`, matches what `mlb export`/`get_connection()` itself reads
(see scripts/verify_delivery_surface.py's own note on this).

Compares gold.batting_season / gold.pitching_season combined rows (one row
per player per season, traded stints already merged -- is_combined = true)
for known player-seasons against their official Baseball-Reference line.
Counting stats must match exactly; rate stats must match
Baseball-Reference's own displayed precision (3 decimal places) after
rounding -- this project stores full float64 precision, Baseball-Reference
displays 3 decimals, so an exact float comparison would be the wrong bar.

Reference values are cited to the exact Baseball-Reference page/table they
were read from (fetched live 2026-09-03 via the Tavily search API, not
typed from memory) -- see each case's `source_url`.

Exits non-zero (fails closed) if a case's row is missing (the backbone
hasn't been built against this database, or these players/seasons aren't
covered) or if any field doesn't match.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import psycopg


@dataclass(frozen=True)
class TieOutCase:
    description: str
    table: str  # "batting_season" or "pitching_season"
    retro_id: str
    season: int
    source_url: str
    expected: dict[str, Any]
    rate_fields: frozenset[str] = field(default_factory=frozenset)


# fmt: off
CASES: tuple[TieOutCase, ...] = (
    TieOutCase(
        description="Aaron Judge 2022 AL MVP season (62 HR, AL single-season HR record)",
        table="batting_season",
        retro_id="judga001",
        season=2022,
        source_url="https://www.baseball-reference.com/awards/awards_2022.shtml",
        expected={
            "g": 157, "ab": 570, "r": 133, "h": 177, "hr": 62, "rbi": 131, "bb": 111,
            "avg": 0.311, "obp": 0.425, "slg": 0.686, "ops": 1.111,
        },
        rate_fields=frozenset({"avg", "obp", "slg", "ops"}),
    ),
    TieOutCase(
        description="Gerrit Cole 2023 AL Cy Young season (unanimous)",
        table="pitching_season",
        retro_id="coleg001",
        season=2023,
        source_url="https://www.baseball-reference.com/awards/awards_2023.shtml",
        expected={
            "g": 33, "gs": 33, "bf": 821, "h": 157, "r": 64, "bb": 48, "ibb": 0,
            "so": 222, "hr": 20, "hbp": 7, "wp": 4, "bk": 1, "w": 15, "l": 4, "sv": 0,
            "ip": 209.0, "whip": 0.981,
        },
        rate_fields=frozenset({"ip", "whip"}),
    ),
)
# fmt: on


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit(
            "DATABASE_URL (or TEST_DATABASE_URL) is required and must point at a "
            "database with the backbone gold tables already built (`mlb report`)."
        )
    return url


def _fetch_combined_row(
    conn: psycopg.Connection, table: str, retro_id: str, season: int
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT t.*
            FROM gold.{table} t
            JOIN core.player p ON p.id = t.player_id
            WHERE p.retro_id = %s AND t.season = %s AND t.is_combined = true
            """,  # noqa: S608 -- table is one of two hardcoded literals above, not user input
            (retro_id, season),
        )
        columns = [d.name for d in cur.description or []]
        row = cur.fetchone()
    return dict(zip(columns, row, strict=True)) if row is not None else None


def _check_case(conn: psycopg.Connection, case: TieOutCase) -> list[str]:
    """Return a list of mismatch descriptions; empty means the case passed."""
    row = _fetch_combined_row(conn, case.table, case.retro_id, case.season)
    if row is None:
        return [
            f"no gold.{case.table} row found for retro_id={case.retro_id!r} "
            f"season={case.season} (is the backbone built against this database?)"
        ]

    if "ip" in case.expected:
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


def main() -> None:
    database_url = _database_url()
    any_failed = False

    with psycopg.connect(database_url) as conn:
        for case in CASES:
            print(f"{case.description} ({case.source_url})")
            mismatches = _check_case(conn, case)
            if mismatches:
                any_failed = True
                print(f"  FAIL ({len(mismatches)} mismatch(es)):")
                for m in mismatches:
                    print(f"    - {m}")
            else:
                print(f"  OK -- {len(case.expected)} field(s) matched Baseball-Reference")
            print()

    if any_failed:
        raise SystemExit("Baseball-Reference tie-out FAILED -- see mismatches above.")
    print(f"All {len(CASES)} Baseball-Reference tie-out case(s) passed.")


if __name__ == "__main__":
    sys.exit(main())
