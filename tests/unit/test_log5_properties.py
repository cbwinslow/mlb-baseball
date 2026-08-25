"""Generative invariants for the canonical Log5 probability formula.

These tests complement the hand-calculated examples in ``test_log5_formula``.
They protect properties that must hold for every valid winning percentage,
including early-season edge cases at zero and one.
"""

from decimal import Decimal

from hypothesis import assume, given
from hypothesis import strategies as st

from mlb_baseball.model.log5 import probability

PROBABILITIES = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)
INTERIOR_PROBABILITIES = st.decimals(
    min_value=Decimal("0.000001"),
    max_value=Decimal("0.999999"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)
TOLERANCE = Decimal("1e-24")


@given(home=PROBABILITIES, away=PROBABILITIES)
def test_log5_probability_is_bounded(home: Decimal, away: Decimal) -> None:
    """Every valid pair, including degenerate equal extremes, returns a probability."""
    result = probability(home, away)
    assert Decimal("0") <= result <= Decimal("1")


@given(home=PROBABILITIES, away=PROBABILITIES)
def test_log5_swapping_teams_complements_probability(home: Decimal, away: Decimal) -> None:
    """Changing home and away swaps the mutually exclusive win event."""
    combined = probability(home, away) + probability(away, home)
    assert abs(combined - Decimal("1")) <= TOLERANCE


@given(win_pct=PROBABILITIES)
def test_log5_against_league_average_equals_own_win_pct(win_pct: Decimal) -> None:
    """This is Log5's defining calibration identity: P(x, .500) = x."""
    assert probability(win_pct, Decimal("0.5")) == win_pct


@given(win_pct=PROBABILITIES)
def test_log5_equal_teams_are_even_at_every_valid_record(win_pct: Decimal) -> None:
    """Equal records must be an even matchup, including 0-0 and 1-1 cases."""
    assert probability(win_pct, win_pct) == Decimal("0.5")


@given(away=INTERIOR_PROBABILITIES, first=PROBABILITIES, second=PROBABILITIES)
def test_log5_is_strictly_increasing_in_home_win_pct(
    away: Decimal, first: Decimal, second: Decimal
) -> None:
    """Against a fixed non-degenerate opponent, a stronger home record helps."""
    assume(first != second)
    lower, higher = sorted((first, second))
    assert probability(lower, away) < probability(higher, away)
