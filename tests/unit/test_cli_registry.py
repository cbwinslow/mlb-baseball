import pytest

from mlb_baseball.cli import CONNECTORS, main


def test_all_connectors_expose_bootstrap_and_update():
    for name, connector in CONNECTORS.items():
        assert callable(connector.bootstrap), f"{name} missing bootstrap()"
        assert callable(connector.update), f"{name} missing update()"


def test_all_connectors_expose_health_check():
    # Required by CLAUDE.md "Operational health checks" — every connector must
    # be checkable by `mlb doctor`, not invisible until something breaks.
    for name, connector in CONNECTORS.items():
        assert callable(connector.health_check), f"{name} missing health_check()"


def test_ingest_rejects_unknown_source():
    with pytest.raises(SystemExit):
        main(["ingest", "not-a-real-source"])
