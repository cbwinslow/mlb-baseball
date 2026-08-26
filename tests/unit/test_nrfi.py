"""Unit tests for First-Inning Run Scored (NRFI / YRFI) Valuation Engine (NRFI-01, ADR-156)."""

from mlb_baseball.model.nrfi import (
    FirstInningValuationEngine,
    InningOneMatchupInputs,
    health_check,
)


def test_ace_pitchers_matchup_yields_high_nrfi_probability():
    """Verify duel between low-ERA starters results in high P(NRFI).

    Threshold recalibrated for NRFI-01 (0.40 -> 0.52 baseline-runs fix):
    the higher, documented-correct baseline lowers NRFI probability across
    the board, so this matchup now lands around 56% instead of the pre-fix
    bug's ~60%+.
    """
    engine = FirstInningValuationEngine()

    pitcher_duel = InningOneMatchupInputs(
        home_team="SEA",
        away_team="HOU",
        home_starter_inn1_era=2.40,
        away_starter_inn1_era=2.60,
        home_top3_woba=0.315,
        away_top3_woba=0.320,
        park_factor=0.92,
    )

    res = engine.evaluate_first_inning(pitcher_duel)

    assert res.nrfi_probability > 0.55
    assert res.recommended_side == "NRFI"
    assert res.fair_nrfi_american < -100


def test_coors_field_slugfest_yields_high_yrfi_probability():
    """Verify high-offense, high-ERA matchup produces elevated YRFI probability."""
    engine = FirstInningValuationEngine()

    coors_game = InningOneMatchupInputs(
        home_team="COL",
        away_team="CIN",
        home_starter_inn1_era=5.20,
        away_starter_inn1_era=4.90,
        home_top3_woba=0.370,
        away_top3_woba=0.365,
        park_factor=1.35,
    )

    res = engine.evaluate_first_inning(coors_game)

    assert res.yrfi_probability > 0.60
    assert res.recommended_side == "YRFI"
    assert res.fair_yrfi_american < 0


def test_default_matchup_baseline_uses_documented_052_constant():
    """Regression test for NRFI-01.

    The class's own default/neutral matchup (no explicit overrides) must
    use the implemented-and-documented 0.52 runs/inning baseline, not the
    pre-fix bug's 0.40 -- the mismatch flipped the engine's own recommended
    side. Before the fix, the default matchup computed nrfi_probability
    ~0.465 and recommended_side "NEUTRAL"; after the fix it computes
    ~0.37 and flips to "YRFI".
    """
    engine = FirstInningValuationEngine()

    default_matchup = InningOneMatchupInputs(home_team="HOME", away_team="AWAY")

    res = engine.evaluate_first_inning(default_matchup)

    assert res.nrfi_probability == 0.37
    assert res.recommended_side == "YRFI"


def test_nrfi_health_check():
    """Verify NRFI health check passes."""
    checks = health_check()
    assert len(checks) == 1
    assert checks[0].ok is True
    assert "NRFI verified" in checks[0].detail
