"""Hand-checked Chamberlain/Pavlidis VAA kinematics (FanGraphs 2022-02-01)."""

import math

from mlb_baseball.model.vaa import pitch_vaa_degrees

# y0=50, yf=17/12, vy0=-130, ay=30, vz0=-8, az=-20
# disc = 130^2 - 2*30*(50-17/12) = 16900 - 2915 = 13985
# vy_f = -sqrt(13985) ≈ -118.2582
# t = (-118.2582 - (-130)) / 30 ≈ 0.391393
# vz_f = -8 + (-20)*0.391393 ≈ -15.8279
# VAA = -atan(-15.8279 / -118.2582) * 180/pi ≈ -7.6214


def test_pitch_vaa_degrees_matches_hand_calculated_kinematics():
    disc = 130.0**2 - 2.0 * 30.0 * (50.0 - 17.0 / 12.0)
    assert abs(disc - 13985.0) < 0.01
    vy_f = -math.sqrt(disc)
    t = (vy_f - (-130.0)) / 30.0
    vz_f = -8.0 + (-20.0) * t
    expected = math.degrees(-math.atan(vz_f / vy_f))
    got = pitch_vaa_degrees(vy0=-130.0, ay=30.0, vz0=-8.0, az=-20.0)
    assert got is not None
    assert abs(got - round(expected, 4)) < 1e-9
    assert abs(got - (-7.6233)) < 0.001


def test_pitch_vaa_degrees_rejects_unphysical_kinematics():
    assert pitch_vaa_degrees(vy0=-130.0, ay=0.0, vz0=-8.0, az=-20.0) is None
    assert pitch_vaa_degrees(vy0=-1.0, ay=30.0, vz0=-8.0, az=-20.0) is None
