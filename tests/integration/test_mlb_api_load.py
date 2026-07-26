"""Real DB, real DataFrame/COPY loading — only the network (the `statsapi`
package's own HTTP calls) is mocked, returning small fixture payloads shaped
like real statsapi.schedule()/standings_data() output."""

from datetime import date
from unittest.mock import patch

import pytest

from mlb_baseball.connectors import mlb_api

TABLES = ["raw.mlb_schedule", "raw.mlb_standing"]

FIXTURE_GAMES = [
    {
        "game_id": 1001,
        "game_datetime": "2026-04-01T18:05:00Z",
        "game_date": "2026-04-01",
        "game_type": "R",
        "status": "Final",
        "away_name": "New York Yankees",
        "home_name": "Baltimore Orioles",
        "away_id": 147,
        "home_id": 110,
        "away_score": 2,
        "home_score": 5,
        "national_broadcasts": ["MLBN"],
        "winning_pitcher": "Someone",
        "losing_pitcher": "Someone Else",
        "save_pitcher": None,
    },
    {
        "game_id": 1002,
        "game_datetime": "2026-04-02T18:05:00Z",
        "game_date": "2026-04-02",
        "game_type": "R",
        "status": "Scheduled",
        "away_name": "New York Yankees",
        "home_name": "Baltimore Orioles",
        "away_id": 147,
        "home_id": 110,
        "away_score": "0",
        "home_score": "0",
        "national_broadcasts": [],
        "winning_pitcher": None,
        "losing_pitcher": None,
        "save_pitcher": None,
    },
]

FIXTURE_STANDINGS = {
    201: {
        "div_name": "American League East",
        "teams": [
            {"name": "Baltimore Orioles", "team_id": 110, "div_rank": "1", "w": 1, "l": 0},
            {"name": "New York Yankees", "team_id": 147, "div_rank": "2", "w": 0, "l": 1},
        ],
    }
}


class _FixedDate(date):
    @classmethod
    def today(cls):
        return date(2026, 6, 1)


@pytest.fixture(autouse=True)
def _fixed_season(monkeypatch):
    monkeypatch.setattr(mlb_api, "date", _FixedDate)


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    db_conn.commit()


def _mocked_statsapi():
    return patch.multiple(
        mlb_api.statsapi,
        schedule=lambda **kwargs: FIXTURE_GAMES,
        standings_data=lambda **kwargs: FIXTURE_STANDINGS,
    )


def test_bootstrap_lands_schedule_and_standings(db_conn):
    with _mocked_statsapi():
        counts = mlb_api.bootstrap()

    assert counts == {"raw.mlb_schedule": 2, "raw.mlb_standing": 2}
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT game_id, status, national_broadcasts, _season "
            "FROM raw.mlb_schedule ORDER BY game_id"
        )
        rows = cur.fetchall()
    assert rows[0] == ("1001", "Final", '["MLBN"]', "2026")
    assert rows[1] == ("1002", "Scheduled", "[]", "2026")

    with db_conn.cursor() as cur:
        cur.execute("SELECT division_id, div_name, name, w, l FROM raw.mlb_standing ORDER BY name")
        rows = cur.fetchall()
    assert rows == [
        ("201", "American League East", "Baltimore Orioles", "1", "0"),
        ("201", "American League East", "New York Yankees", "0", "1"),
    ]


def test_rerunning_replaces_instead_of_duplicating(db_conn):
    with _mocked_statsapi():
        mlb_api.bootstrap()
        mlb_api.update()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_schedule")
        assert cur.fetchone() == (2,)
        cur.execute("SELECT count(*) FROM raw.mlb_standing")
        assert cur.fetchone() == (2,)
