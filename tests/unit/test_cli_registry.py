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


def test_mlb_api_analytics_stage_passes_bounded_operator_options(monkeypatch):
    received = {}

    def staged(**kwargs):
        received.update(kwargs)
        return {"raw.mlb_win_prob": 1}

    monkeypatch.setattr(CONNECTORS["mlb_api"], "backfill_analytics", staged)

    main(
        [
            "ingest",
            "mlb_api",
            "--stage",
            "analytics",
            "--start-year",
            "1967",
            "--end-year",
            "1968",
            "--workers",
            "8",
        ]
    )

    assert received == {"start_year": 1967, "end_year": 1968, "workers": 8}
