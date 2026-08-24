"""Unit tests for Batter Platoon Split Shrinkage Engine (PLATOON-01, ADR-155)."""

from mlb_baseball.model.splits import (
    BatterPlatoonEngine,
    BatterPlatoonRawStats,
    health_check,
)


def test_lhb_platoon_split_shrunk_toward_prior():
    """Verify small sample LHB split regresses toward prior."""
    engine = BatterPlatoonEngine()

    raw_lhb = BatterPlatoonRawStats(
        batter_id="b1",
        batter_name="Extreme LHB",
        bats_hand="L",
        overall_woba=0.340,
        pa_vs_lhp=100,
        woba_vs_lhp=0.220,  # Extreme raw dip
        pa_vs_rhp=400,
        woba_vs_rhp=0.370,
    )

    res = engine.evaluate_platoon_talent(raw_lhb, shrinkage_m=1000.0)

    # Regresses significantly from 0.220 up towards 0.315
    assert res.shrunk_woba_vs_lhp > 0.290
    assert res.shrunk_woba_vs_rhp > res.shrunk_woba_vs_lhp
    assert res.platoon_tier in ("EXTREME_PLATOON", "MODERATE_PLATOON")


def test_switch_hitter_maintains_neutral_platoon_profile():
    """Verify switch hitter evaluates to PLATOON_NEUTRAL."""
    engine = BatterPlatoonEngine()

    switch = BatterPlatoonRawStats(
        batter_id="b2",
        batter_name="Switch Hitter",
        bats_hand="S",
        overall_woba=0.330,
        pa_vs_lhp=250,
        woba_vs_lhp=0.332,
        pa_vs_rhp=350,
        woba_vs_rhp=0.328,
    )

    res = engine.evaluate_platoon_talent(switch, shrinkage_m=1000.0)

    assert res.platoon_tier == "PLATOON_NEUTRAL"
    assert res.true_talent_platoon_delta < 0.020
    assert res.is_strict_platoon_candidate is False


def test_platoon_health_check():
    """Verify platoon health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Platoon verified" in checks[0].detail
