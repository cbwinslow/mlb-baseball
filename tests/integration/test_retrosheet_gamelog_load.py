"""Real DB, real CSV parsing (against the fixed GAMELOG_FIELDS layout) — only
the network fetch is mocked, returning a small committed fixture (trimmed
from the real 2025 game log)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import retrosheet_gamelog as gamelog

FIXTURE_ZIP = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet" / "gl2025.zip"
GLWS_FIXTURE_ZIP = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet" / "glws.zip"


@pytest.fixture(autouse=True)
def _clean_table(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gamelog")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gamelog_post")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _isolated_manifest(tmp_path, monkeypatch):
    # _download_year is mocked below, but manifest.mark_status() is not —
    # it would otherwise write a real "gl2025.zip" entry into the actual
    # downloads/retrosheet_gamelog/manifest.json that production bootstraps
    # use. Redirect to a fresh tmp_path instead.
    monkeypatch.setattr(gamelog.manifest, "DOWNLOADS_ROOT", tmp_path)


def _mock_download(year):
    return FIXTURE_ZIP if year == 2025 else None


def test_load_year_lands_rows_with_all_161_columns(db_conn):
    with patch.object(gamelog, "_download_year", side_effect=_mock_download):
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
    with patch.object(gamelog, "_download_year", side_effect=_mock_download):
        counts = gamelog._load_year(db_conn, 1872)

    assert counts == {}


def test_reloading_a_year_replaces_without_touching_another(db_conn):
    with patch.object(gamelog, "_download_year", side_effect=_mock_download):
        gamelog._load_year(db_conn, 2025)
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO raw.retrosheet_gamelog (v_team, _season) VALUES ('FAKE', '2024')")
    db_conn.commit()

    with patch.object(gamelog, "_download_year", side_effect=_mock_download):
        gamelog._load_year(db_conn, 2025)
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _season, count(*) FROM raw.retrosheet_gamelog GROUP BY _season ORDER BY 1"
        )
        rows = cur.fetchall()
    assert ("2024", 1) in rows
    assert any(season == "2025" for season, _ in rows)


def test_load_post_archive_lands_rows_in_separate_table(db_conn):
    with patch.object(gamelog.manifest, "download", return_value=GLWS_FIXTURE_ZIP):
        counts = gamelog._load_post_archive(db_conn, "glws.zip", "worldseries")
    db_conn.commit()

    assert counts == {"raw.retrosheet_gamelog_post": 3}
    with db_conn.cursor() as cur:
        cur.execute("SELECT DISTINCT _type FROM raw.retrosheet_gamelog_post")
        assert cur.fetchall() == [("worldseries",)]
        cur.execute(
            "SELECT v_team, h_team, v_score, h_score FROM raw.retrosheet_gamelog_post LIMIT 1"
        )
        assert cur.fetchone() is not None


def test_load_post_archive_replaces_its_own_type_only(db_conn):
    with patch.object(gamelog.manifest, "download", return_value=GLWS_FIXTURE_ZIP):
        gamelog._load_post_archive(db_conn, "glws.zip", "worldseries")
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gamelog_post (v_team, _type) VALUES ('FAKE', 'allstar')"
        )
    db_conn.commit()

    with patch.object(gamelog.manifest, "download", return_value=GLWS_FIXTURE_ZIP):
        gamelog._load_post_archive(db_conn, "glws.zip", "worldseries")
        db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _type, count(*) FROM raw.retrosheet_gamelog_post GROUP BY _type ORDER BY 1"
        )
        rows = cur.fetchall()
    assert ("allstar", 1) in rows
    assert any(t == "worldseries" for t, _ in rows)
