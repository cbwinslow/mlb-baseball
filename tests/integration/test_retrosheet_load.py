"""Runs the real cwevent binary against a small committed fixture (one real game,
trimmed from Atlanta's 2025 season) — not mocked, since parsing correctness is
exactly what this connector exists to get right. Only the git clone/pull (network)
is mocked; REPO_DIR points at the fixture directory instead."""

from pathlib import Path

import pytest

from mlb_baseball.connectors import retrosheet

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet"


@pytest.fixture(autouse=True)
def _use_fixture_repo(monkeypatch):
    monkeypatch.setattr(retrosheet, "REPO_DIR", FIXTURES_DIR)
    monkeypatch.setattr(retrosheet, "sync_repo", lambda: None)


@pytest.fixture(autouse=True)
def _clean_table(db_conn):
    yield
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()


def test_run_cwevent_parses_the_real_fixture_game():
    df = retrosheet._run_cwevent(2025)

    assert len(df) == 75  # one full game's worth of events
    assert df.iloc[0]["GAME_ID"] == "ATL202504040"
    assert (df["_season"] == "2025").all()


def test_load_season_lands_rows(db_conn):
    rowcount = retrosheet._load_season(db_conn, 2025)
    db_conn.commit()

    assert rowcount == 75
    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.retrosheet_event WHERE _season = '2025'")
        assert cur.fetchone() == (75,)


def test_reloading_a_season_replaces_it_without_touching_other_seasons(db_conn):
    retrosheet._load_season(db_conn, 2025)
    db_conn.commit()
    # Simulate a second, independently-loaded season sharing the same table.
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_event (game_id, _season) VALUES ('FAKE202401010', '2024')"
        )
    db_conn.commit()

    retrosheet._load_season(db_conn, 2025)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT _season, count(*) FROM raw.retrosheet_event GROUP BY _season ORDER BY 1"
        )
        assert cur.fetchall() == [("2024", 1), ("2025", 75)]
