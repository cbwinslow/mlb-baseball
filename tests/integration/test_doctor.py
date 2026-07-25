"""doctor.run()'s per-check logic is tested against the real (empty but
migrated) test database. The connector-aggregation loop is tested with a
faked CONNECTORS registry — real lahman/retrosheet tables only exist in the
production database (populated by running the actual connectors, which is
not something the fast test suite should depend on)."""

from mlb_baseball import doctor
from mlb_baseball.health import Check


def test_database_reachable_is_true_against_the_test_db():
    assert doctor._database_reachable().ok


def test_required_schemas_exist_against_the_test_db():
    result = doctor._required_schemas_exist()
    assert result.ok
    assert "raw, conformed, meta" in result.detail


def test_migrations_up_to_date_against_the_test_db():
    # The session fixture in conftest.py already applied every migration.
    assert doctor._migrations_up_to_date().ok


def test_run_includes_a_fake_connectors_health_checks(monkeypatch):
    fake = type(
        "FakeConnector",
        (),
        {"health_check": staticmethod(lambda: [Check("fake thing", True, "looks fine")])},
    )
    monkeypatch.setattr(doctor, "CONNECTORS", {"fake": fake})

    checks = doctor.run()

    assert any(c.name == "fake thing" and c.ok for c in checks)


def test_run_flags_a_connector_with_no_health_check(monkeypatch):
    fake = type("FakeConnector", (), {})  # deliberately no health_check
    monkeypatch.setattr(doctor, "CONNECTORS", {"fake": fake})

    checks = doctor.run()

    match = next(c for c in checks if c.name == "fake connector")
    assert not match.ok
    assert "no health_check" in match.detail


def test_run_survives_a_connector_whose_health_check_raises(monkeypatch):
    # A never-bootstrapped connector querying a table that doesn't exist yet
    # (or any other health_check() bug) must not blind doctor to every other
    # connector's health — it should be reported as one failed check, not
    # crash the whole run.
    def _broken():
        raise RuntimeError("boom")

    broken = type("BrokenConnector", (), {"health_check": staticmethod(_broken)})
    fine = type(
        "FineConnector",
        (),
        {"health_check": staticmethod(lambda: [Check("fine thing", True, "looks fine")])},
    )
    monkeypatch.setattr(doctor, "CONNECTORS", {"broken": broken, "fine": fine})

    checks = doctor.run()

    broken_check = next(c for c in checks if c.name == "broken connector")
    assert not broken_check.ok
    assert "boom" in broken_check.detail
    assert any(c.name == "fine thing" and c.ok for c in checks)
