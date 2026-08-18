from decimal import Decimal

from mlb_baseball.model.log5 import probability


def test_equal_teams_give_fifty_fifty():
    assert probability(Decimal("0.500"), Decimal("0.500")) == Decimal("0.5")


def test_stronger_home_team_favored():
    p = probability(Decimal("0.600"), Decimal("0.400"))
    assert p > Decimal("0.5")
    # Hand-computed: 0.6*0.6 / (0.6*0.6 + 0.4*0.4) = 0.36 / 0.52
    assert abs(p - Decimal("0.36") / Decimal("0.52")) < Decimal("0.0001")


def test_matches_p_x_500_equals_x_defining_property():
    # The SABR article's own stated defining property: a team with
    # winning percentage x must get win probability exactly x against a
    # league-average (.500) team. This is what the previously shipped
    # home^2/(home^2+away^2) formula violated (.5902, not .600).
    p = probability(Decimal("0.600"), Decimal("0.500"))
    assert abs(p - Decimal("0.600")) < Decimal("0.0001")


def test_symmetric():
    home = probability(Decimal("0.650"), Decimal("0.450"))
    away = probability(Decimal("0.450"), Decimal("0.650"))
    assert abs(home + away - Decimal("1")) < Decimal("0.0001")


def test_extreme_records():
    # An undefeated team at a winless team's park -- still not literally
    # certain (log5 has no sense of sample size), but should be close to it.
    p = probability(Decimal("1.000"), Decimal("0.000"))
    assert p == Decimal("1")


def test_both_teams_winless_returns_fifty_fifty_not_a_zero_division_error():
    # Real production case, not hypothetical: found via a real
    # gold.game_feature sample containing two genuine still-winless 2018/
    # 2020 teams (0-2 and 0-1) matched up against each other. The raw
    # formula divides 0/0 here (home_term = away_term = 0) -- 0.5 is the
    # same limiting value the formula already returns for two *equal*
    # teams at any other winning percentage, not an arbitrary guess.
    assert probability(Decimal("0.000"), Decimal("0.000")) == Decimal("0.5")


def test_both_teams_undefeated_returns_fifty_fifty_not_a_zero_division_error():
    # Mirror-image real production case: a real gold.game_feature sample
    # also contains two genuine still-undefeated teams (2019/2020/2023
    # samples, up to 4-0) matched against each other -- same 0/0 (both
    # terms are x*(1-x) = 1*0 = 0), same 0.5 fix, same reasoning.
    assert probability(Decimal("1.000"), Decimal("1.000")) == Decimal("0.5")
