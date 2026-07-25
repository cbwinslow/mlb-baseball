"""Real DB, real CSV parsing (against the fixed GAMELOG_FIELDS layout) — only
the network fetch is mocked, returning a small committed fixture (trimmed
from the real 2025 game log)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import retrosheet_gamelog as gamelog

FIXTURE_ZIP = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet" / "gl2025.zip"


@pytest.fixture(autouse=True)
def _clean_table(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gamelog")
    db_conn.commit()


def _mock_fetch(year):
    return FIXTURE_ZIP.read_bytes() if year == 2025 else None


def test_load_year_lands_rows_with_all_161_columns(db_conn):
    with patch.object(gamelog, "_fetch_year_zip", side_effect=_mock_fetch):
        counts = gamelog._load_year(db_conn, 2025)
    db_conn.commit()

    assert counts == {"raw.retrosheet_gamelog": 20}
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema='raw' AND table_name='retrosheet_gamelog'"
        )
        (column_count,) = cur.fetchone()
        # 161 documented fields + _season + _loaded_at (see load.py).
        assert column_count == 163

        cur.execute("SELECT v_team, h_team, v_score, h_score FROM raw.retrosheet_gamelog LIMIT 1")
        row = cur.fetchone()
    assert row is not None
    assert all(v is not None for v in row)


def test_missing_year_returns_empty(db_conn):
    with patch.object(gamelog, "_fetch_year_zip", side_effect=_mock_fetch):
        counts = gamelog._load_year(db_conn, 1872)

    assert counts == {}


def test_reloading_a_year_replaces_without_touching_another(db_conn):
    with patch.object(gamelog, "_fetch_year_zip", side_effect=_mock_fetch):
        gamelog._load_year(db_conn, 2025)
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO raw.retrosheet_gamelog (v_team, _season) VALUES ('FAKE', '2024')")
    db_conn.commit()

    with patch.object(gamelog, "_fetch_year_zip", side_effect=_mock_fetch):
        gamelog._load_year(db_conn, 2025)
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _season, count(*) FROM raw.retrosheet_gamelog GROUP BY _season ORDER BY 1"
        )
        rows = cur.fetchall()
    assert ("2024", 1) in rows
    assert any(season == "2025" for season, _ in rows)
