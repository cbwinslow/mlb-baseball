"""Tests for Batter Swing Timing & Tempo Consistency Engine (SWING-TEMPO-01)."""

from mlb_baseball.model.swing_tempo import (
    BatterSwingTempoEngine,
    BatterSwingTempoMetrics,
    SwingTempoEvaluationResult,
    health_check,
)


def test_elite_tempo_classified_properly():
    """Verify low timing std with high bat speed consistency yields ELITE tempo."""
    engine = BatterSwingTempoEngine()

    vlad = BatterSwingTempoMetrics(
        batter_id="p1",
        batter_name="Vlad Jr Archetype",
        timing_std_ms=1.2,
        bat_speed_consistency_pct=97.0,
        late_count_contact_pct=88.0,
        total_swings=400,
        avg_bat_speed_mph=78.0,
    )

    res: SwingTempoEvaluationResult = engine.evaluate_tempo(vlad)

    assert res.stci_score > 116.0
    assert res.lsar_runs > 7.0
    assert res.tempo_tier == "ELITE_METRONOME_SWING_MACHINE"
    assert res.is_elite_tempo is True


def test_erratic_swinger_triggers_liability():
    """Verify high timing std yields ERRATIC liability tier."""
    engine = BatterSwingTempoEngine()

    erratic = BatterSwingTempoMetrics(
        batter_id="p2",
        batter_name="Erratic Hacker",
        timing_std_ms=7.0,
        bat_speed_consistency_pct=78.0,
        late_count_contact_pct=58.0,
        total_swings=200,
    )

    res: SwingTempoEvaluationResult = engine.evaluate_tempo(erratic)

    assert res.stci_score < 100.0
    assert res.lsar_runs < 0.0
    assert res.tempo_tier == "ERRATIC_TIMING_WILD_SWINGER_LIABILITY"
    assert res.is_elite_tempo is False


def test_swing_tempo_health_check():
    """Verify swing tempo health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
