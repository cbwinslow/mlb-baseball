"""Unit tests for Catcher Quick Exchange & Pop Time Engine (CATCH-XCHG-01, ADR-209)."""

from mlb_baseball.model.catch_xchg import (
    CatcherExchangeEngine,
    CatcherExchangeMetrics,
    health_check,
)


def test_lightning_exchange_catcher_classified_properly():
    """Verify sub-0.64s exchange and 85+ mph arm yields LIGHTNING_QUICK_EXCHANGE_CANNON."""
    engine = CatcherExchangeEngine()

    realmuto = CatcherExchangeMetrics(
        catcher_id="c1",
        catcher_name="J.T. Realmuto Archetype",
        exchange_time_sec=0.60,
        throw_velocity_mph=88.0,
        throw_flight_time_sec=1.24,
        throw_accuracy_pct=82.0,
        stolen_base_attempts_against=85,
    )

    res = engine.evaluate_exchange(realmuto)

    assert res.total_pop_time_sec <= 1.85
    assert res.cevi_score > 125.0
    assert res.sbd_runs_saved > 8.0
    assert res.transfer_tier == "LIGHTNING_QUICK_EXCHANGE_CANNON"
    assert res.is_lightning_transfer is True


def test_slow_transfer_strong_arm_classified_properly():
    """Verify slow exchange with high velocity yields STRONG_ARM_SLOW_TRANSFER."""
    engine = CatcherExchangeEngine()

    slow_catcher = CatcherExchangeMetrics(
        catcher_id="c2",
        catcher_name="Slow Transfer Cannon",
        exchange_time_sec=0.75,
        throw_velocity_mph=86.0,
        throw_flight_time_sec=1.27,
        throw_accuracy_pct=65.0,
        stolen_base_attempts_against=65,
    )

    res = engine.evaluate_exchange(slow_catcher)

    assert res.transfer_tier == "STRONG_ARM_SLOW_TRANSFER"
    assert res.is_lightning_transfer is False


def test_catch_xchg_health_check():
    """Verify catch xchg health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Catch Xchg verified" in checks[0].detail
