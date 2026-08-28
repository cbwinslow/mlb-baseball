"""Unit tests for Starting Pitcher Times-Through-the-Order Engine (TTO-01, ADR-164)."""

from mlb_baseball.model.tto import (
    PitcherTTOMetrics,
    TimesThroughOrderEngine,
    health_check,
)


def test_starter_with_heavy_third_time_penalty_classified_as_strict_2_time_hook():
    """Verify sharp wOBA jump and K% drop trigger strict 2-time hook recommendation."""
    engine = TimesThroughOrderEngine()

    vulnerable_starter = PitcherTTOMetrics(
        pitcher_id="p1",
        pitcher_name="Two-Time Specialist",
        tto1_woba=0.275,
        tto2_woba=0.305,
        tto3_woba=0.370,
        tto1_k_pct=0.28,
        tto3_k_pct=0.16,
    )

    res = engine.evaluate_tto(vulnerable_starter)

    assert res.tto_woba_delta_3_1 > 0.080
    assert res.tto_k_delta_3_1 < -0.100
    assert res.third_time_vulnerability_index > 65.0
    assert res.recommended_hook_policy == "STRICT_2_TIME_HOOK"


def test_workhorse_ace_maintains_consistent_order_profile():
    """Verify elite ace with flat TTO profile evaluates to WORKHORSE_ACE."""
    engine = TimesThroughOrderEngine()

    ace = PitcherTTOMetrics(
        pitcher_id="p2",
        pitcher_name="Workhorse Ace",
        tto1_woba=0.280,
        tto2_woba=0.285,
        tto3_woba=0.295,
        tto1_k_pct=0.32,
        tto3_k_pct=0.30,
    )

    res = engine.evaluate_tto(ace)

    assert res.tto_woba_delta_3_1 <= 0.020
    assert res.third_time_vulnerability_index < 30.0
    assert res.recommended_hook_policy == "WORKHORSE_ACE"


def test_tto_health_check():
    """Verify TTO health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "TTO verified" in checks[0].detail
