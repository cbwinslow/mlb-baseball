"""Unit rules for the extended cwevent columns."""

from retrosheetpy.extended import exception_flags, force_fields, pitch_counts, safe_on_error
from retrosheetpy.play import parse_play

ALL = (True, True, True)


def test_pitch_counts_split_balls_and_strikes():
    counts = pitch_counts("CCFF*BB.X")
    assert counts["PA_BALL_CT"] == "2" and counts["PA_CALLED_BALL_CT"] == "2"
    assert counts["PA_STRIKE_CT"] == "5" and counts["PA_INPLAY_STRIKE_CT"] == "1"
    assert counts["PA_FOUL_STRIKE_CT"] == "2" and counts["PA_CALLED_STRIKE_CT"] == "2"


def test_hit_batter_and_other_ball_are_counted_differently():
    hit = pitch_counts("H")
    other = pitch_counts("V")
    assert hit["PA_BALL_CT"] == "1" and hit["PA_HITBATTER_BALL_CT"] == "1"
    assert other["PA_BALL_CT"] == "0" and other["PA_OTHER_BALL_CT"] == "1"


def test_force_flags_need_force_out_or_ground_double_play():
    forced = force_fields(parse_play("64(1)3/GDP/G6"), (True, False, False))
    assert forced["BASE2_FORCE_FL"] == "T"
    assert force_fields(parse_play("5(2)4(1)3/GTP"), (True, True, False))["BASE2_FORCE_FL"] == "F"
    assert force_fields(parse_play("63/G6"), ALL)["BASE2_FORCE_FL"] == "F"


def test_safe_on_error_by_batter_advance_error():
    assert safe_on_error(parse_play("36(1)/FO/G3.2-3;BX1(6E1)"), True)
    assert not safe_on_error(parse_play("S7/L7D+.BX2(74)"), True)
    assert safe_on_error(parse_play("E5/G5"), True)


def test_exception_flags():
    assert exception_flags(parse_play("CS2(99)"))["UNKNOWN_OUT_EXC_FL"] == "T"
    assert exception_flags(parse_play("K#"))["UNCERTAIN_PLAY_EXC_FL"] == "T"
    assert exception_flags(parse_play("K")) == {
        "UNKNOWN_OUT_EXC_FL": "F",
        "UNCERTAIN_PLAY_EXC_FL": "F",
    }
