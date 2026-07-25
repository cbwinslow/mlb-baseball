from mlb_baseball import migrate


def test_rerunning_migrate_applies_nothing_new():
    # The session fixture already applied every migration once.
    applied = migrate.run()
    assert applied == []


def test_every_migration_file_is_recorded_as_applied(db_conn):
    expected = {path.name for path in migrate.MIGRATIONS_DIR.glob("*.sql")}
    with db_conn.cursor() as cur:
        cur.execute("SELECT version FROM public.schema_migrations")
        recorded = {row[0] for row in cur.fetchall()}
    assert expected <= recorded


def test_expected_schemas_exist(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname IN ('raw', 'conformed', 'meta')"
        )
        schemas = {row[0] for row in cur.fetchall()}
    assert schemas == {"raw", "conformed", "meta"}
