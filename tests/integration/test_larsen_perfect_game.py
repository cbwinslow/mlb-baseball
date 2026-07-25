"""Ties out one real, famous, independently-verifiable game — Don Larsen's
perfect game, 1956 World Series Game 5 (Yankees 2, Dodgers 0, Oct 8 1956) —
across every Retrosheet product this project ingests, using real (trimmed)
data from each: the pre-parsed CSV product, the raw event files (parsed by
this project's own cwevent/cwgame integration, not trusted from upstream),
and the postseason game log.

This is the automated version of a manual cross-check that found a real bug
this session: raw.retrosheet_gamelog only ever covered regular-season games,
so this exact game was silently absent from it. If any of these products'
parsing ever drifts, disagrees with another, or drops this game, this test
fails — not just "does bootstrap run without erroring" like most other
tests, but "do independently-built parsers agree on one real historical
fact all the way down to the play level."
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball import chadwick_tools
from mlb_baseball.connectors import retrosheet
from mlb_baseball.connectors import retrosheet_event as event
from mlb_baseball.connectors import retrosheet_gamelog as gamelog

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "larsen_game"
CSV_FIXTURE = FIXTURES_DIR / "1956csvs.zip"
EVENT_FIXTURE = FIXTURES_DIR / "allpost_1956.zip"
GAMELOG_FIXTURE = FIXTURES_DIR / "glws.zip"

# Every test here loads the raw event file via real cwevent/cwgame parsing —
# skip cleanly, not fail, if these aren't installed. See README.md
# "Requirements".
pytestmark = pytest.mark.skipif(
    bool(chadwick_tools.missing_tools()),
    reason=f"cwevent/cwgame not installed: {chadwick_tools.missing_tools()}",
)

GID = "NYA195610080"


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for name in retrosheet.CSV_NAMES:
            cur.execute(f"DROP TABLE IF EXISTS raw.retrosheet_{name}")
        cur.execute(f"DROP TABLE IF EXISTS {event.EVENT_TABLE}")
        cur.execute(f"DROP TABLE IF EXISTS {event.GAME_TABLE}")
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_gamelog_post")
    db_conn.commit()


@pytest.fixture(autouse=True)
def _isolated_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(retrosheet.manifest, "DOWNLOADS_ROOT", tmp_path)
    monkeypatch.setattr(event.manifest, "DOWNLOADS_ROOT", tmp_path)
    monkeypatch.setattr(gamelog.manifest, "DOWNLOADS_ROOT", tmp_path)


@pytest.fixture
def _loaded(db_conn):
    """Loads the Larsen game into all three products via the real
    connector code paths, only the network fetch mocked."""
    with patch.object(retrosheet, "_download_year", return_value=CSV_FIXTURE):
        retrosheet._load_year(db_conn, 1956)
    with patch.object(event.manifest, "download", return_value=EVENT_FIXTURE):
        event._load_archive(db_conn, "allpost_1956.zip", "https://example.com/x", "postseason")
    with patch.object(gamelog.manifest, "download", return_value=GAMELOG_FIXTURE):
        gamelog._load_post_archive(db_conn, "glws.zip", "worldseries")
    db_conn.commit()
    return db_conn


KNOWN_FACTS = {
    "away_team": "BRO",
    "home_team": "NYA",
    "away_score": "0",
    "home_score": "2",
    "winning_pitcher": "larsd102",  # Don Larsen
    "losing_pitcher": "magls101",  # Sal Maglie
    "attendance": "64519",
    "park": "NYC16",  # Yankee Stadium
}


def test_csv_product_matches_known_facts(_loaded):
    with _loaded.cursor() as cur:
        cur.execute(
            "SELECT visteam, hometeam, vruns, hruns, wp, lp, attendance, site "
            "FROM raw.retrosheet_gameinfo WHERE gid = %s",
            (GID,),
        )
        row = cur.fetchone()
    assert row == (
        KNOWN_FACTS["away_team"],
        KNOWN_FACTS["home_team"],
        KNOWN_FACTS["away_score"],
        KNOWN_FACTS["home_score"],
        KNOWN_FACTS["winning_pitcher"],
        KNOWN_FACTS["losing_pitcher"],
        KNOWN_FACTS["attendance"],
        KNOWN_FACTS["park"],
    )


def test_raw_event_file_parse_matches_known_facts(_loaded):
    with _loaded.cursor() as cur:
        cur.execute(
            "SELECT away_team_id, home_team_id, away_score_ct, home_score_ct, "
            "win_pit_id, lose_pit_id, attend_park_ct, park_id "
            f"FROM {event.GAME_TABLE} WHERE game_id = %s",
            (GID,),
        )
        row = cur.fetchone()
    assert row == (
        KNOWN_FACTS["away_team"],
        KNOWN_FACTS["home_team"],
        KNOWN_FACTS["away_score"],
        KNOWN_FACTS["home_score"],
        KNOWN_FACTS["winning_pitcher"],
        KNOWN_FACTS["losing_pitcher"],
        KNOWN_FACTS["attendance"],
        KNOWN_FACTS["park"],
    )


def test_postseason_gamelog_matches_known_facts(_loaded):
    with _loaded.cursor() as cur:
        cur.execute(
            "SELECT v_team, h_team, v_score, h_score, winning_pitcher_id, "
            "losing_pitcher_id, attendance, park_id "
            "FROM raw.retrosheet_gamelog_post WHERE date = '19561008'"
        )
        row = cur.fetchone()
    assert row == (
        KNOWN_FACTS["away_team"],
        KNOWN_FACTS["home_team"],
        KNOWN_FACTS["away_score"],
        KNOWN_FACTS["home_score"],
        KNOWN_FACTS["winning_pitcher"],
        KNOWN_FACTS["losing_pitcher"],
        KNOWN_FACTS["attendance"],
        KNOWN_FACTS["park"],
    )


def test_play_by_play_confirms_the_perfect_game_itself(_loaded):
    """Not just metadata agreement — the actual play-by-play parsed by this
    project's own cwevent integration must show the real defining fact of a
    perfect game: every Dodger batter made an out, nobody ever reached base."""
    with _loaded.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {event.EVENT_TABLE} WHERE game_id = %s", (GID,))
        (total_plays,) = cur.fetchone()

        cur.execute(
            f"SELECT count(*) FROM {event.EVENT_TABLE} WHERE game_id = %s "
            "AND bat_team_id = 'BRO' AND h_cd != '0'",
            (GID,),
        )
        (hits_allowed,) = cur.fetchone()

        cur.execute(
            f"SELECT count(*) FROM {event.EVENT_TABLE} WHERE game_id = %s "
            "AND bat_team_id = 'BRO' "
            "AND (base1_run_id IS NOT NULL AND base1_run_id != '')",
            (GID,),
        )
        (times_runner_on_first,) = cur.fetchone()

    assert total_plays == 56
    assert hits_allowed == 0
    assert times_runner_on_first == 0
