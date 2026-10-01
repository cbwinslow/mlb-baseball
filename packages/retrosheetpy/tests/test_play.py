"""Play-syntax tests. Examples come from Retrosheet's event-file documentation
(https://www.retrosheet.org/eventfile.htm) and from captured source records."""

from pathlib import Path

import pytest
from retrosheetpy import (
    AdvanceKind,
    EventKind,
    ModifierKind,
    ParamKind,
    ParseError,
    PlayRecord,
    iter_records,
    parse_play,
    parse_play_record,
    read_event_file,
)

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "events").glob("*.evt"))


def kinds(play):
    return [e.kind for e in play.events]


def test_documented_hit_with_location_and_advances():
    p = parse_play("S9/L9S.2-H;1-3")
    assert kinds(p) == [EventKind.SINGLE] and p.events[0].fielders == "9"
    assert [(m.kind, m.code, m.location) for m in p.modifiers] == [
        (ModifierKind.TRAJECTORY, "L", "9S")
    ]
    assert [(a.kind, a.from_base, a.to_base) for a in p.advances] == [
        (AdvanceKind.SAFE, "2", "H"),
        (AdvanceKind.SAFE, "1", "3"),
    ]
    assert p.rebuild() == p.raw == "S9/L9S.2-H;1-3"


@pytest.mark.parametrize(
    "text,kind,fielders",
    [
        ("8/F78", EventKind.FIELDED_OUT, "8"),
        ("63/G6M", EventKind.FIELDED_OUT, "63"),
        ("143/G1", EventKind.FIELDED_OUT, "143"),
        ("S7", EventKind.SINGLE, "7"),
        ("D7/G5.3-H;2-H;1-H", EventKind.DOUBLE, "7"),
        ("T9/F9LD.2-H", EventKind.TRIPLE, "9"),
        ("DGR/L9LS.2-H", EventKind.GROUND_RULE_DOUBLE, ""),
        ("H/L7D", EventKind.HOME_RUN, ""),
        ("HR/F78XD.2-H;1-H", EventKind.HOME_RUN, ""),
        ("HR9/F9LS.3-H;1-H", EventKind.HOME_RUN, "9"),
        ("FC5/G5.3XH(52)", EventKind.FIELDERS_CHOICE, "5"),
        ("FLE5/P5F", EventKind.FOUL_FLY_ERROR, "5"),
        ("HP.1-2", EventKind.HIT_BY_PITCH, ""),
        ("K", EventKind.STRIKEOUT, ""),
        ("K23", EventKind.STRIKEOUT, "23"),
        ("NP", EventKind.NO_PLAY, ""),
        ("W.1-2", EventKind.WALK, ""),
        ("IW", EventKind.INTENTIONAL_WALK, ""),
        ("I", EventKind.INTENTIONAL_WALK, ""),
        ("BK.3-H;1-2", EventKind.BALK, ""),
        ("DI.1-2", EventKind.DEFENSIVE_INDIFFERENCE, ""),
        ("OA.2X3(25)", EventKind.OTHER_ADVANCE, ""),
        ("PB.2-3", EventKind.PASSED_BALL, ""),
        ("WP.2-3;1-2", EventKind.WILD_PITCH, ""),
        ("C/E2.1-2", EventKind.CATCHER_INTERFERENCE, ""),
    ],
)
def test_documented_primary_events(text, kind, fielders):
    p = parse_play(text)
    assert kinds(p) == [kind] and p.events[0].fielders == fielders
    assert p.rebuild() == text


def test_error_events_with_and_without_assists():
    e = parse_play("E1/TH/BG15.1-3").events[0]
    assert (e.kind, e.fielders, e.error_fielder) == (EventKind.ERROR, "", "1")
    e = parse_play("3E1").events[0]
    assert (e.fielders, e.error_fielder) == ("3", "1")


def test_fielded_out_chains_with_runner_outs():
    e = parse_play("64(1)3/GDP/G6").events[0]
    assert [(s.fielders, s.runner) for s in e.chain] == [("64", "1"), ("3", None)]
    e = parse_play("54(B)/BG25/SH.1-2").events[0]
    assert [(s.fielders, s.runner) for s in e.chain] == [("54", "B")]
    e = parse_play("1(B)16(2)63(1)/LTP/L1").events[0]
    assert [(s.fielders, s.runner) for s in e.chain] == [("1", "B"), ("16", "2"), ("63", "1")]
    e = parse_play("3(B)3(1)/LDP").events[0]
    assert [(s.fielders, s.runner) for s in e.chain] == [("3", "B"), ("3", "1")]


@pytest.mark.parametrize(
    "text,kind,base,params",
    [
        ("SB2", EventKind.STOLEN_BASE, "2", []),
        ("SBH", EventKind.STOLEN_BASE, "H", []),
        ("CSH(12)", EventKind.CAUGHT_STEALING, "H", ["12"]),
        ("CS2(2E4).1-3", EventKind.CAUGHT_STEALING, "2", ["2E4"]),
        ("PO2(14)", EventKind.PICKOFF, "2", ["14"]),
        ("PO1(E3).1-2", EventKind.PICKOFF, "1", ["E3"]),
        ("PO2(E1/TH)", EventKind.PICKOFF, "2", ["E1/TH"]),
        ("POCS2(1361)", EventKind.PICKOFF_CAUGHT_STEALING, "2", ["1361"]),
        ("SBH(UR);SB2", EventKind.STOLEN_BASE, "H", ["UR"]),
    ],
)
def test_base_running_events(text, kind, base, params):
    e = parse_play(text).events[0]
    assert (e.kind, e.base, [p.text for p in e.params]) == (kind, base, params)


def test_semicolon_joined_steals_are_separate_events():
    p = parse_play("SB3;SB2")
    assert [(e.kind, e.base) for e in p.events] == [
        (EventKind.STOLEN_BASE, "3"),
        (EventKind.STOLEN_BASE, "2"),
    ]
    assert p.rebuild() == "SB3;SB2"


@pytest.mark.parametrize(
    "text,follow_kind",
    [
        ("K+PB.1-2", EventKind.PASSED_BALL),
        ("K+WP.B-1", EventKind.WILD_PITCH),
        ("K23+WP.2-3", EventKind.WILD_PITCH),
        ("W+WP.2-3", EventKind.WILD_PITCH),
        ("W+PB.3-H(NR);1-3", EventKind.PASSED_BALL),
        ("K+SB2", EventKind.STOLEN_BASE),
        ("K+CS2(24)", EventKind.CAUGHT_STEALING),
        ("K+PO1(E3)", EventKind.PICKOFF),
        ("IW+WP", EventKind.WILD_PITCH),
    ],
)
def test_follow_on_events(text, follow_kind):
    e = parse_play(text).events[0]
    assert e.follow_on is not None and e.follow_on.kind is follow_kind
    assert e.kind in (EventKind.STRIKEOUT, EventKind.WALK, EventKind.INTENTIONAL_WALK)


def test_strikeout_with_two_follow_on_steals():
    p = parse_play("K+SB2;SB3")
    assert len(p.events) == 2 and p.events[0].follow_on.kind is EventKind.STOLEN_BASE
    assert p.rebuild() == "K+SB2;SB3"


def test_modifiers_documented_codes_and_locations():
    p = parse_play("8/SF.3-H")
    assert [(m.kind, m.code) for m in p.modifiers] == [(ModifierKind.CODE, "SF")]
    p = parse_play("D8/78")
    assert [(m.kind, m.location) for m in p.modifiers] == [(ModifierKind.LOCATION, "78")]
    p = parse_play("64(1)3/GDP/G6")
    assert [m.code for m in p.modifiers] == ["GDP", "G"] and p.modifiers[1].location == "6"
    p = parse_play("E1/TH/BG15.1-3")
    assert [(m.kind, m.code) for m in p.modifiers] == [
        (ModifierKind.CODE, "TH"),
        (ModifierKind.TRAJECTORY, "BG"),
    ]
    assert p.modifiers[1].location == "15"


def test_modifier_hit_strength_and_error_throw_relay():
    m = parse_play("8/G+").modifiers[0]
    assert (m.code, m.strength) == ("G", "hard")
    assert parse_play("8/F-").modifiers[0].strength == "soft"
    assert parse_play("C/E2.1-2").modifiers[0].fielders == "2"
    m = parse_play("E5/THH").modifiers[0]
    assert (m.kind, m.base) == (ModifierKind.THROW, "H")
    m = parse_play("S8/R64").modifiers[0]
    assert (m.kind, m.fielders) == (ModifierKind.RELAY, "64")


def test_advances_outs_and_parameters():
    p = parse_play("S8/L78.BX2(8434)")
    a = p.advances[0]
    assert (a.kind, a.from_base, a.to_base) == (AdvanceKind.OUT, "B", "2")
    assert [(x.kind, x.text) for x in a.params] == [(ParamKind.FIELDING, "8434")]
    p = parse_play("S4/G34.2-H(E4/TH)(UR)(NR);1-3;B-2")
    assert [x.kind for x in p.advances[0].params] == [
        ParamKind.ERROR,
        ParamKind.UNEARNED,
        ParamKind.NO_RBI,
    ]
    assert len(p.advances) == 3
    p = parse_play("E6/G6.3-H(RBI);2-3;B-1")
    assert p.advances[0].params[0].kind is ParamKind.RBI
    p = parse_play("S9.3-H(TUR);2-H(TUR);1-3;BX2(93)")
    assert [a.params[0].kind for a in p.advances[:2]] == [ParamKind.UNEARNED] * 2
    p = parse_play("K.1-2(WP)")
    assert p.advances[0].params[0].kind is ParamKind.WILD_PITCH
    p = parse_play("S/L9S.3-H;2X3(5/INT);1-2")
    assert p.advances[1].params[0].kind is ParamKind.INTERFERENCE
    p = parse_play("S7/L7LD.3-H;2-H;BX2(7E4)")
    assert p.advances[2].params[0].kind is ParamKind.ERROR
    p = parse_play("S8.2-H;BX2(8U3)")
    assert p.advances[1].params[0].kind is ParamKind.FIELDING


def test_markers_are_recorded_and_ignored_for_meaning():
    p = parse_play("PB.2-3#")
    assert p.markers == "#" and p.advances[0].to_base == "3" and p.rebuild() == "PB.2-3#"
    p = parse_play("6!3/G6")
    assert p.markers == "!" and p.events[0].fielders == "63"
    p = parse_play("8/F78XD.1X2(E4)!")
    assert "!" in p.markers and p.rebuild() == p.raw


def test_unknown_syntax_strict_raises_with_stage_token_and_offset():
    with pytest.raises(ParseError) as ei:
        parse_play("8/ZZ.1-2")
    e = ei.value
    assert (e.stage, e.token, e.offset, e.raw, e.record_type) == (
        "play-modifier", "ZZ", 2, "8/ZZ.1-2", "play",
    )  # fmt: skip
    with pytest.raises(ParseError) as ei:
        parse_play("QQ")
    assert ei.value.stage == "play-event"
    with pytest.raises(ParseError) as ei:
        parse_play("S8.1-9")
    assert ei.value.stage == "play-advance"
    with pytest.raises(ParseError) as ei:
        parse_play("S8.1-2(WHAT)")
    assert ei.value.stage == "play-param"


def test_unknown_follow_on_event_is_not_hidden():
    with pytest.raises(ParseError) as ei:
        parse_play("K+ZZ.1-2")
    assert (ei.value.stage, ei.value.token) == ("play-event", "ZZ")
    assert parse_play("K+ZZ", strict=False).unsupported() == ["ZZ"]


def test_unknown_syntax_lenient_keeps_raw_and_reports_it():
    p = parse_play("QQ/ZZ.1-9", strict=False)
    assert p.unsupported() == ["QQ", "ZZ", "1-9"]
    assert p.events[0].kind is EventKind.UNKNOWN and p.rebuild() == "QQ/ZZ.1-9"


def test_error_context_comes_from_the_record():
    lines = [b"id,G1\r\n", b"play,1,0,aaaaa001,22,CBFX,QQ\r\n"]
    play_rec = list(iter_records(lines, source="x.EVN"))[1]
    assert isinstance(play_rec, PlayRecord)
    with pytest.raises(ParseError) as ei:
        parse_play_record(play_rec)
    assert (ei.value.source, ei.value.line_no, ei.value.game_id) == ("x.EVN", 2, "G1")


def test_parsing_does_not_touch_game_state():
    p = parse_play("S9/L9S.2-H;1-3")
    # Syntax only: no outs, runs or base state exist on the result.
    assert not hasattr(p, "outs") and not hasattr(p, "runs") and not hasattr(p, "bases")


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_every_fixture_play_parses_strictly_and_rebuilds_exactly(path):
    n = 0
    for rec in read_event_file(path):
        if isinstance(rec, PlayRecord):
            p = parse_play_record(rec)
            assert p.rebuild() == rec.event and not p.unsupported()
            n += 1
    assert n > 20
