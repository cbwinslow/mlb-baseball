#!/usr/bin/env python3
"""Load a bounded, read-only source sample into mlb_test for conformance."""

import os

from mlb_baseball.rehearsal import clear_sample, load_sample


def main() -> None:
    source_url = os.environ.get("SOURCE_DATABASE_URL")
    target_url = os.environ.get("TEST_DATABASE_URL")
    if not target_url:
        raise SystemExit("set TEST_DATABASE_URL")
    if os.environ.get("CLEAR_REHEARSAL_SAMPLE") == "1":
        clear_sample(target_url)
        print("cleared bounded rehearsal sample")
        return
    if not source_url:
        raise SystemExit("set SOURCE_DATABASE_URL")
    result = load_sample(source_url, target_url)
    for relation, count in result.rows.items():
        print(f"{relation}: {count:,} rows")


if __name__ == "__main__":
    main()
