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


def test_default_literal_metrics_not_tagged_elite_despite_raw_lead_outs():
    """Regression (ADR-185): the dataclass's own literal defaults
    (lead_runner_outs=3, popups=2, hits=1) compute total_bunt_runs_saved of
    only 1.25 -- below the documented ELITE_BUNT_ERASER threshold of +1.60 --
    but the removed `or lead_runner_outs >= 3` branch used to tag it elite
    anyway. ADR-185 defines ELITE_BUNT_ERASER as a single condition on the
    computed run value, so this must not be elite.
    """
    engine = InfieldBuntDefenseEngine()
    default_fielder = InfieldBuntDefenseMetrics(fielder_id="f3", fielder_name="Default Fielder")

    res = engine.evaluate_bunt_defense(default_fielder)

    assert res.total_bunt_runs_saved == 1.25
    assert res.defense_tier != "ELITE_BUNT_ERASER"
    assert res.is_elite_bunt_defender is False


def test_bad_defense_with_high_lead_runner_outs_not_tagged_elite():
    """Regression (ADR-185): a fielder with lead_runner_outs >= 3 but many
    bunt hits allowed computes a clearly negative net run value, but the
    removed OR branch used to still tag it ELITE_BUNT_ERASER purely off the
    raw outs count.
    """
    engine = InfieldBuntDefenseEngine()
    leaky_corner = InfieldBuntDefenseMetrics(
        fielder_id="f4",
        fielder_name="Leaky Corner",
        lead_runner_outs=3,
        bunt_popups_caught=0,
        bunt_hits_allowed=10,
        total_bunt_attempts=25,
    )

    res = engine.evaluate_bunt_defense(leaky_corner)

    assert res.total_bunt_runs_saved == -3.36
    assert res.defense_tier != "ELITE_BUNT_ERASER"
    assert res.is_elite_bunt_defender is False


def test_bunt_health_check():
    """Verify bunt defense health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Bunt defense verified" in checks[0].detail
