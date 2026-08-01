"""Regression coverage for migration 0011's partitioning schema shape.

No test previously asserted the actual schema migration 0011 produces (only
the data conform.py builds on top of it) -- found reviewing this session's
commit range. mlb_test already has migration 0011 applied (see
tests/conftest.py's session-scoped migrate.run()), so these assert against
the real, already-migrated schema rather than re-running the migration.
"""

from mlb_baseball.db import get_connection


def test_play_and_pitch_are_partitioned_tables():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT c.relname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'core' AND c.relname IN ('play', 'pitch') "
            "AND c.relkind = 'p'"
        )
        partitioned = {row[0] for row in cur.fetchall()}
    assert partitioned == {"play", "pitch"}


def test_play_and_pitch_constraints_use_final_names():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT conrelid::regclass::text, conname FROM pg_constraint "
            "WHERE conrelid IN ('core.play'::regclass, 'core.pitch'::regclass) "
            "AND contype IN ('p', 'u')"
        )
        constraints = {(table, name) for table, name in cur.fetchall()}
    assert ("core.play", "play_pkey") in constraints
    assert ("core.play", "play_game_id_source_play_index_key") in constraints
    assert ("core.pitch", "pitch_pkey") in constraints


def test_dead_play_pitch_tables_are_dropped():
    # Migration 0011 kept core.play_old/core.pitch_old as a safety net;
    # migration 0023 dropped them for good (6.2GB of dead tables). This
    # replaces the pre-0023 version of the test, which asserted the tables
    # still existed — stale from the moment 0023 landed, and unnoticed
    # because nothing ran the suite automatically.
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'core' AND tablename IN ('play_old', 'pitch_old')"
        )
        assert cur.fetchall() == []
