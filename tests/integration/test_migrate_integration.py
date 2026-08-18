import pytest

from mlb_baseball import migrate


def test_rerunning_migrate_applies_nothing_new():
    # The session fixture already applied every migration once.
    applied = migrate.run()
    assert applied == []


def test_skip_with_unknown_filename_raises_instead_of_silently_no_opping():
    # A typo in --skip must not silently match nothing and let the named
    # migration apply anyway with no warning.
    with pytest.raises(ValueError, match="not_a_real_migration.sql"):
        migrate.run(skip={"not_a_real_migration.sql"})


def test_every_migration_file_is_recorded_as_applied(db_conn):
    expected = {path.name for path in migrate.MIGRATIONS_DIR.glob("*.sql")}
    with db_conn.cursor() as cur:
        cur.execute("SELECT version FROM public.schema_migrations")
        recorded = {row[0] for row in cur.fetchall()}
    assert expected <= recorded


def test_expected_schemas_exist(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname IN ('raw', 'core', 'gold', 'meta')"
        )
        schemas = {row[0] for row in cur.fetchall()}
    assert schemas == {"raw", "core", "gold", "meta"}
