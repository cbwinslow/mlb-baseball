#!/usr/bin/env python3
"""Retrosheet tie-out gate: do the redundant Retrosheet sources agree with each
other, and is ``core`` faithful to raw?

Spec: ``openspec/changes/raw-source-tieout/`` (pass marks and the register are in
``passmarks.md``). Thin entry point: the logic is in ``mlb_baseball.tieout`` and
``mlb_baseball.tieout_run`` (scripts/AGENTS.md).

**Read-only.** It never writes to ``raw``, ``core`` or ``gold``; the connection is
opened read-only and refuses to run unless the connected database is the one
named with ``--expect-db``. Differences it finds are reported, never repaired.

Example (production, read-only):

    set -a && . ./.env && set +a
    uv run python scripts/verify_retrosheet_tie_out.py --expect-db mlb --from 2015 --to 2025

Exit status: 0 passed, 1 the gate failed, 2 it could not run (wrong database,
bad arguments, query error).
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from mlb_baseball import tieout_run

DEFAULT_TIMEOUT_MINUTES = 15


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--expect-db",
        required=True,
        help="name of the database you mean to read; the run is refused if it differs",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="connection URL (default: the DATABASE_URL environment variable)",
    )
    parser.add_argument("--from", dest="lo", type=int, default=tieout_run.FIRST_SEASON)
    parser.add_argument("--to", dest="hi", type=int, default=tieout_run.LAST_SEASON)
    parser.add_argument(
        "--levels",
        default="season",
        help="comma-separated: season, game, player_game, core, schema (default: season)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="verify the target is read-only and is the expected database, then stop",
    )
    parser.add_argument(
        "--show-all",
        action="store_true",
        help="print every difference instead of the first 15 per comparison",
    )
    parser.add_argument(
        "--statement-timeout-minutes",
        type=int,
        default=DEFAULT_TIMEOUT_MINUTES,
        help="per-query limit; the CSV play-by-play table is large",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    url = args.database_url or os.environ.get("DATABASE_URL") or ""
    started = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"Retrosheet tie-out, started {started}")
    return tieout_run.execute(
        url=url,
        expect_db=args.expect_db,
        lo=args.lo,
        hi=args.hi,
        levels=[level.strip() for level in args.levels.split(",") if level.strip()],
        dry_run=args.dry_run,
        statement_timeout_ms=args.statement_timeout_minutes * 60_000,
        show_all=args.show_all,
    )


if __name__ == "__main__":
    raise SystemExit(main())
