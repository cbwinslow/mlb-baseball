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
    sequence of Outcome choices in order, ignoring the population/weights
    it's called with, so a game-level test can pin down an exact
    play-by-play sequence across many half-innings without fighting real
    Random's internals. Raises loudly if the script runs out -- a test
    that under-scripts a sequence should fail clearly, not hang or return
    a wrong value silently."""

    def __init__(self, script: list[Outcome]):
        self._script = list(script)

    def choices(self, population, weights=None, k=1):  # noqa: ARG002
        if not self._script:
            raise AssertionError("scripted outcomes exhausted -- script too short for this test")
        return [self._script.pop(0)]


def test_simulate_game_plays_nine_innings_when_never_decided_early():
    # Scoreless through 8 full innings, then away scores the game's only
    # run in the top of the 9th and home is scoreless in the bottom --
    # decided exactly at the end of regulation, not tied (which would
    # continue to extras) and not decided early (which would skip or
    # truncate the 9th).
    distribution = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
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
    distribution = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
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
        EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0},
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
    distribution = {EMPTY_ZERO: {Outcome(TERMINAL, 0): 1.0}}
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
