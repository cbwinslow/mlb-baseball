"""Real DB, real CSV parsing — the network is mocked: park/team text fetches
return small inline fixtures, and the biofile fetch returns a small committed
zip (trimmed from the real files, headers intact)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import retrosheet_reference as reference

FIXTURE_ZIP = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet" / "biofile.zip"

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
]


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in ALL_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    db_conn.commit()


def _fetch_text(url):
    return TEAM_TEXT if "TEAMABR" in url else PARK_TEXT


def test_bootstrap_lands_all_six_tables(db_conn):
    with (
        patch.object(reference, "_fetch_text", side_effect=_fetch_text),
        patch.object(reference, "_fetch_bytes", return_value=FIXTURE_ZIP.read_bytes()),
    ):
        counts = reference.bootstrap()

    assert set(counts) == set(ALL_TABLES)
    assert all(c > 0 for c in counts.values())
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.retrosheet_park")
        assert cur.fetchone() == (1,)


def test_rerunning_replaces_instead_of_duplicating():
    with (
        patch.object(reference, "_fetch_text", side_effect=_fetch_text),
        patch.object(reference, "_fetch_bytes", return_value=FIXTURE_ZIP.read_bytes()),
    ):
        reference.bootstrap()
        reference.update()

    with reference.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.retrosheet_park")
        assert cur.fetchone() == (1,)
