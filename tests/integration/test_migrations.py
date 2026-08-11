"""Regression coverage for migration-driven database schema shape.

No test previously asserted the actual schema migration 0011 produces (only
the data conform.py builds on top of it) -- found reviewing this session's
commit range. mlb_test already has migration 0011 applied (see
tests/conftest.py's session-scoped migrate.run()), so these assert against
the real, already-migrated schema rather than re-running the migration.
"""

from pathlib import Path

from mlb_baseball.db import get_connection


def test_schedule_season_index_migration_removes_only_an_exact_duplicate(db_conn):
    try:
        with db_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
            cur.execute("CREATE TABLE raw.mlb_schedule (_season text, game_id text)")
            cur.execute("CREATE INDEX mlb_schedule__season_idx ON raw.mlb_schedule (_season)")
            cur.execute("CREATE INDEX mlb_schedule_season_idx ON raw.mlb_schedule (_season)")
            cur.execute(Path("migrations/0042_drop_duplicate_schedule_season_index.sql").read_text())
            cur.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'raw' "
                "AND tablename = 'mlb_schedule' ORDER BY indexname"
            )
            assert cur.fetchall() == [('mlb_schedule__season_idx',)]
        db_conn.commit()
    finally:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        db_conn.commit()


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


def test_prediction_primary_key_uses_durable_game_instance_identity():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
            "WHERE c.conrelid = 'gold.prediction'::regclass AND c.contype = 'p' "
            "ORDER BY k.ord"
        )
        assert [row[0] for row in cur.fetchall()] == [
            "game_instance_key",
            "model_version",
            "generated_at",
        ]


def test_game_instance_registry_exists_outside_rebuilt_feature_table():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('meta.game_instance')")
        assert cur.fetchone() == ("meta.game_instance",)


def test_core_game_mlb_key_has_a_partial_unique_index():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = 'core' AND indexname = 'core_game_game_pk_key'"
        )
        indexdef = cur.fetchone()[0]
    assert "UNIQUE INDEX core_game_game_pk_key" in indexdef
    assert "WHERE (game_pk IS NOT NULL)" in indexdef


def test_core_pitch_retains_the_statcast_source_game_key():
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'core' AND table_name = 'pitch' "
            "AND column_name = 'source_game_pk'"
        )
        assert cur.fetchone() == ("YES",)
