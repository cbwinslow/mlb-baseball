"""Real DB, real CSV parsing — the network is mocked: manifest.download() is
patched to hand back small local fixture files instead of hitting the network
(park/team text fixtures written inline, the biofile/biodata fetches return
small committed zips trimmed from the real files, headers intact)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import retrosheet_reference as reference

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet"
BIOFILE_ZIP = FIXTURES_DIR / "biofile.zip"
BIODATA_ZIP = FIXTURES_DIR / "biodata.zip"

PARK_TEXT = (
    "PARKID,NAME,AKA,CITY,STATE,START,END,LEAGUE,NOTES\nALB01,Riverside Park,,Albany,NY,,,, \n"
)
TEAM_TEXT = '"BS1","NA","Boston","Braves","1871","1875"\n'

ALL_TABLES = [
    "raw.retrosheet_park",
    "raw.retrosheet_team",
    "raw.retrosheet_biofile",
    "raw.retrosheet_biofile0",
    "raw.retrosheet_coach",
    "raw.retrosheet_relative",
    "raw.retrosheet_ballpark",
    "raw.retrosheet_coach0",
    "raw.retrosheet_manager",
    "raw.retrosheet_team0",
    "raw.retrosheet_umpire",
]


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in ALL_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    db_conn.commit()


def _mock_download(tmp_path):
    def _download(source, filename, url):
        dest = tmp_path / filename
        if filename == "parkcode.txt":
            dest.write_text(PARK_TEXT)
        elif filename == "TEAMABR.TXT":
            dest.write_text(TEAM_TEXT)
        elif filename == "biofile.zip":
            dest.write_bytes(BIOFILE_ZIP.read_bytes())
        elif filename == "biodata.zip":
            dest.write_bytes(BIODATA_ZIP.read_bytes())
        else:
            raise AssertionError(f"unexpected download: {filename}")
        return dest

    return _download


def test_bootstrap_lands_all_eleven_tables(db_conn, tmp_path):
    with patch.object(reference, "manifest") as mock_manifest:
        mock_manifest.download_required.side_effect = _mock_download(tmp_path)
        counts = reference.bootstrap()

    assert set(counts) == set(ALL_TABLES)
    assert all(c > 0 for c in counts.values())
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.retrosheet_park")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM raw.retrosheet_umpire")
        assert cur.fetchone() == (3,)


def test_rerunning_replaces_instead_of_duplicating(tmp_path):
    with patch.object(reference, "manifest") as mock_manifest:
        mock_manifest.download_required.side_effect = _mock_download(tmp_path)
        reference.bootstrap()
        reference.update()

    with reference.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.retrosheet_park")
        assert cur.fetchone() == (1,)
