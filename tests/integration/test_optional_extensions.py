"""Migration 0116 creates whichever optional extensions the server ships.
Each test skips when its package is absent (stock CI image), and otherwise
proves the extension does real work in the migrated test database."""

import pytest


def _installed(cur, name):
    cur.execute("SELECT 1 FROM pg_extension WHERE extname = %s", (name,))
    return cur.fetchone() is not None


def _scalar(db_conn, extname, sql):
    with db_conn.cursor() as cur:
        if not _installed(cur, extname):
            pytest.skip(f"{extname} not installed on this server")
        cur.execute(sql)
        return cur.fetchone()[0]


def test_fuzzystrmatch_levenshtein(db_conn):
    assert _scalar(db_conn, "fuzzystrmatch", "SELECT levenshtein('Ohtani','Otani')") == 1


def test_roaringbitmap_intersection(db_conn):
    sql = "SELECT rb_cardinality(rb_and(rb_build('{1,2,3}'), rb_build('{2,3,4}')))"
    assert _scalar(db_conn, "roaringbitmap", sql) == 2


def test_pg_uuidv7_is_version_7(db_conn):
    assert _scalar(db_conn, "pg_uuidv7", "SELECT substr(uuid_generate_v7()::text, 15, 1)") == "7"


def test_pg_similarity_jaro_winkler(db_conn):
    assert _scalar(db_conn, "pg_similarity", "SELECT jarowinkler('Judge','Judge')") == 1


def test_timescaledb_toolkit_percentile(db_conn):
    sql = "SELECT approx_percentile(0.5, percentile_agg(x)) > 0 FROM generate_series(1,100) x"
    assert _scalar(db_conn, "timescaledb_toolkit", sql) is True


def test_pg_ivm_updates_view_incrementally(db_conn):
    with db_conn.cursor() as cur:
        if not _installed(cur, "pg_ivm"):
            pytest.skip("pg_ivm not installed on this server")
        cur.execute("CREATE TABLE public._ivm_base (k int)")
        cur.execute(
            "SELECT pgivm.create_immv('_ivm_view', 'SELECT count(*) AS n FROM public._ivm_base')"
        )
        cur.execute("INSERT INTO public._ivm_base VALUES (1), (2)")
        cur.execute("SELECT n FROM _ivm_view")
        assert cur.fetchone()[0] == 2
    db_conn.rollback()


def test_pg_partman_schema(db_conn):
    sql = "SELECT count(*) > 0 FROM pg_proc WHERE pronamespace = 'partman'::regnamespace"
    assert _scalar(db_conn, "pg_partman", sql) is True


def test_migration_is_idempotent(db_conn):
    # Re-running the DO block must change nothing and must not raise.
    from pathlib import Path

    sql = Path("migrations/0116_postgres_extensions.sql").read_text()
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM pg_extension")
        before = cur.fetchone()[0]
        cur.execute(sql)
        cur.execute("SELECT count(*) FROM pg_extension")
        assert cur.fetchone()[0] == before


def test_pg_graphql_resolves_query(db_conn):
    sql = "SELECT graphql.resolve('{ __typename }')::text"
    assert "Query" in _scalar(db_conn, "pg_graphql", sql)


def test_vectorscale_provides_diskann(db_conn):
    sql = "SELECT count(*) FROM pg_am WHERE amname = 'diskann'"
    assert _scalar(db_conn, "vectorscale", sql) == 1


def test_multicorn_handler_function(db_conn):
    sql = "SELECT count(*) FROM pg_proc WHERE proname = 'multicorn_handler'"
    assert _scalar(db_conn, "multicorn", sql) == 1


def test_pg_column_tetris_installed(db_conn):
    sql = "SELECT count(*) > 0 FROM pg_proc WHERE proname = 'compute_layout'"
    assert _scalar(db_conn, "pg_column_tetris", sql) is True
