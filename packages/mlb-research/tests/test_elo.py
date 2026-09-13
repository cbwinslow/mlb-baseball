import numpy as np
import pytest
from mlb_research import elo


def test_elo_v2_config_has_documented_defaults():
    config = elo.EloV2Config()
    assert config.home_advantage == elo.HOME_ADVANTAGE
    assert config.k_factor == elo.K_FACTOR
    assert config.reversion_weight == elo.REVERSION_WEIGHT
    assert config.fade_games == elo.FADE_GAMES
    assert config.starter_weight == elo.STARTER_WEIGHT


def test_faded_rating_blends_from_preseason_prior_to_in_season_rating():
    preseason_prior = 1550.0
    in_season_rating = 1620.0
    fade_games = 30

    # n=0: exactly the preseason prior -- the fade generalizes v1's jump,
    # it doesn't replace it.
    assert elo._faded_rating(preseason_prior, in_season_rating, 0, fade_games) == preseason_prior

    # mid-fade (n=15, half faded): strictly between the two, at the
    # hand-computed halfway point.
    mid = elo._faded_rating(preseason_prior, in_season_rating, 15, fade_games)
    assert mid == pytest.approx((preseason_prior + in_season_rating) / 2)
    assert preseason_prior < mid < in_season_rating

    # n >= fade_games: fully faded to the plain in-season Elo walk.
    assert elo._faded_rating(preseason_prior, in_season_rating, 30, fade_games) == in_season_rating
    assert elo._faded_rating(preseason_prior, in_season_rating, 45, fade_games) == in_season_rating


def test_a_brand_new_team_starts_at_starting_elo_regardless_of_reversion_weight():
    # A team with no prior-season history defaults its "prior rating" to
    # STARTING_ELO -- blending STARTING_ELO with itself is idempotent, so
    # the preseason prior (and thus the faded rating at n=0) is STARTING_ELO
    # exactly, whatever reversion_weight is. No special-casing needed beyond
    # the same formula every team goes through.
    for reversion_weight in (0.0, 0.25, 1.0):
        preseason_prior = elo._preseason_prior(elo.STARTING_ELO, reversion_weight)
        assert preseason_prior == elo.STARTING_ELO
        assert (
            elo._faded_rating(preseason_prior, elo.STARTING_ELO, 0, elo.FADE_GAMES)
            == elo.STARTING_ELO
        )


def test_quality_z_matches_hand_calculated_zscore_and_sign():
    values = np.array([3.0, 4.0, 5.0, 6.0])
    mean, std = float(values.mean()), float(values.std())

    # Lower FIP is a better pitcher, so it should score a positive z.
    z_good = elo._quality_z(3.0, mean, std)
    z_bad = elo._quality_z(6.0, mean, std)

    assert z_good == pytest.approx(-(3.0 - mean) / std)
    assert z_bad == pytest.approx(-(6.0 - mean) / std)
    assert z_good > 0
    assert z_bad < 0


def test_quality_z_is_neutral_for_a_missing_starter_value():
    # A missing input -> no adjustment for that side, not a fabricated
    # average -- the other side's real value is unaffected either way,
    # since _quality_z scores each side independently.
    assert elo._quality_z(None, mean=4.0, std=1.0) == 0.0
    assert elo._quality_z(3.0, mean=4.0, std=1.0) != 0.0


def test_fip_mean_std_pools_home_and_away_train_values():
    train_fip = np.array([3.0, 4.0, 5.0, 6.0] * 6)  # 24 values, >= min_count
    mean, std = elo._fip_mean_std(train_fip)
    assert mean == pytest.approx(4.5)
    assert std == pytest.approx(train_fip.std())


def test_fip_mean_std_is_neutral_when_degenerate():
    # Fewer than the documented minimum count of real values.
    too_few = np.array([3.0, 4.0, np.nan, np.nan])
    mean, std = elo._fip_mean_std(too_few)
    assert std == 0.0
    assert elo._quality_z(3.0, mean, std) == 0.0

    # Zero variance (every real value identical) -- can't divide by it.
    zero_variance = np.array([4.0] * 25)
    mean, std = elo._fip_mean_std(zero_variance)
    assert std == 0.0
    assert elo._quality_z(4.0, mean, std) == 0.0


def test_expected_win_prob_matches_v1s_formula():
    # Equal ratings: home advantage alone should give the home team a
    # probability above 0.5, matching the hand-computed v1 formula.
    home_advantage = 24.0
    prob = elo.expected_win_prob(1500.0, 1500.0, home_advantage)
    expected = 1.0 / (1.0 + 10 ** ((1500.0 - (1500.0 + home_advantage)) / 400.0))
    assert prob == pytest.approx(expected)
    assert prob > 0.5


def test_effective_rating_with_zero_starter_weight_ignores_quality_z():
    # This is the tie-out the model card's baseline depends on (design D5):
    # starter_weight=0 must reproduce the unadjusted rating exactly,
    # regardless of quality_z's value.
    rating = 1550.0
    for quality_z in (-3.0, 0.0, 2.5):
        assert elo._effective_rating(rating, quality_z, starter_weight=0.0) == rating

    assert elo._effective_rating(rating, 2.0, starter_weight=50.0) == rating + 100.0
