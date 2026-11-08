"""A forced Retrosheet refresh of an unchanged archive must not re-parse or re-write."""

from unittest.mock import Mock, patch

import pandas as pd

from mlb_baseball import manifest
from mlb_baseball.connectors import retrosheet_event


def _frames() -> dict:
    event = pd.DataFrame({"game_id": ["A"], "_scope": ["2020_pbp"]})
    game = pd.DataFrame({"game_id": ["A"], "_scope": ["2020_pbp"]})
    return {2020: (event, game)}


def _run(tmp_path, monkeypatch, content: bytes):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    response = Mock(status_code=200, content=content)
    response.raise_for_status = Mock()
    parse = Mock(return_value=_frames())
    load = Mock(return_value=1)
    with (
        patch.object(manifest, "get_with_retry", return_value=response),
        patch.object(retrosheet_event, "_parse_archive", parse),
        patch.object(retrosheet_event, "load_dataframe", load),
    ):
        counts = retrosheet_event._load_archive(
            Mock(), "2020seve.zip", "http://x/2020seve.zip", "pbp", force=True
        )
    return counts, parse, load


def test_forced_refresh_of_unchanged_archive_writes_nothing(tmp_path, monkeypatch):
    first, parse1, _ = _run(tmp_path, monkeypatch, b"same bytes")
    assert first[retrosheet_event.EVENT_TABLE] == 1
    assert parse1.called

    second, parse2, load2 = _run(tmp_path, monkeypatch, b"same bytes")
    assert second == {}
    assert not parse2.called
    assert not load2.called
    entry = manifest.load_manifest(retrosheet_event.SOURCE)["2020seve.zip"]
    assert entry["status"] == "loaded"
    assert entry["parser_version"] == retrosheet_event.PARSER_VERSION


def test_forced_refresh_of_changed_archive_reloads(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, b"old bytes")
    counts, parse, load = _run(tmp_path, monkeypatch, b"corrected bytes")
    assert parse.called
    assert load.called
    assert counts[retrosheet_event.EVENT_TABLE] == 1
