"""markov's public import surface must not change across the package split."""

from mlb_baseball.model import markov

# Every name production code and tests import from `markov` today. If the
# package split drops or renames one, this fails before anything else does.
_EXPECTED = {
    # dataclasses / errors
    "BaseOutState",
    "MarkovError",
    "DegenerateSimulation",
    "TransitionCountRow",
    "Outcome",
    "GameResult",
    "PitchArsenal",
    "BatterArsenalProfile",
    "InGameSimulationResult",
    # constants
    "MATCHUP_PRIOR_PA",
    "TERMINAL",
    "EMPTY_ZERO_OUTS",
    "TRANSIENT_STATES",
    "SIM_MAX_INNINGS",
    # pure computation
    "build_transition_matrix",
    "run_expectancy",
    "build_outcome_distribution",
    "shrink_outcome_distribution",
    "simulate_half_inning_steps",
    "simulate_half_inning",
    "simulate_half_innings",
    "simulate_game",
    "simulate_home_win_rate",
    "summarize_runs",
    "compute_arsenal_matchup_edge",
    "adjust_outcome_distribution_for_matchup",
    "simulate_matchup_game",
    "simulate_in_game_win_probability",
    # DB estimators
    "estimate_transition_matrix",
    "estimate_run_expectancy",
    "estimate_outcome_distribution",
    "fetch_matchup_transition_counts",
    "estimate_matchup_distribution",
    "real_half_inning_runs",
    "real_game_scores",
    "fetch_pitcher_arsenal",
    "fetch_batter_arsenal",
}


def test_markov_exposes_every_expected_name():
    missing = {n for n in _EXPECTED if not hasattr(markov, n)}
    assert not missing, f"markov no longer exports: {sorted(missing)}"
    assert set(markov.__all__) == _EXPECTED, "markov.__all__ drifted from the locked surface"
    assert len(markov.__all__) == len(set(markov.__all__)), "duplicate in markov.__all__"


def test_core_module_has_no_database_code():
    """`markov/core.py` is pure computation -- no psycopg, no SQL loader, no
    db helpers. That is the property the plate-appearance matchup model
    depends on (it reuses core's simulator without a connection). Whole-
    process DB-free import is blocked by mlb_baseball/model/__init__.py and
    is separate work."""
    from pathlib import Path

    src = Path(__file__).parents[2] / "mlb_baseball" / "model" / "markov" / "core.py"
    text = src.read_text()
    forbidden_fragments = (
        "import psycopg",
        "from mlb_baseball.sql",
        "from mlb_baseball.db",
        "read_sql",
    )
    for forbidden in forbidden_fragments:
        assert forbidden not in text, f"markov/core.py must stay DB-free -- found {forbidden!r}"
