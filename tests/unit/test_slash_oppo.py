"""Unit tests for Batter Opposite Field Slash Engine (SLASH-OPPO-01, ADR-219)."""

from mlb_baseball.model.slash_oppo import (
    BatterSlashOppoEngine,
    BatterSlashOppoMetrics,
    health_check,
)


def test_slash_artist_classified_as_elite_all_fields():
    """Verify 32%+ oppo spray and low pull GB% yields ELITE_ALL_FIELDS_SLASH_ARTIST."""
    engine = BatterSlashOppoEngine()

    arraez = BatterSlashOppoMetrics(
        batter_id="b1",
        batter_name="Luis Arraez Archetype",
        oppo_contact_pct=35.0,
        oppo_line_drive_pct=30.0,
        pull_groundball_pct=46.0,
        total_bbe_count=350,
    )

    res = engine.evaluate_slash(arraez)

    assert res.ofsrr_score > 125.0
    assert res.babip_adjustment > 0.025
    assert res.ofsrv_runs_saved > 4.0
    assert res.slash_tier == "ELITE_ALL_FIELDS_SLASH_ARTIST"
    assert res.is_slash_artist is True


def test_pull_shift_bait_triggers_pull_bait_tier():
    """Verify heavy pull groundballs with low oppo contact triggers EXTREME_PULL_SHIFT_BAIT."""
    engine = BatterSlashOppoEngine()

    pull_heavy = BatterSlashOppoMetrics(
        batter_id="b2",
        batter_name="Extreme Puller",
        oppo_contact_pct=15.0,
        oppo_line_drive_pct=14.0,
        pull_groundball_pct=78.0,
        total_bbe_count=260,
    )

    res = engine.evaluate_slash(pull_heavy)

    assert res.slash_tier == "EXTREME_PULL_SHIFT_BAIT"
    assert res.is_slash_artist is False


def test_default_metrics_produce_neutral_ofsrr_score():
    """SLASH-OPPO-01 regression: the class's own default pull_groundball_pct (64.0) is
    documented in its own inline comment as the benchmark, but the OFSRR formula was
    anchored at 65.0 instead. Feeding the engine its own defaults (24.0 oppo, 20.0 oppo
    LD, 64.0 pull GB -- all three matching their own comments) should now produce an
    exactly neutral OFSRR score of 100.0.
    """
    engine = BatterSlashOppoEngine()
    default_batter = BatterSlashOppoMetrics(batter_id="b3", batter_name="League Average")

    res = engine.evaluate_slash(default_batter)

    assert res.ofsrr_score == 100.0
    assert res.babip_adjustment == 0.0
    assert res.ofsrv_runs_saved == 0.0


def test_slash_oppo_health_check():
    """Verify slash oppo health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Slash Oppo verified" in checks[0].detail
