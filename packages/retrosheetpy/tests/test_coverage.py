from retrosheetpy import PlayCoverage, iter_records


def play_lines(*events):
    yield b"id,G1\r\n"
    for e in events:
        yield f"play,1,0,aaaaa001,22,CBFX,{e}\r\n".encode()


def test_counts_plays_and_groups_unsupported_by_family():
    cov = PlayCoverage()
    cov.add_records(
        iter_records(play_lines("S8/L.1-2", "8/R64", "8/R65", "8/ZZ", "K"), source="f.EVN")
    )
    assert cov.plays == 5 and cov.plays_unsupported == 1
    d = cov.to_dict()
    assert d["plays_parsed"] == 4
    assert list(d["unsupported_families"]) == ["play-modifier:ZZ"]
    assert d["unsupported_families"]["play-modifier:ZZ"] == {
        "count": 1,
        "example": "8/ZZ",
        "source": "f.EVN:5",
    }


def test_digit_runs_collapse_into_one_family():
    cov = PlayCoverage()
    cov.add_records(iter_records(play_lines("8/B25", "8/B1S", "8/B23"), source="f"))
    assert cov.families["play-modifier:B$"].count == 2
    assert cov.families["play-modifier:B$S"].count == 1
