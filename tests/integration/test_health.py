import uuid

import psycopg

from mlb_baseball.health import (
    check_join_coverage,
    check_last_run,
    check_no_duplicate_key,
    check_recent_run,
    check_table_exists,
    check_table_has_rows,
)


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


def test_check_last_run_reports_actionable_message_when_meta_schema_missing(monkeypatch):
    # Same class of regression as test_check_table_has_rows_false_when_table_never_created,
    # but for meta.ingestion_run specifically: a fresh, unmigrated database
    # must not crash this with UndefinedTable. Needs a genuinely separate
    # database (not mlb_test, which every other test assumes is migrated).
    db_name = f"mlb_health_freshtest_{uuid.uuid4().hex[:8]}"
    with psycopg.connect("postgresql:///postgres", autocommit=True) as admin_conn:
        with admin_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {db_name}")
        try:
            monkeypatch.setenv("DATABASE_URL", f"postgresql:///{db_name}")
            result = check_last_run("anything")
        finally:
            with admin_conn.cursor() as cur:
                cur.execute(f"DROP DATABASE {db_name}")

    assert not result.ok
    assert "mlb migrate" in result.detail


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


def test_check_recent_run_reports_actionable_message_when_meta_schema_missing(monkeypatch):
    db_name = f"mlb_health_freshtest_{uuid.uuid4().hex[:8]}"
    with psycopg.connect("postgresql:///postgres", autocommit=True) as admin_conn:
        with admin_conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE {db_name}")
        try:
            monkeypatch.setenv("DATABASE_URL", f"postgresql:///{db_name}")
            result = check_recent_run("anything", max_age_minutes=15)
        finally:
            with admin_conn.cursor() as cur:
                cur.execute(f"DROP DATABASE {db_name}")

    assert not result.ok
    assert "mlb migrate" in result.detail


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
