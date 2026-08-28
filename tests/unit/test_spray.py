"""Unit tests for Batter Pull-Side / Opposite-Field Spray Power Engine (SPRAY-01, ADR-163)."""

from mlb_baseball.model.spray import (
    BatterSprayMetrics,
    SprayDirectionEngine,
    health_check,
)


def test_dead_pull_slugger_has_high_ppc_and_dead_pull_flag():
    """Verify dead pull power hitter classifies into DEAD_PULL_SLUGGER."""
    engine = SprayDirectionEngine()

    pull_slugger = BatterSprayMetrics(
        batter_id="b1",
        batter_name="Pull Powerhouse",
        bats_hand="L",
        pull_pct=0.49,
        center_pct=0.31,
        oppo_pct=0.20,
        hr_pull=32,
        hr_total=35,
        gb_pull_pct=0.68,
    )

    res = engine.evaluate_spray(pull_slugger)

    assert res.pull_power_concentration_pct > 90.0
    assert res.spray_archetype == "DEAD_PULL_SLUGGER"
    assert res.is_dead_pull_liability is True


def test_all_fields_spray_hitter_has_high_sni():
    """Verify spray contact hitter shows high Spray Neutrality Index."""
    engine = SprayDirectionEngine()

    all_fields = BatterSprayMetrics(
        batter_id="b2",
        batter_name="Luis Arraez Archetype",
        bats_hand="L",
        pull_pct=0.33,
        center_pct=0.34,
        oppo_pct=0.33,
        hr_pull=2,
        hr_total=5,
        gb_pull_pct=0.45,
    )

    res = engine.evaluate_spray(all_fields)

    assert res.spray_neutrality_index > 0.90
    assert res.spray_archetype == "ALL_FIELDS_GAP_HITTER"
    assert res.is_dead_pull_liability is False


def test_spray_health_check():
    """Verify spray health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Spray verified" in checks[0].detail
