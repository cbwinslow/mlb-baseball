import random

import pytest

from mlb_baseball.model.markov import (
    TERMINAL,
    BaseOutState,
    GameResult,
    MarkovError,
    Outcome,
    simulate_game,
)

EMPTY_ZERO = BaseOutState(0, False, False, False)


class _ScriptedRandom:
    """Test double standing in for random.Random: returns a pre-scripted
    sequence of Outcome choices in order, so a game-level test can pin
    down an exact play-by-play sequence across many half-innings without
    fighting real Random's internals. Unlike a bare stub, this enforces
    the same contract real random.Random.choices() has -- k must be 1 (the
    only way simulate_half_inning_steps calls it) and the scripted choice
    must actually be a member of the population it's asked to choose from
    -- so a test can't accidentally script an outcome real sampling could
    never produce, which would make it look like simulate_game handles a
    play it was never actually offered. Raises loudly if the script runs
    out -- a test that under-scripts a sequence should fail clearly, not
    hang or return a wrong value silently."""

    def __init__(self, script: list[Outcome]):
        self._script = list(script)

    def choices(self, population, weights=None, k=1):  # noqa: ARG002
        if k != 1:
            raise AssertionError(f"expected exactly one choice, got k={k}")
        if not self._script:
            raise AssertionError("scripted outcomes exhausted -- script too short for this test")
        chosen = self._script.pop(0)
        if chosen not in population:
            raise AssertionError(
                f"scripted outcome {chosen} is not in the distribution for this state "
                f"({population}) -- add it so this test exercises a real Markov trajectory"
            )
        return [chosen]


def test_simulate_game_plays_nine_innings_when_never_decided_early():
    # Scoreless through 8 full innings, then away scores the game's only
    # run in the top of the 9th and home is scoreless in the bottom --
    # decided exactly at the end of regulation, not tied (which would
    # continue to extras) and not decided early (which would skip or
    # truncate the 9th).
    distribution = {
        EMPTY_ZERO: {Outcome(TERMINAL, 0): 0.9, Outcome(TERMINAL, 1): 0.1},
    }
    script = _ScriptedRandom(
        [Outcome(TERMINAL, 0) for _ in range(16)]  # innings 1-8, both sides
        + [Outcome(TERMINAL, 1)]  # top of the 9th: away scores 1
        + [Outcome(TERMINAL, 0)]  # bottom of the 9th: home scores 0
    )
    result = simulate_game(distribution, script)
    assert result == GameResult(away_runs=1, home_runs=0, innings=9)


def test_simulate_game_skips_the_bottom_of_the_ninth_when_home_already_leads():
    # Home leads 5-3 after 8 complete innings. Script exactly 8 away
    # half-innings and 8 home half-innings summing to 3 and 5
    # respectively, then a top-of-9th scoring 0. Home should never bat in
    # the bottom of the 9th at all -- proven by a script with nothing
    # left for it: if simulate_game tried to draw one more outcome, the
    # scripted double would raise since the script is exhausted exactly
    # after the top of the 9th.
    distribution = {
        EMPTY_ZERO: {
            Outcome(TERMINAL, 0): 0.4,
            Outcome(TERMINAL, 1): 0.3,
            Outcome(TERMINAL, 2): 0.3,
        },
    }
    away_innings = [Outcome(TERMINAL, 1), Outcome(TERMINAL, 1), Outcome(TERMINAL, 1)] + [
        Outcome(TERMINAL, 0)
    ] * 5
    home_innings = [Outcome(TERMINAL, 1), Outcome(TERMINAL, 2), Outcome(TERMINAL, 2)] + [
        Outcome(TERMINAL, 0)
    ] * 5
    script: list[Outcome] = []
    for a, h in zip(away_innings, home_innings, strict=True):
        script.append(a)
        script.append(h)
    script.append(Outcome(TERMINAL, 0))  # top of the 9th only

    result = simulate_game(distribution, _ScriptedRandom(script))

    assert result == GameResult(away_runs=3, home_runs=5, innings=9)


def test_simulate_game_ends_immediately_on_a_walk_off_play():
    # Tied 2-2 entering the bottom of the 9th. The home half-inning is
    # scripted as two plays: a scoreless one, then a 1-run single that
    # immediately wins the game -- the walk-off must end the half-inning
    # right there, not continue drawing outcomes for the rest of the
    # inning (proven by a script with nothing left after the winning
    # play).
    first_out = BaseOutState(1, False, False, False)
    distribution = {
        EMPTY_ZERO: {
            Outcome(TERMINAL, 0): 0.4,
            Outcome(TERMINAL, 1): 0.4,
            Outcome(first_out, 0): 0.2,
        },
        first_out: {Outcome(TERMINAL, 1): 1.0},
    }
    script = (
        [Outcome(TERMINAL, 1)] * 2  # innings 1-2: away scores 1 each
        + [Outcome(TERMINAL, 1)] * 2  # innings 1-2: home scores 1 each -> tied 2-2
        + [Outcome(TERMINAL, 0)] * 12  # innings 3-8 scoreless for both sides (6 x 2)
        + [Outcome(TERMINAL, 0)]  # top of the 9th: away scores 0
        + [Outcome(first_out, 0), Outcome(TERMINAL, 1)]  # bottom 9th: 1 out, then the walk-off
    )
    result = simulate_game(distribution, _ScriptedRandom(script))

    assert result == GameResult(away_runs=2, home_runs=3, innings=9)


def test_simulate_game_continues_to_extra_innings_when_tied():
    # Tied after 9 (0-0 through 9 full innings, 18 scripted plays), then
    # away scores 1 and home scores 0 in the 10th -- the game must
    # continue past regulation and end 1-0 in 10, not stop at 9.
    distribution = {
        EMPTY_ZERO: {Outcome(TERMINAL, 0): 0.9, Outcome(TERMINAL, 1): 0.1},
    }
    script = [Outcome(TERMINAL, 0) for _ in range(18)] + [
        Outcome(TERMINAL, 1),
        Outcome(TERMINAL, 0),
    ]
    result = simulate_game(distribution, _ScriptedRandom(script))
    assert result == GameResult(away_runs=1, home_runs=0, innings=10)


def test_simulate_game_rejects_a_non_positive_regulation_innings():
    distribution = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    with pytest.raises(MarkovError, match="regulation_innings"):
        simulate_game(distribution, _ScriptedRandom([]), regulation_innings=0)


def test_simulate_game_rejects_a_max_innings_below_regulation_innings():
    distribution = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    with pytest.raises(MarkovError, match="max_innings"):
        simulate_game(distribution, _ScriptedRandom([]), regulation_innings=9, max_innings=8)


def test_simulate_game_raises_rather_than_hang_forever_on_a_perpetual_tie():
    # A degenerate distribution where every half-inning is guaranteed
    # scoreless can never break a tie -- real random.Random (not scripted)
    # is used here specifically to prove this terminates via the
    # max_innings guard rather than "getting lucky" with a scripted
    # sequence. Real, non-degenerate estimated distributions always carry
    # some probability of differing run totals between innings, so this
    # is a defensive bound against a narrow/degenerate distribution, not
    # a realistic production scenario -- but simulate_half_inning already
    # refuses to silently hang on a dead-end state, and this extends that
    # same "fail loudly, don't hang" contract to the game level.
    distribution = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
    with pytest.raises(MarkovError, match="max_innings"):
        simulate_game(distribution, random.Random(0), max_innings=5)
