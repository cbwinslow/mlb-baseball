"""Migration 0118 retypes the register tables to the declared schema (typed-raw-layer 1.2)."""

from pathlib import Path

from mlb_baseball.ingest_layer import schemas

MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "0118_typed_register.sql"


def _types(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'raw' AND table_name LIKE 'register\\_%%'"
        )
        out = {(t, c): d for t, c, d in cur.fetchall()}
    db_conn.rollback()
    return out


def test_register_columns_match_the_declared_schema(db_conn):
    have = _types(db_conn)
    for table, spec in schemas.load("register").items():
        rel = table.split(".")[1]
        for column in spec.columns:
            want = "integer" if column.kind == "integer" else "text"
            assert have[(rel, column.name)] == want, (rel, column.name)


def test_the_migration_is_safe_to_run_again(db_conn):
    before = _types(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(MIGRATION.read_text())
    db_conn.commit()
    assert _types(db_conn) == before


def test_typed_columns_keep_values_and_empty_is_null(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.register_people (key_person, key_mlbam, birth_year) "
            "VALUES ('t1', 660271, 1994), ('t2', NULL, NULL)"
        )
        cur.execute("SELECT key_mlbam, birth_year FROM raw.register_people ORDER BY key_person")
        assert cur.fetchall() == [(660271, 1994), (None, None)]
    db_conn.rollback()
