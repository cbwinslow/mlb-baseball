import json

import pytest
from retrosheetpy import iter_records, parse_play
from retrosheetpy.crosswalk import chadwick_fields, csv_fields
from retrosheetpy.report import build_report, main
from retrosheetpy.validation import compare_chadwick, compare_plays_csv


def cw(event):
    return chadwick_fields(parse_play(event))


def csvf(event):
    return csv_fields(parse_play(event))


def records(*events, game="ABC202001010"):
    lines = [f"id,{game}\r\n"] + [f"play,1,0,aaaaa001,22,CBFX,{e}\r\n" for e in events]
    return list(iter_records(lines, source="f.EVN"))


def test_hit_and_event_codes():
    assert cw("S8/L.1-2")["EVENT_CD"] == 20 and cw("S8/L.1-2")["H_CD"] == 1
    assert cw("DGR/L")["H_CD"] == 2 and cw("DGR/L")["EVENT_CD"] == 21
    assert cw("HR/F78XD")["H_CD"] == 4
    assert cw("K+SB2.B-1(WP)")["EVENT_CD"] == 3  # first event decides
    assert cw("K+SB2.B-1(WP)")["WP_FL"] == "T" and cw("K+SB2")["RUN1_SB_FL"] == "T"


def test_pickoff_codes_follow_observed_cwevent_output():
    assert cw("PO1(13)")["EVENT_CD"] == 8 and cw("PO1(13)")["RUN1_PK_FL"] == "T"
    pocs = cw("POCS2(136)")
    assert pocs["EVENT_CD"] == 8
    assert pocs["RUN1_PK_FL"] == "T" and pocs["RUN1_CS_FL"] == "T"  # origin base, not target


def test_fielder_then_error_is_a_generic_out_for_chadwick():
    assert cw("5E3/G56.B-2")["EVENT_CD"] == 2
    assert cw("E3")["EVENT_CD"] == 18


def test_inferred_fields_are_omitted_not_guessed():
    assert "BATTEDBALL_CD" not in cw("63") and "BATTEDBALL_LOC_TX" not in cw("63")
    f = csvf("7")
    assert "hittype" not in f and "loc" not in f and "ground" not in f


def test_bunts_and_trajectory_without_location():
    assert cw("5/P")["BATTEDBALL_CD"] == "P"
    assert cw("13/SH.2-3")["BUNT_FL"] == "T" and cw("K/BF")["BUNT_FL"] == "T"
    assert "BATTEDBALL_CD" not in cw("K/BF")
    f = csvf("53/BG")
    assert f["bunt"] == 1 and f["ground"] == 0 and f["hittype"] == "BG"


def test_csv_flags():
    f = csvf("W+SB2")
    assert f["walk"] == 1 and f["iw"] == 0 and f["sb2"] == 1
    assert csvf("IW")["iw"] == 1 and csvf("IW")["walk"] == 1
    assert csvf("S9/L9S+")["loc"] == "9S" and csvf("S9/L9S+")["line"] == 1


def test_compare_counts_mismatches_with_examples():
    recs = records("S8/L8", "K")
    rows = [
        {"GAME_ID": "ABC202001010", "EVENT_TX": "S8/L8", "H_CD": "1", "EVENT_CD": "20"},
        {"GAME_ID": "ABC202001010", "EVENT_TX": "K", "H_CD": "0", "EVENT_CD": "2"},
    ]
    res = compare_chadwick(recs, rows, version="x")
    assert res.reference == "chadwick cwevent x" and res.plays_compared == 2
    assert res.fields["EVENT_CD"].compared == 2 and res.fields["EVENT_CD"].mismatches == 1
    assert res.fields["H_CD"].mismatches == 0
    ex = res.fields["EVENT_CD"].examples[0]
    assert ex["event"] == "K" and ex["ours"] == 3 and ex["reference"] == "2"
    assert ex["source"] == "f.EVN:3"


def test_compare_flags_misaligned_and_one_sided_games_and_ignores_np():
    recs = records("NP", "K") + records("S8", game="DEF202001010")
    rows = [
        {"gid": "ABC202001010", "event": "NP", "single": "0"},
        {"gid": "ABC202001010", "event": "K", "single": "0"},
        {"gid": "DEF202001010", "event": "S7", "single": "1"},  # text differs
        {"gid": "ZZZ202001010", "event": "K", "single": "0"},  # no event file
    ]
    res = compare_plays_csv(recs, rows)
    assert (res.games, res.games_misaligned, res.games_only_reference) == (2, 1, 1)
    assert res.misaligned_examples[0]["game_id"] == "DEF202001010"
    assert res.plays_compared == 1  # NP dropped on both sides; misaligned game skipped


def test_csv_location_strength_marker_is_ignored_both_ways():
    recs = records("S9/L9S")
    rows = [{"gid": "ABC202001010", "event": "S9/L9S", "loc": "9S+"}]
    assert compare_plays_csv(recs, rows).mismatches == 0


def test_build_report_and_cli(tmp_path, capsys):
    evt = tmp_path / "x.EVN"
    evt.write_text("id,ABC202001010\r\nplay,1,0,a,22,CBFX,S8/L8\r\nplay,1,0,b,22,CBFX,8/ZZ\r\n")
    ref = tmp_path / "ref.csv"
    ref.write_text("gid,event,single\nABC202001010,S8/L8,0\nABC202001010,8/ZZ,0\n")
    rep = build_report([evt], plays_csv=ref)
    assert rep["plays"]["plays_unsupported"] == 1
    assert "play-modifier:ZZ" in rep["plays"]["unsupported_families"]
    assert rep["reference_mismatches"][0]["mismatches"] == 1  # single: ours 1, csv 0
    assert main([str(evt)]) == 0
    assert json.loads(capsys.readouterr().out)["records"]["by_type"]["play"] == 2


@pytest.mark.parametrize("event", ["", "Q"])
def test_derivation_never_raises_on_unsupported_text(event):
    parse = parse_play(event, strict=False)
    assert chadwick_fields(parse)["EVENT_CD"] == 0
    assert csv_fields(parse)["single"] == 0
