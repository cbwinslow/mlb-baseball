"""Unit tests for Correlated Same-Game Parlay (SGP) Engine & Copulas (PARLAY-01, ADR-125)."""

from mlb_baseball.model.parlay import (
    CorrelatedParlayEvaluator,
    ParlayLeg,
    ParlayLegType,
    SimulatedGamePath,
    SyntheticGaussianCopulaSampler,
    health_check,
)


def test_parlay_leg_path_evaluation():
    """Verify ParlayLeg correctly evaluates individual simulated game paths."""
    path1 = SimulatedGamePath(
        path_id=1,
        home_score=5,
        away_score=2,
        f5_home_score=3,
        f5_away_score=1,
        home_starter_ks=8,
        away_starter_ks=4,
    )

    leg_ml = ParlayLeg("l1", ParlayLegType.MONEYLINE_HOME, "Home ML")
    leg_rl = ParlayLeg("l2", ParlayLegType.RUN_LINE_HOME, "Home -1.5", line=1.5)
    leg_und = ParlayLeg("l3", ParlayLegType.TOTAL_UNDER, "Under 8.5", line=8.5)
    leg_k = ParlayLeg("l4", ParlayLegType.PITCHER_K_HOME_OVER, "Home K Over 6.5", line=6.5)
    leg_f5 = ParlayLeg("l5", ParlayLegType.F5_MONEYLINE_HOME, "Home F5 ML")

    assert leg_ml.evaluate_path(path1) is True
    assert leg_rl.evaluate_path(path1) is True
    assert leg_und.evaluate_path(path1) is True  # 5 + 2 = 7 < 8.5
    assert leg_k.evaluate_path(path1) is True  # 8 > 6.5
    assert leg_f5.evaluate_path(path1) is True  # 3 > 1


def test_correlated_parlay_synergy_boost():
    """Verify positive inter-event correlation produces correlation multiplier > 1.0."""
    sampler = SyntheticGaussianCopulaSampler(
        exp_home_runs=5.5,
        exp_away_runs=2.5,
        exp_home_ks=8.0,
        exp_away_ks=4.0,
        random_seed=123,
    )
    evaluator = CorrelatedParlayEvaluator(sampler, n_sims=3000)

    # Home Win + Away Team Under 3.5 + Home Starter Over 6.5 Ks
    leg1 = ParlayLeg("l1", ParlayLegType.MONEYLINE_HOME, "Home ML", individual_probability=0.65)
    leg2 = ParlayLeg(
        "l2",
        ParlayLegType.TEAM_TOTAL_AWAY_UNDER,
        "Away Under 3.5",
        line=3.5,
        individual_probability=0.60,
    )
    leg3 = ParlayLeg(
        "l3",
        ParlayLegType.PITCHER_K_HOME_OVER,
        "Home K Over 6.5",
        line=6.5,
        individual_probability=0.65,
    )

    parlay = evaluator.evaluate_parlay(
        "sgp_1", "game_123", [leg1, leg2, leg3], sportsbook_offered_odds=4.50
    )

    # Expected correlation boost
    assert parlay.correlation_multiplier > 1.10
    assert parlay.joint_prob > parlay.independent_prob
    assert parlay.fair_decimal_odds < (1.0 / parlay.independent_prob)
    assert parlay.leg_count == 3


def test_find_best_correlated_parlays_combinatorial():
    """Verify combinatorial search ranks high-correlation parlay combinations."""
    sampler = SyntheticGaussianCopulaSampler(random_seed=42)
    evaluator = CorrelatedParlayEvaluator(sampler, n_sims=2000)

    candidate_legs = [
        ParlayLeg("l1", ParlayLegType.MONEYLINE_HOME, "Home ML", individual_probability=0.55),
        ParlayLeg(
            "l2", ParlayLegType.RUN_LINE_HOME, "Home -1.5", line=1.5, individual_probability=0.42
        ),
        ParlayLeg(
            "l3",
            ParlayLegType.TEAM_TOTAL_AWAY_UNDER,
            "Away Under 3.5",
            line=3.5,
            individual_probability=0.52,
        ),
        ParlayLeg(
            "l4",
            ParlayLegType.PITCHER_K_HOME_OVER,
            "Home K Over 6.5",
            line=6.5,
            individual_probability=0.50,
        ),
        ParlayLeg(
            "l5", ParlayLegType.TOTAL_OVER, "Over 9.5", line=9.5, individual_probability=0.45
        ),
    ]

    best_2legs = evaluator.find_best_correlated_parlays(
        "game_123", candidate_legs, leg_count=2, min_correlation_boost=1.05
    )

    assert len(best_2legs) > 0
    # Top parlay should have highest correlation multiplier
    assert best_2legs[0].correlation_multiplier >= best_2legs[-1].correlation_multiplier


def test_parlay_health_check():
    """Verify parlay health check returns clean pass."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "Correlated SGP boost verified" in checks[0].detail
