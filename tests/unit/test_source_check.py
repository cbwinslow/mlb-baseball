"""Pure tests for `mlb source-check` -- no network, no database."""

import hashlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from mlb_baseball import manifest, source_check
from mlb_baseball.source_check import (
    CHANGED,
    GONE,
    UNCHANGED,
    UNKNOWN,
    Head,
    classify,
)

DOWNLOADED = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
ENTRY = {
    "url": "https://example.com/a.zip",
    "sha256": "abc",
    "bytes": 100,
    "downloaded_at": DOWNLOADED.isoformat(),
    "status": "loaded",
}


def test_newer_last_modified_is_changed():
    head = Head(status=200, last_modified=datetime(2026, 8, 9, tzinfo=UTC), content_length=100)
    assert classify(ENTRY, head).status == CHANGED


def test_different_size_is_changed():
    head = Head(status=200, last_modified=datetime(2026, 7, 1, tzinfo=UTC), content_length=101)
    assert classify(ENTRY, head).status == CHANGED


def test_both_agreeing_is_unchanged():
    head = Head(status=200, last_modified=datetime(2026, 7, 1, tzinfo=UTC), content_length=100)
    assert classify(ENTRY, head).status == UNCHANGED


def test_no_usable_headers_is_unknown():
    assert classify(ENTRY, Head(status=200)).status == UNKNOWN


def test_one_agreeing_header_is_not_enough_for_unchanged():
    head = Head(status=200, content_length=100)
    assert classify(ENTRY, head).status == UNKNOWN


def test_404_is_gone():
    assert classify(ENTRY, Head(status=404)).status == GONE


def test_request_error_is_unknown_with_the_error():
    verdict = classify(ENTRY, Head(error="ConnectionError: boom"))
    assert verdict.status == UNKNOWN
    assert "boom" in verdict.detail


def test_equal_hash_overrides_differing_headers():
    head = Head(status=200, last_modified=datetime(2026, 8, 9, tzinfo=UTC), content_length=999)
    assert classify(ENTRY, head, remote_sha256="abc").status == UNCHANGED


def test_different_hash_is_changed_even_when_headers_agree():
    head = Head(status=200, last_modified=datetime(2026, 7, 1, tzinfo=UTC), content_length=100)
    assert classify(ENTRY, head, remote_sha256="other").status == CHANGED


def test_fetch_headers_parses_http_date_and_length():
    response = Mock(
        status_code=200,
        headers={"Last-Modified": "Sun, 09 Aug 2026 10:00:00 GMT", "Content-Length": "123"},
    )
    with patch("mlb_baseball.source_check.head_with_retry", return_value=response):
        head = source_check.fetch_headers("https://example.com/a.zip")
    assert head == Head(
        status=200, last_modified=datetime(2026, 8, 9, 10, 0, tzinfo=UTC), content_length=123
    )


def test_fetch_headers_reports_failure_instead_of_raising():
    with patch(
        "mlb_baseball.source_check.head_with_retry",
        side_effect=requests.exceptions.ConnectionError("boom"),
    ):
        head = source_check.fetch_headers("https://example.com/a.zip")
    assert head.error is not None
    assert "boom" in head.error


def _tree(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_check_never_touches_the_downloads_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    manifest.save_manifest("src", {"a.zip": ENTRY, "b.zip": {**ENTRY, "url": "https://x/b.zip"}})
    before = _tree(tmp_path)

    head = Head(status=200, last_modified=datetime(2026, 8, 9, tzinfo=UTC), content_length=100)
    results, no_record = source_check.check(["src"], head=lambda url: head)

    assert [r.verdict.status for r in results] == [CHANGED, CHANGED]
    assert no_record == []
    assert _tree(tmp_path) == before


def test_missing_and_empty_manifests_are_no_download_record(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    manifest.save_manifest("empty", {})

    results, no_record = source_check.check(["empty", "absent"], head=lambda url: Head())

    assert results == []
    assert no_record == ["empty", "absent"]
    lines = source_check.render(results, no_record)
    assert "empty: no download record" in lines
    assert not any("unchanged" in line for line in lines)


def test_entry_without_url_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    manifest.save_manifest("src", {"a.zip": {"status": "loaded"}})

    results, _ = source_check.check(["src"], head=lambda url: pytest.fail("no url to fetch"))

    assert results[0].verdict.status == UNKNOWN


def test_exit_codes_distinguish_changed_from_unchecked():
    def result(status):
        return source_check.Result("s", "a.zip", source_check.Verdict(status))

    assert source_check.exit_code([result(UNCHANGED)], [], requested=False) == 0
    assert source_check.exit_code([result(CHANGED), result(UNKNOWN)], [], requested=False) == 1
    assert source_check.exit_code([result(UNKNOWN)], [], requested=False) == 2
    assert source_check.exit_code([result(GONE)], [], requested=False) == 2
    assert source_check.exit_code([], ["s"], requested=False) == 0
    assert source_check.exit_code([], ["s"], requested=True) == 2


def test_render_prints_refresh_command_for_each_changed_source(tmp_path, monkeypatch):
    results = [
        source_check.Result("retrosheet_gamelog", "gl1871.zip", source_check.Verdict(CHANGED, "x")),
        source_check.Result("retrosheet_roster", "rosters.zip", source_check.Verdict(UNCHANGED)),
    ]
    lines = source_check.render(results, [])
    assert "  mlb ingest retrosheet_gamelog --refresh" in lines
    assert "  mlb ingest retrosheet_roster --refresh" not in lines
    assert "No source changed." not in lines


def test_hash_check_compares_sha256_and_removes_the_temporary_file(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path / "downloads")
    content = b"archive bytes"
    manifest.save_manifest(
        "src", {"a.zip": {**ENTRY, "sha256": hashlib.sha256(content).hexdigest()}}
    )
    temp_dir = tmp_path / "tmp"
    temp_dir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))
    response = Mock(status_code=200, content=content)

    with patch("mlb_baseball.source_check.get_with_retry", return_value=response):
        results, _ = source_check.check(
            ["src"], hash_check=True, head=lambda url: pytest.fail("headers not needed")
        )

    assert results[0].verdict.status == UNCHANGED
    assert list(temp_dir.iterdir()) == []


def test_hash_check_404_is_gone(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    manifest.save_manifest("src", {"a.zip": ENTRY})
    with patch("mlb_baseball.source_check.get_with_retry", return_value=Mock(status_code=404)):
        results, _ = source_check.check(["src"], hash_check=True)
    assert results[0].verdict.status == GONE


def test_discover_sources_lists_directories_and_skips_set_aside_ones(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest, "DOWNLOADS_ROOT", tmp_path)
    (tmp_path / "retrosheet").mkdir()
    (tmp_path / "_superseded").mkdir()
    (tmp_path / "stray.txt").write_text("x")
    assert source_check.discover_sources() == ["retrosheet"]
