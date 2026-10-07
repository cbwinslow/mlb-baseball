"""Parsers behind `mlb schema-watch`: a seeded new file in a publisher's list is reported."""

from mlb_baseball.schema_sources import (
    MLB_API_ENDPOINTS,
    frame_columns,
    github_dir_files,
    mlb_api_datasets,
    retrosheet_files,
)
from mlb_baseball.schema_watch import Dataset, SnapshotStore, check

HTML = (
    '<a href="https://www.retrosheet.org/downloads/csvdownloads.zip">x</a>'
    '<a href="https://www.retrosheet.org/downloads/2025/2025csvs.zip">y</a>'
    '<a href="https://www.retrosheet.org/downloads/notes.html">skip</a>'
)


def test_retrosheet_files_keeps_zip_links_only():
    assert retrosheet_files(HTML) == {"csvdownloads.zip": "file", "2025/2025csvs.zip": "file"}


def test_github_dir_files_ignores_subdirectories():
    listing = [{"name": "a.csv", "type": "file"}, {"name": "sub", "type": "dir"}]
    assert github_dir_files(listing) == {"a.csv": "file"}


def test_new_season_file_is_reported_as_added(tmp_path):
    store = SnapshotStore(tmp_path)

    def dataset(html):
        return Dataset("retrosheet", "downloads_page", lambda: retrosheet_files(html), kind="names")

    check([dataset(HTML)], store)
    seeded = HTML + '<a href="https://www.retrosheet.org/downloads/2026/2026csvs.zip">z</a>'
    (finding,) = check([dataset(seeded)], store)
    assert finding.status == "drift"
    assert finding.drift.added == {"2026/2026csvs.zip": "file"}


def test_frame_columns_reads_dtypes_from_rows_or_frames():
    assert frame_columns([{"a": 1, "b": "x"}]) == {"a": "int64", "b": "object"}


def test_every_mlb_endpoint_is_a_dataset():
    assert {d.name for d in mlb_api_datasets()} == set(MLB_API_ENDPOINTS)
