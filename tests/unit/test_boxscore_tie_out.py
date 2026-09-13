"""The event_type -> counting-stat map in scripts/verify_mlb_boxscore_tie_out.py.

The map is the load-bearing part of the 2026 play-by-play cross-check gate:
an event it classifies wrong silently biases the reconstruction, and an event
it does not know must fail loudly rather than count as zero.
"""

import pytest

from scripts.verify_mlb_boxscore_tie_out import (
    FIELDS,
    Line,
    UnmappedEventType,
    classify,
)


def _line(event_type):
    line = Line()
    line.add(classify(event_type))
    return line.as_dict()


def test_field_error_is_an_at_bat_with_no_hit():
    # batter reaches on a fielder's error: PA and AB, but not a hit.
    assert _line("field_error") == {**dict.fromkeys(FIELDS, 0), "pa": 1, "ab": 1}


def test_fielders_choice_and_force_out_are_at_bats():
    for et in ("fielders_choice", "fielders_choice_out", "force_out"):
        assert _line(et) == {**dict.fromkeys(FIELDS, 0), "pa": 1, "ab": 1}, et


def test_catcher_interference_is_a_plate_appearance_but_not_an_at_bat():
    assert _line("catcher_interf") == {**dict.fromkeys(FIELDS, 0), "pa": 1}


def test_empty_event_type_counts_as_nothing():
    # inning-ending / placeholder plays carry an empty event_type -- a known,
    # small edge case covered by the gate's tolerance, never a hard failure.
    assert _line("") == dict.fromkeys(FIELDS, 0)
    assert _line(None) == dict.fromkeys(FIELDS, 0)


def test_common_events_classify_as_expected():
    assert _line("single") == {**dict.fromkeys(FIELDS, 0), "pa": 1, "ab": 1, "h": 1}
    assert _line("home_run") == {**dict.fromkeys(FIELDS, 0), "pa": 1, "ab": 1, "h": 1, "hr": 1}
    assert _line("strikeout") == {**dict.fromkeys(FIELDS, 0), "pa": 1, "ab": 1, "so": 1}
    assert _line("walk") == {**dict.fromkeys(FIELDS, 0), "pa": 1, "bb": 1}
    assert _line("hit_by_pitch") == {**dict.fromkeys(FIELDS, 0), "pa": 1, "hbp": 1}
    assert _line("sac_fly") == {**dict.fromkeys(FIELDS, 0), "pa": 1, "sf": 1}
    assert _line("sac_bunt") == {**dict.fromkeys(FIELDS, 0), "pa": 1, "sh": 1}


def test_baserunning_events_are_not_plate_appearances():
    for et in ("caught_stealing_2b", "wild_pitch", "pickoff_1b", "stolen_base_2b", "mound_visit"):
        assert _line(et) == dict.fromkeys(FIELDS, 0), et


def test_unknown_event_type_fails_loudly():
    with pytest.raises(UnmappedEventType):
        classify("teleport_to_second")
