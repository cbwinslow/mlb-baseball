"""Unit tests for Batter Opposite-Field Line Drive Engine (OPPO-LINER-01, ADR-251)."""

from mlb_baseball.model.oppo_liner import (
    BatterOppoLinerEngine,
    BatterOppoLinerMetrics,
    OppoLinerEvaluationResult,
    health_check,
)


def test_line_drive_artist_classified_properly():
    """Verify 28%+ LD and 0.700+ BABIP yields SURGICAL_OPPOSITE_FIELD_LINE_DRIVE_ARTIST."""
    engine = BatterOppoLinerEngine()

    arraez = BatterOppoLinerMetrics(
        batter_id="b1",
        batter_name="Luis Arraez Archetype",
        oppo_line_drive_pct=32.0,
        oppo_liner_babip=0.760,
        oppo_liner_hard_hit_pct=50.0,
        oppo_contact_events=180,
    )

    res: OppoLinerEvaluationResult = engine.evaluate_oppo_liner(arraez)

    assert res.ofldii_score > 125.0
    assert res.olpr_runs_produced > 15.0
    assert res.liner_tier == "SURGICAL_OPPOSITE_FIELD_LINE_DRIVE_ARTIST"
    assert res.is_line_drive_artist is True


def test_weak_flare_triggers_liability_tier():
    """Verify low line drive rate and low BABIP triggers ROLLOVER_WEAK_OPPO_FLARE_LIABILITY."""
    engine = BatterOppoLinerEngine()

    flare = BatterOppoLinerMetrics(
        batter_id="b2",
        batter_name="Weak Roller",
        oppo_line_drive_pct=10.0,
        oppo_liner_babip=0.450,
        oppo_liner_hard_hit_pct=22.0,
        oppo_contact_events=120,
    )

    res = engine.evaluate_oppo_liner(flare)

    assert res.liner_tier == "ROLLOVER_WEAK_OPPO_FLARE_LIABILITY"
    assert res.is_line_drive_artist is False


def test_oppo_liner_health_check():
    """Verify oppo liner health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Oppo Liner verified" in checks[0].detail
