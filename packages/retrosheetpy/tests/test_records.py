import io
import zipfile
from pathlib import Path

import pytest
from retrosheetpy import (
    AdjustmentRecord,
    CommentRecord,
    DataRecord,
    IdRecord,
    InfoRecord,
    ParseError,
    PlayRecord,
    RecordStats,
    StartRecord,
    SubRecord,
    UnsupportedRecord,
    VersionRecord,
    iter_event_zip,
    iter_records,
    read_event_file,
)

FIX = Path(__file__).parent / "fixtures" / "events"
FIXTURES = sorted(FIX.glob("*.evt"))

GAME = [
    b"id,CIN195004180\r\n",
    b"version,1\r\n",
    b"info,visteam,CHN\r\n",
    b'info,umphome,"Smith, Bob"\r\n',
    b'start,aaaaa001,"Al A",0,1,7\r\n',
    b'sub,bbbbb001,"Bo B",1,2,10\r\n',
    b"play,1,0,aaaaa001,22,CBFX,S8/L\r\n",
    b'com,"a note, with comma"\r\n',
    b"data,er,ccccc001,2\r\n",
    b"badj,aaaaa001,L\r\n",
]


def test_typed_records_and_locations():
    recs = list(iter_records(GAME, source="t.EVN"))
    assert [type(r) for r in recs] == [
        IdRecord, VersionRecord, InfoRecord, InfoRecord, StartRecord, SubRecord,
        PlayRecord, CommentRecord, DataRecord, AdjustmentRecord,
    ]  # fmt: skip
    idr, ver, info, info2, start, sub, play, com, data, adj = recs
    assert idr.value == "CIN195004180" and idr.game_id == "CIN195004180"
    assert ver.version == "1"
    assert (info.key, info.value) == ("visteam", "CHN")
    assert info2.value == "Smith, Bob"
    assert (start.player_id, start.name, start.team, start.batting_order, start.position) == (
        "aaaaa001", "Al A", 0, 1, 7,
    )  # fmt: skip
    assert (sub.team, sub.batting_order, sub.position) == (1, 2, 10)
    assert (play.inning, play.team, play.player_id, play.count, play.pitches, play.event) == (
        1, 0, "aaaaa001", "22", "CBFX", "S8/L",
    )  # fmt: skip
    assert com.text == "a note, with comma"
    assert (data.kind, data.fields) == ("er", ("ccccc001", "2"))
    assert (adj.kind, adj.fields) == ("badj", ("aaaaa001", "L"))
    # location + exact raw text (line ending removed, nothing else changed)
    assert play.source == "t.EVN" and play.line_no == 7 and play.game_id == "CIN195004180"
    assert play.raw == "play,1,0,aaaaa001,22,CBFX,S8/L"
    assert info2.raw == 'info,umphome,"Smith, Bob"'


def test_game_id_is_none_before_first_id():
    rec = next(iter_records([b"version,1\r\n"], source="t"))
    assert rec.game_id is None


def test_unknown_record_type_fails_in_strict_mode():
    lines = [b"id,X1\r\n", b"zzz,1,2\r\n"]
    with pytest.raises(ParseError) as ei:
        list(iter_records(lines, source="f.EVN"))
    e = ei.value
    assert (e.source, e.line_no, e.game_id, e.record_type, e.raw, e.stage) == (
        "f.EVN", 2, "X1", "zzz", "zzz,1,2", "record-type",
    )  # fmt: skip


def test_unknown_record_type_is_explicit_in_diagnostic_mode_and_counted():
    stats = RecordStats()
    recs = list(iter_records([b"id,X1\r\n", b"zzz,1,2\r\n"], source="f", strict=False, stats=stats))
    bad = recs[1]
    assert isinstance(bad, UnsupportedRecord)
    assert (bad.record_type, bad.fields, bad.raw) == ("zzz", ("1", "2"), "zzz,1,2")
    assert stats.unsupported["zzz"] == 1 and stats.by_type["id"] == 1 and stats.lines == 2


@pytest.mark.parametrize(
    "line",
    [b"play,1,0,aaaaa001,22\r\n", b'start,a,"N",x,1,7\r\n', b"id\r\n", b"\r\n"],
)
def test_malformed_known_or_blank_lines_are_never_skipped(line):
    with pytest.raises(ParseError):
        list(iter_records([line], source="f"))
    [rec] = list(iter_records([line], source="f", strict=False))
    assert isinstance(rec, UnsupportedRecord) and rec.reason


def test_text_lines_and_lf_only_endings_accepted():
    [rec] = list(iter_records(["version,2\n"], source="f"))
    assert rec.raw == "version,2"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_games_parse_strictly_and_round_trip_raw(path):
    stats = RecordStats()
    recs = list(read_event_file(path, stats=stats))
    original = path.read_bytes().decode("utf-8").splitlines()
    assert [r.raw for r in recs] == original  # lossless
    assert not stats.unsupported
    assert isinstance(recs[0], IdRecord) and len({r.game_id for r in recs}) == 1


def test_fixtures_cover_every_era_and_record_kind():
    seen = set()
    for p in FIXTURES:
        seen |= {r.raw.split(",", 1)[0] for r in read_event_file(p)}
    assert {"id", "version", "info", "start", "sub", "play", "data", "com", "badj",
            "ladj", "presadj"} <= seen  # fmt: skip
    assert {p.stem for p in FIXTURES} >= {
        "regular_2007", "regular_1950", "postseason", "allstar", "deduced", "negro_league",
    }  # fmt: skip


def test_non_ascii_names_preserved():
    names = [
        r.name for r in read_event_file(FIX / "negro_league.evt") if isinstance(r, StartRecord)
    ]
    assert any(not n.isascii() for n in names)


def test_invalid_utf8_bytes_round_trip_losslessly():
    [rec] = list(iter_records([b'com,"caf\xe9"\r\n'], source="f"))
    assert rec.raw.encode("utf-8", "surrogateescape") == b'com,"caf\xe9"'


def test_iter_event_zip_reads_event_members_only(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("1950CIN.EVN", b"".join(GAME))
        zf.writestr("TEAM1950", b"CIN,N,Cincinnati,Reds\r\n")
        zf.writestr("1950CIN.ROS", b"abc,def\r\n")
    p = tmp_path / "x.zip"
    p.write_bytes(buf.getvalue())
    recs = list(iter_event_zip(p))
    assert len(recs) == len(GAME) and {r.source for r in recs} == {"1950CIN.EVN"}
