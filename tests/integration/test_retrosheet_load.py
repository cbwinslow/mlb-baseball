"""Real DB, real CSV parsing — only the network fetch is mocked, returning the
small committed fixture zip (trimmed from Atlanta's actual 2025 season data)."""

from datetime import date
from pathlib import Path
from unittest.mock import patch

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


def _mock_fetch(year):
    return FIXTURE_ZIP.read_bytes() if year == 2025 else None


def test_load_year_lands_all_seven_tables(db_conn):
    with patch.object(retrosheet, "_fetch_year_zip", side_effect=_mock_fetch):
        counts = retrosheet._load_year(db_conn, 2025)
    db_conn.commit()

    assert set(counts) == {f"raw.retrosheet_{name}" for name in retrosheet.CSV_NAMES}
    assert all(c > 0 for c in counts.values())
    with db_conn.cursor() as cur:
        cur.execute("SELECT gid, batter FROM raw.retrosheet_plays LIMIT 1")
        assert cur.fetchone() is not None


def test_missing_year_returns_empty_without_erroring(db_conn):
    with patch.object(retrosheet, "_fetch_year_zip", side_effect=_mock_fetch):
        counts = retrosheet._load_year(db_conn, 1899)  # not mocked -> None -> "not published yet"

    assert counts == {}


def test_reloading_a_year_replaces_it_without_touching_another(db_conn):
    with patch.object(retrosheet, "_fetch_year_zip", side_effect=_mock_fetch):
        retrosheet._load_year(db_conn, 2025)
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, _season) VALUES ('FAKE202401010', '2024')"
        )
    db_conn.commit()

    with patch.object(retrosheet, "_fetch_year_zip", side_effect=_mock_fetch):
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
    # published yet" (None) — verifying the sequential fetch/load loop
    # handles both cases and still aggregates totals correctly.
    class _FixedDate:
        @staticmethod
        def today():
            return date(2026, 1, 1)

    monkeypatch.setattr(retrosheet, "FIRST_YEAR", 2024)
    monkeypatch.setattr(retrosheet, "date", _FixedDate)

    def fetch(year):
        if year in (2024, 2025):
            return (FIXTURES_DIR / f"{year}csvs.zip").read_bytes()
        return None  # 2026: the current, still-in-progress year

    with patch.object(retrosheet, "_fetch_year_zip", side_effect=fetch):
        totals = retrosheet.bootstrap()

    assert set(totals) == {f"raw.retrosheet_{name}" for name in retrosheet.CSV_NAMES}
    assert all(c > 0 for c in totals.values())
