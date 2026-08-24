"""Unit tests for Pitch Physics & Stuff+/Location+/Pitching+ Rating Engine (STUFF-01, ADR-126)."""

from mlb_baseball.model.stuff import (
    PhysicalPitchRatingEngine,
    PitchPhysicsVector,
    PitchType,
    health_check,
)


def test_stuff_plus_four_seam_fastball_scaling():
    """Verify elite fastball scores >120 Stuff+ and sub-par fastball scores <90."""
    engine = PhysicalPitchRatingEngine()

    elite_ff = PitchPhysicsVector(
        pitch_type=PitchType.FOUR_SEAM,
        release_speed_mph=98.5,
        induced_vert_break_in=19.0,
        horizontal_break_in=8.0,
        release_height_ft=6.0,
        release_side_ft=-1.8,
        release_extension_ft=6.6,
        plate_x_ft=0.2,
        plate_z_ft=3.2,
    )
    subpar_ff = PitchPhysicsVector(
        pitch_type=PitchType.FOUR_SEAM,
        release_speed_mph=90.0,
        induced_vert_break_in=13.0,
        horizontal_break_in=6.0,
        release_height_ft=6.0,
        release_side_ft=-1.8,
        release_extension_ft=5.5,
        plate_x_ft=0.0,
        plate_z_ft=2.5,
    )

    grade_elite = engine.evaluate_pitch(elite_ff)
    grade_subpar = engine.evaluate_pitch(subpar_ff)

    assert grade_elite.stuff_plus > 120.0
    assert grade_subpar.stuff_plus < 90.0
    assert grade_elite.expected_whiff_rate > grade_subpar.expected_whiff_rate


def test_location_plus_count_awareness():
    """Verify Location+ rewards edge/chase pitches on 2-strikes."""
    engine = PhysicalPitchRatingEngine()

    # 2-strike count (0-2)
    # Edge shadow pitch (plate_x=0.75, plate_z=1.4)
    shadow_pitch = PitchPhysicsVector(
        pitch_type=PitchType.SLIDER,
        release_speed_mph=86.0,
        induced_vert_break_in=2.0,
        horizontal_break_in=-12.0,
        release_height_ft=6.0,
        release_side_ft=-2.0,
        release_extension_ft=6.2,
        plate_x_ft=0.75,
        plate_z_ft=1.4,
    )
    # Heart of plate meatball on 0-2 (plate_x=0.0, plate_z=2.5)
    meatball_pitch = PitchPhysicsVector(
        pitch_type=PitchType.SLIDER,
        release_speed_mph=86.0,
        induced_vert_break_in=2.0,
        horizontal_break_in=-12.0,
        release_height_ft=6.0,
        release_side_ft=-2.0,
        release_extension_ft=6.2,
        plate_x_ft=0.0,
        plate_z_ft=2.5,
    )

    grade_shadow = engine.evaluate_pitch(shadow_pitch, count=(0, 2))
    grade_meatball = engine.evaluate_pitch(meatball_pitch, count=(0, 2))

    assert grade_shadow.location_plus > 110.0
    assert grade_meatball.location_plus < 90.0


def test_pitcher_arsenal_profile_aggregation():
    """Verify repertoire evaluation computes usage-weighted composite Stuff+ and Pitching+."""
    engine = PhysicalPitchRatingEngine()

    p1 = PitchPhysicsVector(
        pitch_type=PitchType.FOUR_SEAM,
        release_speed_mph=95.0,
        induced_vert_break_in=16.5,
        horizontal_break_in=7.0,
        release_height_ft=6.0,
        release_side_ft=-1.8,
        release_extension_ft=6.2,
        plate_x_ft=0.2,
        plate_z_ft=3.0,
    )
    p2 = PitchPhysicsVector(
        pitch_type=PitchType.SLIDER,
        release_speed_mph=85.0,
        induced_vert_break_in=2.0,
        horizontal_break_in=-8.0,
        release_height_ft=6.0,
        release_side_ft=-1.8,
        release_extension_ft=6.2,
        plate_x_ft=0.7,
        plate_z_ft=1.5,
    )

    pitches = [(p1, (0, 0))] * 60 + [(p2, (0, 2))] * 40
    profile = engine.evaluate_arsenal("12345", "Test Ace", pitches)

    assert profile.pitches_evaluated == 100
    assert "FF" in profile.repertoire_grades
    assert "SL" in profile.repertoire_grades
    assert profile.usage_weights["FF"] == 0.60
    assert profile.usage_weights["SL"] == 0.40
    assert 95.0 <= profile.overall_stuff_plus <= 110.0


def test_stuff_health_check():
    """Verify stuff health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Stuff+ model verified" in checks[0].detail
