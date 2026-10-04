import pytest

from mlb_baseball.timing import timed, timed_step


def test_timed_prints_label_even_when_the_block_fails(capsys):
    with pytest.raises(ValueError), timed("predict", "gbm"):
        raise ValueError("boom")
    assert capsys.readouterr().out.startswith("predict step gbm: ")


def test_timed_step_labels_by_function_name_or_argument(capsys):
    @timed_step("report")
    def _build_thing():
        return 1

    @timed_step("report", 1)
    def build(conn, table):
        return 2

    assert (_build_thing(), build(None, "gold.x")) == (1, 2)
    out = capsys.readouterr().out
    assert "report step build_thing: " in out
    assert "report step gold.x: " in out
