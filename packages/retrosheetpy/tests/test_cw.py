"""The Chadwick port (``retrosheetpy.cw``): all 164 columns equal captured ``cwevent`` output."""

import csv
from pathlib import Path

import pytest
from retrosheetpy.cw.events import COLUMNS, event_rows
from retrosheetpy.cw.parse import Ev, parse_event
from retrosheetpy.validation import compare_rows

HERE = Path(__file__).parent
FIXTURES = HERE / "fixtures" / "events"
CHADWICK = HERE / "reference" / "chadwick"
NAMES = sorted(p.stem for p in FIXTURES.glob("*.evt"))


def read_rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@pytest.mark.parametrize("name", NAMES)
def test_port_rows_equal_captured_chadwick(name):
    ours = list(event_rows((FIXTURES / f"{name}.evt").read_bytes()))
    result = compare_rows("chadwick 0.10.0", ours, read_rows(CHADWICK / f"{name}.csv"), COLUMNS)
    assert result.games >= 1 and result.games_misaligned == 0
    assert result.plays_compared == len(ours)
    assert result.mismatches == 0, result.to_dict()["fields"]


def test_parse_follows_the_c_rules():
    e, ok = parse_event("64(1)3/GDP/G6")
    assert ok and e.event_type == Ev.GENERICOUT and e.dp_flag and e.gdp_flag
    assert e.putouts[:2] == [4, 3] and e.assists[:2] == [6, 4]
    assert e.play[0] == "43" and e.play[1] == "64" and e.fc_flag[1]

    e, ok = parse_event("SBH(UR)")  # archaic spelling is rewritten to SB4 first
    assert ok and e.advance[3] == 5 and e.sb_flag[3]

    e, ok = parse_event("S9/L9S.2-H;1-3")
    assert ok and e.advance[0] == 1 and e.advance[2] == 4 and e.advance[1] == 3
    assert e.batted_ball_type == "L" and e.hit_location == "9S"


def test_unparseable_play_reports_failure_like_chadwick():
    _, ok = parse_event("ZZ9")
    assert not ok


def test_trailing_blank_in_a_number_is_accepted_like_atoi():
    from retrosheetpy import iter_records

    (rec,) = iter_records(['sub,comoa101,"Adam Comorosky",1,8,12 \n'], source="t.EVN")
    assert rec.position == 12 and rec.raw.endswith("12 ")
