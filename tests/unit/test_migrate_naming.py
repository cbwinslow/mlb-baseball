from mlb_baseball.migrate import MIGRATIONS_DIR


def test_migration_files_are_sequentially_named():
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    assert files, "expected at least one migration file"
    for path in files:
        assert path.name[:4].isdigit(), f"{path.name} should start with a 4-digit sequence number"
