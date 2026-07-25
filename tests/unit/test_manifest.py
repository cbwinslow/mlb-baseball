from unittest.mock import Mock, patch

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


def test_load_manifest_returns_empty_dict_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)

    assert manifest.load_manifest("nonexistent_source") == {}
