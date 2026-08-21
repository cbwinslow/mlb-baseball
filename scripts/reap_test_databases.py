#!/usr/bin/env python3
"""Drop orphaned per-run test databases left behind by a crashed pytest
process. Safe to run any time, including while other test sessions are
active -- see mlb_baseball/reap_test_databases.py for why.

Usage:
    TEST_DATABASE_URL=postgresql:///mlb_test uv run python scripts/reap_test_databases.py
"""

import os

from mlb_baseball.reap_test_databases import reap_orphaned_test_databases


def main() -> None:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit("set TEST_DATABASE_URL (used only for host/port/user, not the dbname)")
    dropped = reap_orphaned_test_databases(url)
    if dropped:
        print(f"dropped {len(dropped)} orphaned test database(s): {', '.join(dropped)}")
    else:
        print("no orphaned test databases found")


if __name__ == "__main__":
    main()
