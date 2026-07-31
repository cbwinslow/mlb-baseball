from mlb_baseball.model.elo import HOME_ADVANTAGE, _mov_multiplier, expected_win_prob


def test_equal_ratings_favor_home_via_home_advantage():
    # Not 0.5 -- HOME_ADVANTAGE is baked into expected_win_prob itself, so
    # even dead-equal ratings should favor the home team slightly.
    p = expected_win_prob(1500.0, 1500.0)
    assert p > 0.5
    assert abs(p - 0.5345) < 0.001


def test_stronger_away_team_can_still_be_underdog_at_home():
    # A big enough road-team rating gap should overcome HOME_ADVANTAGE.
    p = expected_win_prob(1500.0, 1700.0)
    assert p < 0.5


def test_symmetric_around_home_advantage():
    # Reversing which team is "home" by the exact size of HOME_ADVANTAGE
    # should reproduce the equal-ratings home probability.
    p = expected_win_prob(1500.0 - HOME_ADVANTAGE, 1500.0)
    assert abs(p - 0.5) < 1e-9


def test_mov_multiplier_grows_with_margin():
    small = _mov_multiplier(1, 1500.0, 1500.0)
    large = _mov_multiplier(10, 1500.0, 1500.0)
    assert large > small


def test_mov_multiplier_dampens_for_a_big_favorite():
    # Same margin, but the winner was already a big favorite -- multiplier
    # should be smaller (the win was expected, so it should move ratings
    # less than the same margin from a competitive matchup).
    competitive = _mov_multiplier(5, 1500.0, 1500.0)
    lopsided_favorite = _mov_multiplier(5, 1700.0, 1500.0)
    assert lopsided_favorite < competitive
