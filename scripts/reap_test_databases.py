#!/usr/bin/env python3
"""Drop orphaned per-run test databases left behind by a crashed pytest
process. Safe to run any time, including while other test sessions are
active -- see mlb_baseball/reap_test_databases.py for why.

Usage:
    TEST_DATABASE_URL=postgresql:///mlb_test uv run python scripts/reap_test_databases.py
"""

import argparse
import os

import psycopg

from mlb_baseball.reap_test_databases import (
    find_orphaned_test_databases,
    reap_orphaned_test_databases,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Drop orphaned per-run test databases left behind by a crashed pytest process."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually drop the orphaned databases (default is dry-run mode).",
    )
    args = parser.parse_args()

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit("set TEST_DATABASE_URL (used for host/port/user connection coordinates)")

    if args.apply:
        dropped = reap_orphaned_test_databases(url)
        if dropped:
            print(f"dropped {len(dropped)} orphaned test database(s): {', '.join(dropped)}")
        else:
            print("no orphaned test databases found")
    else:
        with psycopg.connect(url, autocommit=True) as conn:
            with conn.cursor() as cur:
                candidates = find_orphaned_test_databases(cur)
        if candidates:
            cand_str = ", ".join(candidates)
            print(
                f"dry-run: found {len(candidates)} orphaned test database candidate(s) "
                f"(pass --apply to drop): {cand_str}"
            )
        else:
            print("dry-run: no orphaned test database candidates found")


if __name__ == "__main__":
    main()
