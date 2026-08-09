"""Real DB, real CSV parsing — only the network fetch is mocked, returning the
small committed fixture zip (trimmed from Atlanta's actual 2025 season data)."""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from mlb_baseball.connectors import retrosheet

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet"
FIXTURE_ZIP = FIXTURES_DIR / "2025csvs.zip"


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for name in retrosheet.CSV_NAMES:
            cur.execute(f"DROP TABLE IF EXISTS raw.retrosheet_{name}")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _isolated_manifest(tmp_path, monkeypatch):
    # _download_year is mocked below, but manifest.mark_status() is not —
    # it would otherwise write real entries (fixture filenames like
    # "2025csvs.zip") into the actual downloads/retrosheet/manifest.json
    # that production bootstraps use. Redirect to a fresh tmp_path instead.
    monkeypatch.setattr(retrosheet.manifest, "DOWNLOADS_ROOT", tmp_path)


def _mock_download(year):
    return FIXTURE_ZIP if year == 2025 else None


def test_load_year_lands_all_seven_tables(db_conn):
    with patch.object(retrosheet, "_download_year", side_effect=_mock_download):
        counts = retrosheet._load_year(db_conn, 2025)
    db_conn.commit()

    assert set(counts) == {f"raw.retrosheet_{name}" for name in retrosheet.CSV_NAMES}
    assert all(c > 0 for c in counts.values())
    with db_conn.cursor() as cur:
        cur.execute("SELECT gid, batter FROM raw.retrosheet_plays LIMIT 1")
        assert cur.fetchone() is not None

    entry = retrosheet.manifest.load_manifest(retrosheet.SOURCE)["2025csvs.zip"]
    assert entry["parser_version"] == retrosheet.PARSER_VERSION
    assert entry["schema_fingerprint"] == retrosheet.manifest.schema_fingerprint(
        [
            f"{name}.{column}"
            for name, df in retrosheet._extract_csvs(2025, FIXTURE_ZIP).items()
            for column in df.columns
        ]
    )


def test_missing_year_returns_empty_without_erroring(db_conn):
    with patch.object(retrosheet, "_download_year", side_effect=_mock_download):
        counts = retrosheet._load_year(db_conn, 1899)  # not mocked -> None -> "not published yet"

    assert counts == {}


def test_reloading_a_year_replaces_it_without_touching_another(db_conn):
    with patch.object(retrosheet, "_download_year", side_effect=_mock_download):
        retrosheet._load_year(db_conn, 2025)
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, _season) VALUES ('FAKE202401010', '2024')"
        )
    db_conn.commit()

    with patch.object(retrosheet, "_download_year", side_effect=_mock_download):
        retrosheet._load_year(db_conn, 2025)
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _season, count(*) FROM raw.retrosheet_gameinfo GROUP BY _season ORDER BY 1"
        )
        rows = cur.fetchall()
    assert ("2024", 1) in rows
    assert any(season == "2025" for season, _ in rows)


def test_bootstrap_loads_multiple_years_and_skips_missing_ones(monkeypatch):
    # Two real (fixture) years, 2024 and 2025, plus 2026 deliberately "not
    # published yet" (None) — verifying the sequential download/load loop
    # handles both cases and still aggregates totals correctly.
    class _FixedDate:
        @staticmethod
        def today():
            return date(2026, 1, 1)

    monkeypatch.setattr(retrosheet, "FIRST_YEAR", 2024)
    monkeypatch.setattr(retrosheet, "date", _FixedDate)

    def download(year):
        if year in (2024, 2025):
            return FIXTURES_DIR / f"{year}csvs.zip"
        return None  # 2026: the current, still-in-progress year

    with patch.object(retrosheet, "_download_year", side_effect=download):
        totals = retrosheet.bootstrap()

    assert set(totals) == {f"raw.retrosheet_{name}" for name in retrosheet.CSV_NAMES}
    assert all(c > 0 for c in totals.values())


def test_year_with_fewer_columns_loads_with_nulls_instead_of_erroring(db_conn):
    # Regression: a real full-history bootstrap found 1898's real plays.csv
    # has 177 columns (matching 2024's real plays.csv too) while 1899's real
    # plays.csv has only 161 -- missing ball/strike-count, left-on-base-ID,
    # pinch-runner base-state, reached-on-error, and score-at-play columns.
    # Confirmed by downloading and diffing the real files, not assumed: this
    # is genuinely less-detailed source material for a less-thoroughly-
    # reconstructed early season, not a parsing bug. The old
    # schema_drift_policy="error" treated the second (narrower) year as
    # fatal, with no per-year recovery -- aborting bootstrap() for every
    # subsequent year too. This must not happen: a narrower year should
    # load with NULLs for whatever it's missing, same as every other
    # Retrosheet-family connector already handles this (e.g.
    # retrosheet_box.py's umpire_lf case).
    wide = pd.DataFrame({"gid": ["W1"], "inn_ct": ["1"], "balls_ct": ["2"], "_season": ["1898"]})
    narrow = pd.DataFrame({"gid": ["N1"], "inn_ct": ["1"], "_season": ["1899"]})

    def fake_extract(year, zip_path):
        return {"plays": wide if year == 1898 else narrow}

    with patch.object(retrosheet, "_extract_csvs", side_effect=fake_extract):
        retrosheet._load_zip(db_conn, 1898, Path("unused-1898.zip"))
        db_conn.commit()
        # Must not raise -- this is the actual regression.
        retrosheet._load_zip(db_conn, 1899, Path("unused-1899.zip"))
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT gid, balls_ct FROM raw.retrosheet_plays ORDER BY gid")
        rows = cur.fetchall()
    assert rows == [("N1", None), ("W1", "2")]


def test_bootstrap_continues_past_a_failing_year(monkeypatch, db_conn):
    # Regression: bootstrap() had no per-year exception handling at all, so
    # any single year's failure (schema drift or otherwise) silently aborted
    # every remaining year -- confirmed the hard way: a real full-history
    # bootstrap died on 1899 (the second year of 128) and never attempted
    # 1900-2026. Mirrors statcast.py's already-proven per-chunk try/except
    # pattern (_load_season), not a new design.
    class _FixedDate:
        @staticmethod
        def today():
            return date(2026, 1, 1)

    monkeypatch.setattr(retrosheet, "FIRST_YEAR", 2024)
    monkeypatch.setattr(retrosheet, "date", _FixedDate)

    def flaky_load_year(conn, year):
        if year == 2024:
            raise RuntimeError("simulated transient failure")
        return retrosheet._load_zip(conn, year, FIXTURES_DIR / f"{year}csvs.zip")

    with patch.object(retrosheet, "_load_year", side_effect=flaky_load_year):
        totals = retrosheet.bootstrap()

    # 2024 failed and was skipped; 2025 must still have loaded despite it.
    assert set(totals) == {f"raw.retrosheet_{name}" for name in retrosheet.CSV_NAMES}
    assert all(c > 0 for c in totals.values())
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _season FROM raw.retrosheet_plays")
        assert cur.fetchall() == [("2025",)]
