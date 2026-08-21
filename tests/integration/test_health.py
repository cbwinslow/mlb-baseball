import uuid

from mlb_baseball.health import (
    check_grouped_no_duplicates,
    check_join_coverage,
    check_last_run,
    check_never_vacuumed,
    check_no_duplicate_key,
    check_partition_coverage,
    check_recent_run,
    check_table_exists,
    check_table_has_rows,
    check_totals_reconcile,
)

VACUUM_SCHEMA = "health_vacuum"


def _reset_never_vacuumed_schema(db_conn):
    db_conn.autocommit = False
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute(f"DROP SCHEMA IF EXISTS {VACUUM_SCHEMA} CASCADE")
    db_conn.commit()


def _table_with_dead_tuples(db_conn, name, *, dead_rows):
    table = f"{VACUUM_SCHEMA}.{name}"
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {VACUUM_SCHEMA}")
        # autovacuum_enabled=false: this fixture's whole point is dead
        # tuples with NO recorded vacuum activity -- without this, a real
        # autovacuum worker racing the test (this cluster's
        # autovacuum_vacuum_cost_limit was raised to 2000 the same night
        # this test was written) could vacuum the table before the
        # assertion runs, making the test flaky rather than wrong.
        cur.execute(f"CREATE TABLE {table} (id int) WITH (autovacuum_enabled = false)")
        cur.execute(f"INSERT INTO {table} (id) SELECT generate_series(1, %s)", (dead_rows,))
        cur.execute(f"DELETE FROM {table}")
    db_conn.commit()
    # pg_stat_user_tables is fed by each backend's own cumulative stats,
    # flushed on a timer (~1s), not synchronously at COMMIT -- without
    # forcing it, check_never_vacuumed's query (a separate connection) can
    # race the flush and see 0 dead tuples immediately after this commit.
    with db_conn.cursor() as cur:
        cur.execute("SELECT pg_stat_force_next_flush()")
    db_conn.commit()
    return table


def test_check_table_has_rows_true_when_populated(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_health_widgets")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
        cur.execute(f"INSERT INTO {table} VALUES (1)")
    db_conn.commit()

    result = check_table_has_rows(table)

    assert result.ok
    assert "1 rows" in result.detail


def test_check_table_has_rows_false_when_table_never_created():
    # A registered connector's health_check() can run before that connector
    # has ever been bootstrapped (e.g. right after a fresh clone + migrate) —
    # this must report cleanly instead of crashing with UndefinedTable, which
    # used to take down the entire `mlb doctor` run (see doctor.py's per-
    # connector try/except).
    result = check_table_has_rows("raw.test_health_never_created")

    assert not result.ok
    assert "never bootstrapped" in result.detail

    # Calling it again must still work cleanly too (no lingering bad state).
    result_again = check_table_has_rows("raw.test_health_never_created")
    assert not result_again.ok


def test_check_table_has_rows_false_when_empty(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_health_empty")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
    db_conn.commit()

    result = check_table_has_rows(table)

    assert not result.ok


def test_check_table_exists_true_when_empty(db_conn, drop_tables_after):
    # The whole point of check_table_exists vs. check_table_has_rows: 0 rows
    # is a valid healthy state for a sparse/event-driven table (e.g.
    # raw.mlb_live_game when nothing is currently live) — must not be
    # reported as unhealthy just because it happens to be empty right now.
    table = drop_tables_after("raw.test_health_sparse")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (id int)")
    db_conn.commit()

    result = check_table_exists(table)

    assert result.ok
    assert "0 rows" in result.detail


def test_check_table_exists_false_when_table_never_created():
    result = check_table_exists("raw.test_health_sparse_never_created")

    assert not result.ok
    assert "never bootstrapped" in result.detail


def test_check_last_run_false_when_never_run():
    result = check_last_run(f"test_never_{uuid.uuid4().hex}")
    assert not result.ok
    assert "never run" in result.detail


def test_check_last_run_reports_actionable_message_when_meta_schema_missing(
    monkeypatch, unmigrated_db_connection
):
    # Same class of regression as test_check_table_has_rows_false_when_table_never_created,
    # but for meta.ingestion_run specifically: a fresh, unmigrated database
    # must not crash this with UndefinedTable. Simulate that PostgreSQL error
    # in-process rather than creating another database.
    monkeypatch.setattr("mlb_baseball.health.get_connection", lambda: unmigrated_db_connection)
    result = check_last_run("anything")

    assert not result.ok
    assert "mlb migrate" in result.detail
    assert unmigrated_db_connection.rolled_back


def test_check_last_run_true_on_success(db_conn):
    source = f"test_health_run_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, finished_at) "
            "VALUES (%s, 'bootstrap', 'success', now())",
            (source,),
        )
    db_conn.commit()

    result = check_last_run(source)

    assert result.ok


def test_check_recent_run_false_when_never_run():
    result = check_recent_run(f"test_never_{uuid.uuid4().hex}", max_age_minutes=15)
    assert not result.ok
    assert "never run" in result.detail


def test_check_recent_run_reports_actionable_message_when_meta_schema_missing(
    monkeypatch, unmigrated_db_connection
):
    monkeypatch.setattr("mlb_baseball.health.get_connection", lambda: unmigrated_db_connection)
    result = check_recent_run("anything", max_age_minutes=15)

    assert not result.ok
    assert "mlb migrate" in result.detail
    assert unmigrated_db_connection.rolled_back


def test_check_recent_run_true_when_recent_and_successful(db_conn):
    source = f"test_health_fresh_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, started_at, finished_at) "
            "VALUES (%s, 'update', 'success', now() - interval '2 minutes', now())",
            (source,),
        )
    db_conn.commit()

    result = check_recent_run(source, max_age_minutes=15)

    assert result.ok


def test_check_recent_run_false_when_last_run_is_stale(db_conn):
    # The whole point of this check over check_last_run: a scheduled job
    # that silently stopped running (crashed host, disabled crontab entry)
    # still has an old "success" row forever — that must not read as healthy.
    source = f"test_health_stale_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, started_at, finished_at) "
            "VALUES (%s, 'update', 'success', now() - interval '45 minutes', now())",
            (source,),
        )
    db_conn.commit()

    result = check_recent_run(source, max_age_minutes=15)

    assert not result.ok
    assert "still running" in result.detail


def test_check_recent_run_mode_scoping_ignores_a_recent_run_of_a_different_mode(db_conn):
    # A source whose SOURCE constant is shared across a scheduled mode
    # (e.g. kalshi/polymarket's daily "update") and an unscheduled one
    # (e.g. an owner-triggered "backfill") must not have a recent manual
    # run of the unscheduled mode mask a genuinely stale scheduled one.
    source = f"test_health_mode_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, started_at, finished_at) "
            "VALUES (%s, 'update', 'success', now() - interval '45 minutes', now())",
            (source,),
        )
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, started_at, finished_at) "
            "VALUES (%s, 'backfill', 'success', now() - interval '2 minutes', now())",
            (source,),
        )
    db_conn.commit()

    unscoped = check_recent_run(source, max_age_minutes=15)
    scoped = check_recent_run(source, max_age_minutes=15, mode="update")

    assert unscoped.ok  # would false-positive healthy without mode scoping
    assert not scoped.ok


def test_check_join_coverage_ok_on_exact_match(db_conn, drop_tables_after):
    core = drop_tables_after("raw.test_health_join_core")
    src = drop_tables_after("raw.test_health_join_src")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {core} (id int)")
        cur.execute(f"INSERT INTO {core} VALUES (1), (2)")
        cur.execute(f"CREATE TABLE {src} (id int)")
        cur.execute(f"INSERT INTO {src} VALUES (1), (2)")
    db_conn.commit()

    result = check_join_coverage(
        "test coverage", f"SELECT count(*) FROM {core}", f"SELECT count(*) FROM {src}"
    )

    assert result.ok
    assert "2 of 2 expected" in result.detail


def test_check_join_coverage_flags_any_overcount_as_fan_out(db_conn, drop_tables_after):
    # Real bug this exists to catch: a non-unique join key silently
    # duplicating rows (e.g. core.game.game_pk's doubleheader collision) —
    # any amount of over-count is a bug, not just past some tolerance.
    core = drop_tables_after("raw.test_health_join_core")
    src = drop_tables_after("raw.test_health_join_src")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {core} (id int)")
        cur.execute(f"INSERT INTO {core} VALUES (1), (2), (3)")
        cur.execute(f"CREATE TABLE {src} (id int)")
        cur.execute(f"INSERT INTO {src} VALUES (1), (2)")
    db_conn.commit()

    result = check_join_coverage(
        "test coverage", f"SELECT count(*) FROM {core}", f"SELECT count(*) FROM {src}"
    )

    assert not result.ok
    assert "fan-out" in result.detail


def test_check_join_coverage_flags_undercount_past_tolerance(db_conn, drop_tables_after):
    core = drop_tables_after("raw.test_health_join_core")
    src = drop_tables_after("raw.test_health_join_src")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {core} (id int)")
        cur.execute(f"INSERT INTO {core} VALUES (1)")
        cur.execute(f"CREATE TABLE {src} (id int)")
        cur.execute(f"INSERT INTO {src} VALUES (1), (2), (3)")
    db_conn.commit()

    result = check_join_coverage(
        "test coverage",
        f"SELECT count(*) FROM {core}",
        f"SELECT count(*) FROM {src}",
        tolerance=1,
    )

    assert not result.ok
    assert "row loss" in result.detail


def test_check_join_coverage_allows_undercount_within_tolerance(db_conn, drop_tables_after):
    core = drop_tables_after("raw.test_health_join_core")
    src = drop_tables_after("raw.test_health_join_src")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {core} (id int)")
        cur.execute(f"INSERT INTO {core} VALUES (1), (2)")
        cur.execute(f"CREATE TABLE {src} (id int)")
        cur.execute(f"INSERT INTO {src} VALUES (1), (2), (3)")
    db_conn.commit()

    result = check_join_coverage(
        "test coverage",
        f"SELECT count(*) FROM {core}",
        f"SELECT count(*) FROM {src}",
        tolerance=1,
    )

    assert result.ok


def test_check_join_coverage_false_when_source_table_missing():
    result = check_join_coverage(
        "test coverage",
        "SELECT count(*) FROM raw.test_health_join_core_never_created",
        "SELECT count(*) FROM raw.test_health_join_src_never_created",
    )

    assert not result.ok
    assert "does not exist" in result.detail


def test_check_partition_coverage_ok_when_all_partitions_meet_ratio():
    # No fixture tables needed — the sql param can be any query returning
    # (partition_key, actual, expected) rows, so a plain VALUES list is
    # enough to exercise the comparison logic directly.
    result = check_partition_coverage(
        "test coverage",
        "SELECT * FROM (VALUES ('2020', 100, 100), ('2021', 95, 100)) "
        "AS t(season, actual, expected)",
    )

    assert result.ok
    assert "2 partitions checked" in result.detail


def test_check_partition_coverage_flags_partitions_below_ratio():
    # Real bug this exists to catch: season_already_loaded only checks
    # "does at least one row exist," not "is this season actually
    # complete" — a season stuck at 10% coverage looks the same as one
    # that was never touched at all to that check, but not to this one.
    # Confirmed in production: 2022-2025 sat at literal 0/thousands.
    result = check_partition_coverage(
        "test coverage",
        "SELECT * FROM (VALUES ('2020', 100, 100), ('2021', 10, 100)) "
        "AS t(season, actual, expected)",
        min_ratio=0.5,
    )

    assert not result.ok
    assert "1 incomplete" in result.detail
    assert "2021: 10/100" in result.detail


def test_check_partition_coverage_ignores_partitions_with_zero_expected():
    # A season with 0 expected games (e.g. before the source's own
    # coverage starts) must not be flagged as "incomplete" — there was
    # never anything to load, that's not a gap.
    result = check_partition_coverage(
        "test coverage",
        "SELECT * FROM (VALUES ('1900', 0, 0), ('2021', 100, 100)) AS t(season, actual, expected)",
    )

    assert result.ok


def test_check_partition_coverage_false_when_source_table_missing():
    result = check_partition_coverage(
        "test coverage", "SELECT season, actual, expected FROM raw.test_health_never_created"
    )

    assert not result.ok
    assert "does not exist" in result.detail


def test_check_no_duplicate_key_true_when_all_unique(db_conn, drop_tables_after):
    table = drop_tables_after("raw.test_health_dupcheck")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (game_pk text)")
        cur.execute(f"INSERT INTO {table} VALUES ('100001'), ('100002'), (NULL)")
    db_conn.commit()

    result = check_no_duplicate_key(table, "game_pk")

    assert result.ok


def test_check_no_duplicate_key_false_when_a_value_repeats(db_conn, drop_tables_after):
    # Real bug this exists to catch: the doubleheader game_pk collision
    # (two core.game rows sharing one game_pk) — confirmed in production
    # before the fix, 12,662 distinct game_pk values shared by 2 rows each.
    table = drop_tables_after("raw.test_health_dupcheck")
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE TABLE {table} (game_pk text)")
        cur.execute(f"INSERT INTO {table} VALUES ('100001'), ('100001'), ('100002')")
    db_conn.commit()

    result = check_no_duplicate_key(table, "game_pk")

    assert not result.ok
    assert "1 duplicate" in result.detail


def test_check_no_duplicate_key_false_when_table_never_created():
    result = check_no_duplicate_key("raw.test_health_dupcheck_never_created", "game_pk")

    assert not result.ok
    assert "does not exist" in result.detail


def test_check_totals_reconcile_ok_within_tolerance():
    result = check_totals_reconcile(
        "test reconcile",
        "SELECT * FROM (VALUES ('ATL-2023', 100, 100), ('NYA-2023', 98, 101)) "
        "AS t(key, computed, reference)",
        tolerance=3,
    )

    assert result.ok
    assert "2 checked" in result.detail


def test_check_totals_reconcile_flags_mismatch_beyond_tolerance():
    # Real check built after finding this in production: core.game-derived
    # win totals compared against raw.lahman_teams turned up ~25 genuine
    # team-season mismatches, the largest being exactly 3 (1951/1962's
    # pennant-tiebreaker playoffs, a known, explained pattern — not a bug).
    result = check_totals_reconcile(
        "test reconcile",
        "SELECT * FROM (VALUES ('ATL-2023', 100, 100), ('NYA-2023', 90, 101)) "
        "AS t(key, computed, reference)",
        tolerance=3,
    )

    assert not result.ok
    assert "1 mismatched" in result.detail
    assert "NYA-2023: 90 vs 101" in result.detail


def test_check_totals_reconcile_symmetric_over_or_under():
    # Unlike check_join_coverage, an over-count here is just as legitimate
    # a mismatch as an under-count — two independent sources can diverge
    # in either direction (e.g. Lahman including tiebreaker games
    # core.game classifies as playoffs, not regular season).
    result = check_totals_reconcile(
        "test reconcile",
        "SELECT * FROM (VALUES ('ATL-2023', 110, 100)) AS t(key, computed, reference)",
        tolerance=3,
    )

    assert not result.ok
    assert "ATL-2023: 110 vs 100" in result.detail


def test_check_totals_reconcile_max_mismatch_rate_allows_proportional_gap():
    # starter.py's real motivating case: ~1.7% of pitcher-seasons
    # genuinely diverge (Retrosheet's own documented missing-event-file
    # rate), a gap that scales with dataset size, not a fixed small
    # count -- tolerance alone can never pass this. 1 mismatch out of 4
    # rows is 25%, which must fail at max_mismatch_rate=0.02 but pass at
    # max_mismatch_rate=0.30.
    sql = (
        "SELECT * FROM (VALUES ('A', 100, 100), ('B', 100, 100), "
        "('C', 100, 100), ('D', 50, 100)) AS t(key, computed, reference)"
    )

    too_strict = check_totals_reconcile("test reconcile", sql, tolerance=3, max_mismatch_rate=0.02)
    assert not too_strict.ok

    lenient_enough = check_totals_reconcile(
        "test reconcile", sql, tolerance=3, max_mismatch_rate=0.30
    )
    assert lenient_enough.ok
    assert "1 mismatched" in lenient_enough.detail
    assert "25.0%" in lenient_enough.detail


def test_check_totals_reconcile_max_mismatch_rate_unset_preserves_old_strict_behavior():
    # Default (no max_mismatch_rate) must be unchanged from before this
    # parameter existed -- any mismatch beyond tolerance fails, full
    # stop, correct for checks like the Lahman one where the expected
    # mismatch count doesn't grow with the dataset.
    result = check_totals_reconcile(
        "test reconcile",
        "SELECT * FROM (VALUES ('ATL-2023', 100, 100), ('NYA-2023', 90, 101)) "
        "AS t(key, computed, reference)",
        tolerance=3,
    )

    assert not result.ok


def test_check_totals_reconcile_false_when_source_table_missing():
    result = check_totals_reconcile(
        "test reconcile", "SELECT key, computed, reference FROM raw.test_health_never_created"
    )

    assert not result.ok
    assert "does not exist" in result.detail


def test_check_grouped_no_duplicates_ok_when_every_group_is_distinct():
    result = check_grouped_no_duplicates(
        "test doubleheader",
        "SELECT * FROM (VALUES ('2024-ATL-NYA', 2, 2), ('2024-BOS-TBA', 2, 2)) "
        "AS t(key, distinct_count, total_count)",
    )

    assert result.ok
    assert "2 multi-game groups checked" in result.detail


def test_check_grouped_no_duplicates_flags_a_collision():
    # Real bug this exists to catch: two different games of the same
    # doubleheader sharing one game_pk (confirmed in production before
    # migration 0011's overwrite-guard fix — game_pk 824912 ended up on
    # both MLB824912 and MLB824913's core.game rows).
    result = check_grouped_no_duplicates(
        "test doubleheader",
        "SELECT * FROM (VALUES ('2024-ATL-NYA', 1, 2)) AS t(key, distinct_count, total_count)",
    )

    assert not result.ok
    assert "1 groups with colliding identity" in result.detail
    assert "2024-ATL-NYA: 1/2" in result.detail


def test_check_grouped_no_duplicates_false_when_source_table_missing():
    result = check_grouped_no_duplicates(
        "test doubleheader",
        "SELECT key, distinct_count, total_count FROM raw.test_health_never_created",
    )

    assert not result.ok
    assert "does not exist" in result.detail


def test_check_never_vacuumed_flags_a_table_with_real_dead_tuples_and_no_vacuum_ever(db_conn):
    # The exact bug pattern found live on production (raw.mlb_win_prob,
    # raw.mlb_linescore): real, substantial dead tuples, autovacuum/manual
    # VACUUM never once run. Deliberately checked via an absolute dead-tuple
    # floor, not a percentage -- a percentage computed against
    # pg_stat_user_tables.n_live_tup would have been fooled the same way a
    # naive version of this check was during that investigation, since
    # n_live_tup is only as fresh as the table's last ANALYZE.
    _reset_never_vacuumed_schema(db_conn)
    _table_with_dead_tuples(db_conn, "bloated", dead_rows=1500)

    result = check_never_vacuumed(schemas=(VACUUM_SCHEMA,), min_dead_tuples=1000)

    assert not result.ok
    assert "bloated" in result.detail

    _reset_never_vacuumed_schema(db_conn)


def test_check_never_vacuumed_ignores_a_table_below_the_min_dead_tuples_floor(db_conn):
    _reset_never_vacuumed_schema(db_conn)
    _table_with_dead_tuples(db_conn, "small_churn", dead_rows=5)

    result = check_never_vacuumed(schemas=(VACUUM_SCHEMA,), min_dead_tuples=1000)

    assert result.ok

    _reset_never_vacuumed_schema(db_conn)


def test_check_never_vacuumed_flags_a_table_at_exactly_the_floor(db_conn):
    # The floor is inclusive (>=): a table sitting at exactly
    # min_dead_tuples is exactly as overdue as this check exists to catch,
    # not a near-miss to exclude.
    _reset_never_vacuumed_schema(db_conn)
    _table_with_dead_tuples(db_conn, "at_floor", dead_rows=1000)

    result = check_never_vacuumed(schemas=(VACUUM_SCHEMA,), min_dead_tuples=1000)

    assert not result.ok
    assert "at_floor" in result.detail

    _reset_never_vacuumed_schema(db_conn)


def test_check_never_vacuumed_ignores_a_table_that_has_already_been_vacuumed(db_conn):
    _reset_never_vacuumed_schema(db_conn)
    table = _table_with_dead_tuples(db_conn, "cleaned", dead_rows=1500)
    db_conn.autocommit = True  # VACUUM can't run inside a transaction block
    with db_conn.cursor() as cur:
        cur.execute(f"VACUUM {table}")
    db_conn.autocommit = False

    result = check_never_vacuumed(schemas=(VACUUM_SCHEMA,), min_dead_tuples=1000)

    assert result.ok

    _reset_never_vacuumed_schema(db_conn)


def test_check_never_vacuumed_ok_when_schema_has_no_qualifying_tables(db_conn):
    _reset_never_vacuumed_schema(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA {VACUUM_SCHEMA}")
        cur.execute(f"CREATE TABLE {VACUUM_SCHEMA}.untouched (id int)")
    db_conn.commit()

    result = check_never_vacuumed(schemas=(VACUUM_SCHEMA,), min_dead_tuples=1000)

    assert result.ok
    assert "no tables" in result.detail

    _reset_never_vacuumed_schema(db_conn)


def test_check_recent_run_false_when_last_run_failed_even_if_recent(db_conn):
    source = f"test_health_failed_{uuid.uuid4().hex}"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meta.ingestion_run (source, mode, status, started_at, finished_at, error) "
            "VALUES (%s, 'update', 'failed', now() - interval '1 minute', now(), 'boom')",
            (source,),
        )
    db_conn.commit()

    result = check_recent_run(source, max_age_minutes=15)

    assert not result.ok
    assert "failed" in result.detail
