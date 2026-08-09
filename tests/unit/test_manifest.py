from unittest.mock import Mock, patch

import pytest

from mlb_baseball import manifest


def test_download_writes_file_and_records_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    fake_response = Mock(status_code=200, content=b"hello world")
    with patch.object(manifest, "get_with_retry", return_value=fake_response) as mock_get:
        dest = manifest.download("retrosheet", "2025csvs.zip", "https://example.com/2025csvs.zip")

    assert dest == tmp_path / "retrosheet" / "2025csvs.zip"
    assert dest.read_bytes() == b"hello world"
    mock_get.assert_called_once_with("https://example.com/2025csvs.zip")

    entry = manifest.load_manifest("retrosheet")["2025csvs.zip"]
    assert entry["status"] == "downloaded"
    assert entry["bytes"] == 11
    assert entry["url"] == "https://example.com/2025csvs.zip"
    assert not list((tmp_path / "retrosheet").glob("*.tmp"))


def test_save_manifest_replaces_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)

    manifest.save_manifest("retrosheet", {"one": {"status": "downloaded"}})

    assert manifest.load_manifest("retrosheet") == {"one": {"status": "downloaded"}}
    assert not (tmp_path / "retrosheet" / "manifest.json.tmp").exists()


def test_persist_artifact_atomically_records_generated_json_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)

    path, entry = manifest.persist_artifact(
        "mlb_api",
        "analytics/1967/batch-00001.ndjson.gz",
        b"compressed-json",
        url="https://statsapi.mlb.com/api/v1/game/{gamePk}/winProbability",
        metadata={"parser_version": "test-v1", "records": 2},
    )

    assert path.read_bytes() == b"compressed-json"
    assert entry["parser_version"] == "test-v1"
    assert manifest.load_manifest("mlb_api")["analytics/1967/batch-00001.ndjson.gz"]["records"] == 2
    assert not list(path.parent.glob("*.tmp"))


def test_download_skips_network_when_hash_matches_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    fake_response = Mock(status_code=200, content=b"same bytes")
    with patch.object(manifest, "get_with_retry", return_value=fake_response) as mock_get:
        manifest.download("retrosheet", "f.zip", "https://example.com/f.zip")
        mock_get.reset_mock()
        dest = manifest.download("retrosheet", "f.zip", "https://example.com/f.zip")

    assert dest.read_bytes() == b"same bytes"
    mock_get.assert_not_called()


def test_download_refetches_when_disk_file_was_modified_or_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    fake_response = Mock(status_code=200, content=b"original")
    with patch.object(manifest, "get_with_retry", return_value=fake_response):
        dest = manifest.download("retrosheet", "f.zip", "https://example.com/f.zip")
    dest.unlink()

    with patch.object(manifest, "get_with_retry", return_value=fake_response) as mock_get:
        manifest.download("retrosheet", "f.zip", "https://example.com/f.zip")

    mock_get.assert_called_once()


def test_download_returns_none_on_404(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    fake_response = Mock(status_code=404)
    with patch.object(manifest, "get_with_retry", return_value=fake_response):
        result = manifest.download("retrosheet", "2099csvs.zip", "https://example.com/2099csvs.zip")

    assert result is None
    assert manifest.load_manifest("retrosheet") == {}


def test_download_required_raises_clearly_on_404(tmp_path, monkeypatch):
    # A must-exist file (rosters.zip, tranDB.zip, ...) 404ing means the
    # source moved or broke — the failure must name the source and URL, not
    # surface later as a TypeError from ZipFile(None).
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    fake_response = Mock(status_code=404)
    with patch.object(manifest, "get_with_retry", return_value=fake_response):
        with pytest.raises(RuntimeError, match=r"rosters\.zip.*404.*example\.com"):
            manifest.download_required(
                "retrosheet_roster", "rosters.zip", "https://example.com/rosters.zip"
            )


def test_download_required_returns_path_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    fake_response = Mock(status_code=200, content=b"zip bytes")
    with patch.object(manifest, "get_with_retry", return_value=fake_response):
        dest = manifest.download_required(
            "retrosheet_roster", "rosters.zip", "https://example.com/rosters.zip"
        )

    assert dest == tmp_path / "retrosheet_roster" / "rosters.zip"
    assert dest.read_bytes() == b"zip bytes"


def test_download_force_refetches_even_when_hash_matches_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    fake_response = Mock(status_code=200, content=b"same bytes")
    with patch.object(manifest, "get_with_retry", return_value=fake_response) as mock_get:
        manifest.download("retrosheet_event", "2020seve.zip", "https://example.com/2020seve.zip")
        mock_get.reset_mock()
        manifest.download(
            "retrosheet_event", "2020seve.zip", "https://example.com/2020seve.zip", force=True
        )

    mock_get.assert_called_once()


def test_mark_status_updates_existing_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    fake_response = Mock(status_code=200, content=b"data")
    with patch.object(manifest, "get_with_retry", return_value=fake_response):
        manifest.download("retrosheet", "f.zip", "https://example.com/f.zip")

    manifest.mark_status("retrosheet", "f.zip", "loaded")

    assert manifest.load_manifest("retrosheet")["f.zip"]["status"] == "loaded"


def test_mark_status_creates_entry_when_none_exists(tmp_path, monkeypatch):
    # Regression: mark_status used to silently no-op if the filename wasn't
    # already a manifest key (e.g. download() was mocked/bypassed rather
    # than actually called first) — it must always take effect.
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)

    manifest.mark_status("retrosheet", "never_downloaded.zip", "loaded")

    assert manifest.load_manifest("retrosheet")["never_downloaded.zip"]["status"] == "loaded"


def test_mark_status_records_optional_parser_and_schema_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    manifest.mark_status(
        "retrosheet", "f.zip", "parsed", parser_version="v2", schema_columns=["a", "b"]
    )
    entry = manifest.load_manifest("retrosheet")["f.zip"]
    assert entry["parser_version"] == "v2"
    assert entry["schema_fingerprint"] == manifest.schema_fingerprint(["a", "b"])


def test_load_manifest_returns_empty_dict_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)

    assert manifest.load_manifest("nonexistent_source") == {}


def test_check_downloads_directory_ok_when_writable_with_space(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path / "downloads")

    ok, detail = manifest.check_downloads_directory()

    assert ok
    assert "writable" in detail
    assert not (tmp_path / "downloads" / ".doctor_write_probe").exists()  # probe cleaned up


def test_check_downloads_directory_fails_when_not_writable(tmp_path, monkeypatch):
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir(mode=0o500)
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", readonly_dir / "downloads")

    try:
        ok, detail = manifest.check_downloads_directory()
    finally:
        readonly_dir.chmod(0o700)  # restore so tmp_path cleanup can remove it

    assert not ok
    assert "not writable" in detail


def test_check_downloads_directory_warns_below_disk_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    monkeypatch.setattr(manifest, "LOW_DISK_WARNING_BYTES", float("inf"))

    ok, detail = manifest.check_downloads_directory()

    assert not ok
    assert "GB free" in detail
