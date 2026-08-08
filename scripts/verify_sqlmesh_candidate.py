#!/usr/bin/env python3
"""Fail-closed SQLMesh candidate parity gate for the existing test database.

This is read-only. A candidate must already have been applied to an isolated
SQLMesh environment; this gate never creates schemas, relations, or databases.
"""

import argparse
import os

import psycopg
from psycopg import sql


def _candidate_relation(value: str) -> sql.Composed:
    """Accept only a relation in the fixed Plan 02 candidate namespace."""
    try:
        schema_name, table_name = value.split(".", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("relation must be schema.table") from exc
    if schema_name not in {"core__plan02_candidate", "gold__plan02_candidate"}:
        raise argparse.ArgumentTypeError(
            "candidate relation must use core__plan02_candidate or gold__plan02_candidate"
        )
    if not table_name.isidentifier():
        raise argparse.ArgumentTypeError("candidate table name must be an identifier")
    return sql.Identifier(schema_name, table_name)


def _count(cur: psycopg.Cursor, statement: sql.Composable) -> int:
    cur.execute(statement)
    return cur.fetchone()[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venue", type=_candidate_relation, required=True)
    parser.add_argument("--feature", type=_candidate_relation, required=True)
    args = parser.parse_args()

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        raise SystemExit("TEST_DATABASE_URL is required; DATABASE_URL is deliberately ignored")
    with psycopg.connect(url) as conn:
        if conn.info.dbname != "mlb_test":
            raise SystemExit("candidate gate only permits the existing mlb_test database")
        with conn.cursor() as cur:
            venue_mismatches = _count(
                cur,
                sql.SQL(
                    """
                    SELECT count(*)
                    FROM core.venue p
                    FULL JOIN {} c USING (retro_park_id)
                    WHERE p.id IS DISTINCT FROM c.id
                    """
                ).format(args.venue),
            )
            feature_mismatches = _count(
                cur,
                sql.SQL(
                    """
                    SELECT count(*)
                    FROM (
                        SELECT
                            CASE
                                WHEN game_id IS NOT NULL THEN 'game:' || game_id::text
                                ELSE 'schedule:' || mlb_game_pk::text
                            END AS feature_key,
                            home_win IS NOT NULL AS is_completed
                        FROM gold.game_feature
                    ) p
                    FULL JOIN (
                        SELECT
                            CASE
                                WHEN game_id IS NOT NULL THEN 'game:' || game_id::text
                                ELSE 'schedule:' || mlb_game_pk::text
                            END AS feature_key,
                            is_completed
                        FROM {}
                    ) c USING (feature_key)
                    WHERE p.is_completed IS DISTINCT FROM c.is_completed
                    """
                ).format(args.feature),
            )

    if venue_mismatches or feature_mismatches:
        raise SystemExit(
            "candidate parity failed: "
            f"venue surrogate-ID mismatches={venue_mismatches}, "
            f"completed/scheduled feature mismatches={feature_mismatches}"
        )
    print("candidate parity passed: surrogate IDs and completed/scheduled rows match")


if __name__ == "__main__":
    main()
