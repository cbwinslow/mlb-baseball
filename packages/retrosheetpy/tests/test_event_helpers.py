"""The small ``cw_event_*`` helpers of ``parse.c`` (``is_official_ab`` to ``rbi_on_play``).

Chadwick's own tools never call them, so no differential run reaches them; the expected values
are read off the C definitions (``parse.c`` lines 103-153) for plays whose answer is clear.
"""

import pytest
from retrosheetpy.cw.parse import (
    is_official_ab,
    outs_on_play,
    parse_event,
    rbi_on_play,
    runner_put_out,
    runs_on_play,
)


def parsed(text: str):  # noqa: ANN201
    event, ok = parse_event(text)
    assert ok
    return event


@pytest.mark.parametrize(
    ("play", "official"),
    [("S8", True), ("K", True), ("8/F", True), ("8/SF", False), ("W", False), ("IW", False),
     ("HP", False), ("C/E2", False), ("SB2", False), ("54(1)3/SH", False)],
)  # fmt: skip
def test_official_at_bat(play: str, official: bool) -> None:
    assert is_official_ab(parsed(play)) is official


def test_outs_runs_and_rbi_counted_from_the_parsed_play() -> None:
    dp = parsed("64(1)3/GDP")
    assert outs_on_play(dp) == 2
    assert runner_put_out(dp, 1)
    assert not runner_put_out(dp, 2)
    homer = parsed("HR.2-H;1-H")
    assert runs_on_play(homer) == 3
    assert rbi_on_play(homer) == 3
    assert outs_on_play(homer) == 0
    error = parsed("S8.1X2(E6)")  # a runner "out" with an error is not an out
    assert not runner_put_out(error, 1)
    assert outs_on_play(error) == 0
