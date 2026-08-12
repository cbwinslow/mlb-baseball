"""Build the first audited, point-in-time-safe MLB game feature family.

Completed games come from ``core.game``; scheduled games come from the latest
``raw.mlb_schedule`` observation. Every output has an MLB provider key and a
parseable schedule start time, retained as its explicit feature cutoff. Raw
schedule history remains untouched, but cannot fan out the gold relation.
"""

import psycopg

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.model.identity import sync_feature_instances
from mlb_baseball.sql import read_sql


def build(conn: psycopg.Connection, *, strict: bool = False) -> int:
    """Rebuild features in the caller's transaction.

    ``strict=True`` is the public first-family contract used by ``mlb
    features``. The compatibility path stays available for isolated legacy
    enrichment tests with deliberately tiny core-only fixtures.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        (schedule_exists,) = fetch_one(cur)
        if strict and not schedule_exists:
            raise RuntimeError(
                "gold.game_feature requires raw.mlb_schedule with MLB game keys and start times; "
                "run `mlb ingest mlb_api --mode bootstrap` first"
            )
        cur.execute("TRUNCATE gold.game_feature")
        if strict:
            cur.execute(read_sql("game_feature_rebuild.sql"))
        elif schedule_exists:
            cur.execute(read_sql("game_feature_legacy_schedule_rebuild.sql"))
        else:
            cur.execute(read_sql("game_feature_legacy_rebuild.sql"))
        count = cur.rowcount
    sync_feature_instances(conn)
    return count


def health_check() -> list[Check]:
    return [check_table_has_rows("gold.game_feature")]
