"""Unit tests for Player-Game Props Prediction System (PROP-01, ADR-106)."""

import math

import pytest

from mlb_baseball.model.props import (
    log5_matchup_rate,
    poisson_cdf,
    poisson_over_prob,
    poisson_pmf,
    predict_batter_props,
    predict_pitcher_outs,
    predict_pitcher_strikeouts,
)


def test_log5_matchup_rate_precision():
    """Verify Log5 combination matches hand calculation."""
    # Pitcher K% = 0.30, Opponent K% = 0.30, League K% = 0.225
    # odds_a = 0.30/0.70 = 0.42857
    # odds_b = 0.30/0.70 = 0.42857
    # odds_lg = 0.225/0.775 = 0.29032
    # odds_matchup = (0.42857 * 0.42857) / 0.29032 = 0.63265
    # prob = 0.63265 / 1.63265 = 0.3875
    res = log5_matchup_rate(0.30, 0.30, 0.225)
    assert res == pytest.approx(0.3875, abs=1e-3)


def test_poisson_pmf_and_cdf_deterministic_math():
    """Verify Poisson distribution formulas against exact closed-form values."""
    # Mean = 2.0
    # P(X=0) = e^-2 = 0.135335
    # P(X=1) = 2 * e^-2 = 0.27067
    # P(X=2) = 2^2/2 * e^-2 = 0.27067
    mu = 2.0
    assert poisson_pmf(0, mu) == pytest.approx(math.exp(-2.0))
    assert poisson_pmf(1, mu) == pytest.approx(2.0 * math.exp(-2.0))
    assert poisson_pmf(2, mu) == pytest.approx(2.0 * math.exp(-2.0))

    # CDF
    cdf_2 = poisson_cdf(2, mu)
    expected_cdf_2 = math.exp(-2.0) * (1 + 2.0 + 2.0)
    assert cdf_2 == pytest.approx(expected_cdf_2)

    # Over 2.5 is P(X >= 3) = 1 - CDF(2)
    over_2_5 = poisson_over_prob(2.5, mu)
    assert over_2_5 == pytest.approx(1.0 - expected_cdf_2)


def test_predict_pitcher_strikeouts():
    """Verify strikeout prop predictions, workload effects, and distribution sums."""
    prop = predict_pitcher_strikeouts(
        player_id=101,
        player_name="Ace Pitcher",
        mlb_game_pk="712345",
        pitcher_k_pct=0.32,
        opponent_k_pct=0.25,
        pitcher_rest_days=5,
        lines=(4.5, 5.5, 6.5),
    )

    assert prop.player_id == 101
    assert prop.expected_k > 6.0
    assert prop.expected_bf == 23.5  # 22.5 baseline + 1.0 for 5 days rest
    assert 0.0 < prop.over_under_probs[5.5] < 1.0
    # Higher line should have strictly lower over probability
    assert prop.over_under_probs[4.5] > prop.over_under_probs[5.5] > prop.over_under_probs[6.5]
    # Sum of first 16 PMF probabilities should be close to 1.0
    assert sum(prop.k_distribution.values()) == pytest.approx(1.0, abs=0.01)


def test_predict_pitcher_outs():
    """Verify pitcher outs recorded expectations."""
    # Strong pitcher (FIP 2.50) vs weak offense (wRC+ 80)
    prop_elite = predict_pitcher_outs(
        player_id=101,
        player_name="Elite Starter",
        mlb_game_pk="712345",
        pitcher_fip=2.50,
        opponent_wrc_plus=80.0,
    )

    # Weak pitcher (FIP 5.50) vs strong offense (wRC+ 120)
    prop_struggling = predict_pitcher_outs(
        player_id=102,
        player_name="Struggling Starter",
        mlb_game_pk="712345",
        pitcher_fip=5.50,
        opponent_wrc_plus=120.0,
    )

    assert prop_elite.expected_outs > prop_struggling.expected_outs
    assert prop_elite.expected_ip > 5.0
    assert prop_elite.over_under_probs[15.5] > prop_struggling.over_under_probs[15.5]


def test_predict_batter_props():
    """Verify batter hit, total bases, and anytime HR calculations."""
    prop_slugger = predict_batter_props(
        player_id=501,
        player_name="Power Hitter",
        mlb_game_pk="712345",
        batter_obp=0.390,
        batter_slg=0.580,
        batter_iso=0.280,
        pitcher_fip=4.50,
        park_hr_factor=115.0,
    )

    assert prop_slugger.expected_hits > 0.8
    assert prop_slugger.expected_total_bases > 1.5
    assert 0.0 < prop_slugger.anytime_hr_prob < 0.5
    assert 0.0 < prop_slugger.over_0_5_hits_prob < 1.0
    assert prop_slugger.over_0_5_hits_prob > prop_slugger.over_1_5_hits_prob
    assert prop_slugger.over_0_5_tb_prob > prop_slugger.over_1_5_tb_prob
