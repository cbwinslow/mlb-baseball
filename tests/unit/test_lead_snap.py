"""Unit tests for Baserunner Secondary Lead Distance Engine (LEAD-SNAP-01, ADR-229)."""

from mlb_baseball.model.lead_snap import (
    LeadSnapEvaluationResult,
    RunnerLeadSnapEngine,
    RunnerLeadSnapMetrics,
    health_check,
)


def test_aggressive_runner_classified_properly():
    """Verify 25ft+ secondary lead yields AGGRESSIVE_TERROR_ON_BASEPATHS."""
    engine = RunnerLeadSnapEngine()

    elly = RunnerLeadSnapMetrics(
        runner_id="r1",
        runner_name="Elly De La Cruz Archetype",
        primary_lead_distance_ft=13.0,
        secondary_jump_distance_ft=25.8,
        pitcher_move_time_sec=1.40,
        pickoff_throw_rate_pct=14.0,
        baserunning_opportunities=90,
    )

    res: LeadSnapEvaluationResult = engine.evaluate_lead_snap(elly)

    assert res.asli_score > 125.0
    assert res.advance_prob_boost_pct > 15.0
    assert res.aslrv_runs_produced > 4.0
    assert res.lead_tier == "AGGRESSIVE_TERROR_ON_BASEPATHS"
    assert res.is_aggressive_terror is True


def test_cautious_runner_triggers_anchored_tier():
    """Verify sub-18ft secondary lead triggers CAUTIOUS_ANCHORED_STATIONARY_RUNNER."""
    engine = RunnerLeadSnapEngine()

    anchored = RunnerLeadSnapMetrics(
        runner_id="r2",
        runner_name="Anchored Runner",
        primary_lead_distance_ft=8.5,
        secondary_jump_distance_ft=17.2,
        pitcher_move_time_sec=1.30,
        pickoff_throw_rate_pct=6.0,
        baserunning_opportunities=65,
    )

    res = engine.evaluate_lead_snap(anchored)

    assert res.lead_tier == "CAUTIOUS_ANCHORED_STATIONARY_RUNNER"
    assert res.is_aggressive_terror is False


def test_lead_snap_health_check():
    """Verify lead snap health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Lead Snap verified" in checks[0].detail
