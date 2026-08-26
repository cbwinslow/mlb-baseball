"""Unit tests for Starting Pitcher First-Pitch Strike Engine (FSTRIKE-01, ADR-172)."""

import dataclasses

from mlb_baseball.model.fstrike import (
    FirstPitchStrikeEngine,
    PitcherFStrikeMetrics,
    health_check,
)


def test_dead_woba_fields_removed():
    """FSTRIKE-01 regression: PitcherFStrikeMetrics used to declare woba_after_0_1 and
    woba_after_1_0 fields that evaluate_fstrike() never actually referenced (the real
    formula is a flat 0.068 runs/PA constant). Assert the dead/misleading fields are
    gone rather than left behind as unused, confusing dataclass state.
    """
    field_names = {f.name for f in dataclasses.fields(PitcherFStrikeMetrics)}

    assert "woba_after_0_1" not in field_names
    assert "woba_after_1_0" not in field_names
    assert field_names == {"pitcher_id", "pitcher_name", "fstrike_pct", "batters_faced"}


def test_elite_first_pitch_strike_pitcher_has_high_fpsv_runs():
    """Verify high first-pitch strike percentage generates positive FPSV surplus runs."""
    engine = FirstPitchStrikeEngine()

    pounder = PitcherFStrikeMetrics(
        pitcher_id="p1",
        pitcher_name="Cliff Lee Archetype",
        fstrike_pct=0.69,
        batters_faced=800,
    )

    res = engine.evaluate_fstrike(pounder, league_fstrike_baseline=0.605)

    assert res.fps_delta_league > 0.080
    assert res.fpsv_runs_seasonal > 4.0
    assert res.command_tier == "ELITE_ZONE_POUNDER"


def test_passive_pitcher_classified_as_passive_behind_count():
    """Verify low first-pitch strike rate generates negative run surplus."""
    engine = FirstPitchStrikeEngine()

    wild = PitcherFStrikeMetrics(
        pitcher_id="p2",
        pitcher_name="Wild Starter",
        fstrike_pct=0.52,
        batters_faced=600,
    )

    res = engine.evaluate_fstrike(wild, league_fstrike_baseline=0.605)

    assert res.fps_delta_league < -0.080
    assert res.fpsv_runs_seasonal < -3.0
    assert res.command_tier == "PASSIVE_BEHIND_COUNT"


def test_fstrike_health_check():
    """Verify first-pitch strike health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "F-Strike verified" in checks[0].detail
