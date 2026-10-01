"""State engine checks: whole-row equality with captured Chadwick output, plus unit rules."""

import csv
from pathlib import Path

import pytest
from implemented_fields import IMPLEMENTED
from retrosheetpy import ParseError, iter_records, read_event_file
from retrosheetpy.state import StateError, event_rows
from retrosheetpy.validation import compare_rows

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures" / "events"
CHADWICK = HERE / "reference" / "chadwick"
NAMES = sorted(p.stem for p in FIXTURES.glob("*.evt"))


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("name", NAMES)
def test_engine_rows_equal_captured_chadwick(name):
    ours = list(event_rows(read_event_file(FIXTURES / f"{name}.evt")))
    result = compare_rows("chadwick 0.10.0", ours, read_rows(CHADWICK / f"{name}.csv"), IMPLEMENTED)
    assert result.games == 1 and result.games_misaligned == 0
    assert result.plays_compared == len(ours)
    assert result.mismatches == 0, result.to_dict()["fields"]


def game(*lines):
    head = [
        "id,TST202001010",
        "info,visteam,AAA",
        "info,hometeam,TST",
        "start,a1,A1,0,1,4",
        "start,a2,A2,0,2,6",
        "start,ap,AP,0,0,1",
        "start,h1,H1,1,1,8",
        "start,h2,H2,1,2,3",
        "start,hp,HP,1,0,1",
    ]
    return list(iter_records([f"{x}\n" for x in [*head, *lines]], source="t.EVN"))


def rows(*lines, strict=True):
    return list(event_rows(game(*lines), strict=strict))


def test_outs_and_runs_carry_across_plays():
    r = rows(
        "play,1,0,a1,00,,S8", "play,1,0,a2,00,,D7.1-H", "play,1,0,a1,00,,K", "play,1,1,h1,00,,K"
    )
    assert [x["OUTS_CT"] for x in r] == ["0", "0", "0", "0"]
    assert [x["AWAY_SCORE_CT"] for x in r] == ["0", "0", "1", "1"]
    assert r[2]["BASE2_RUN_ID"] == "a2" and r[2]["EVENT_OUTS_CT"] == "1"
    assert r[3]["BAT_HOME_ID"] == "1" and r[3]["OUTS_CT"] == "0"  # new half-inning clears outs


def test_walk_forces_only_the_runners_in_the_way():
    r = rows("play,1,0,a1,00,,S8", "play,1,0,a2,00,,W", "play,1,0,a1,00,,W")
    assert (r[2]["RUN1_DEST_ID"], r[2]["RUN2_DEST_ID"], r[2]["BAT_DEST_ID"]) == ("2", "3", "1")


def test_pinch_runner_takes_the_base():
    r = rows("play,1,0,a1,00,,S8", "sub,a3,A3,0,1,12", "play,1,0,a2,00,,K")
    assert r[1]["BASE1_RUN_ID"] == "a3"


def test_strict_mode_rejects_runner_from_an_empty_base():
    with pytest.raises(StateError, match="empty base"):
        rows("play,1,0,a1,00,,S8.2-3")


def test_np_is_not_emitted():
    assert len(rows("play,1,0,a1,00,,NP", "play,1,0,a1,00,,K")) == 1


def test_strict_mode_rejects_unsupported_syntax():
    with pytest.raises(ParseError, match="unsupported"):
        rows("play,1,0,a1,00,,ZZ9")


def test_diagnostic_mode_marks_the_play_and_later_rows():
    r = rows("play,1,0,a1,00,,S8", "play,1,0,a2,00,,ZZ9", "play,1,0,a1,00,,K", strict=False)
    assert r[0]["UNSUPPORTED"] == "" and r[0]["STATE_UNCERTAIN"] == "F"
    assert "unsupported" in r[1]["UNSUPPORTED"] and r[1]["EVENT_OUTS_CT"] == ""  # not guessed
    assert r[2]["STATE_UNCERTAIN"] == "T" and r[2]["UNSUPPORTED"] == ""
    assert r[2]["BASE1_RUN_ID"] == "a1"  # last known state, flagged as uncertain


def test_diagnostic_mode_marks_an_impossible_advance_too():
    r = rows("play,1,0,a1,00,,S8.2-3", strict=False)
    assert "empty base" in r[0]["UNSUPPORTED"]
