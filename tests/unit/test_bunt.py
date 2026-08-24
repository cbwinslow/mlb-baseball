"""Unit tests for Infield Bunt Defense Engine (BUNT-01, ADR-185)."""

from mlb_baseball.model.bunt import (
    InfieldBuntDefenseEngine,
    InfieldBuntDefenseMetrics,
    health_check,
)


def test_elite_third_baseman_classified_as_bunt_eraser():
    """Verify high lead runner outs and bunt popups yield ELITE_BUNT_ERASER."""
    engine = InfieldBuntDefenseEngine()

    arenado = InfieldBuntDefenseMetrics(
        fielder_id="f1",
        fielder_name="Nolan Arenado Archetype",
        position="3B",
        lead_runner_outs=4,
        batter_outs_at_first=14,
        bunt_popups_caught=3,
        bunt_hits_allowed=0,
        total_bunt_attempts=21,
    )

    res = engine.evaluate_bunt_defense(arenado)

    assert res.total_bunt_runs_saved > 2.0
    assert res.lead_runner_kill_pct > 15.0
    assert res.defense_tier == "ELITE_BUNT_ERASER"
    assert res.is_elite_bunt_defender is True


def test_slow_first_baseman_triggers_liability_tier():
    """Verify multiple bunt hits allowed yields SHORT_GAME_LIABILITY."""
    engine = InfieldBuntDefenseEngine()

    slow_1b = InfieldBuntDefenseMetrics(
        fielder_id="f2",
        fielder_name="Slow 1B",
        position="1B",
        lead_runner_outs=0,
        batter_outs_at_first=8,
        bunt_popups_caught=0,
        bunt_hits_allowed=4,
        total_bunt_attempts=12,
    )

    res = engine.evaluate_bunt_defense(slow_1b)

    assert res.total_bunt_runs_saved < -1.0
    assert res.defense_tier == "SHORT_GAME_LIABILITY"
    assert res.is_elite_bunt_defender is False


def test_bunt_health_check():
    """Verify bunt defense health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Bunt defense verified" in checks[0].detail
