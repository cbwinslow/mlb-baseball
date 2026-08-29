"""Pure helpers for the upcoming-game Markov writer (ADR-272)."""

from mlb_baseball.model.sim_predict import rng_for, seasons_for


def test_seasons_for_includes_the_game_season_and_the_prior_year():
    assert seasons_for(2026) == [2025, 2026]
    assert seasons_for(2024) == [2023, 2024]


def test_rng_for_is_stable_for_the_same_game_pk():
    first = rng_for("718234").random()
    second = rng_for("718234").random()
    other = rng_for("718235").random()
    assert first == second
    assert first != other
