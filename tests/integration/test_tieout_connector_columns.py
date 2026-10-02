"""Pinned column-contract tests for the event, game, and CSV tables (task
3.1, design D6, closing audit finding G2): real DB, real connector loads
against committed fixtures -- not synthetic ``CREATE TABLE`` statements like
``test_tieout_schema_contract.py``'s roster fixture, and not production.

Two families, because their column source differs:

- ``raw.retrosheet_event``/``raw.retrosheet_game`` come from a Chadwick CLI
  tool's configured field spec (``chadwick_tools.run_cwevent``/``run_cwgame``)
  and are pinned separately in
  ``mlb_baseball.tieout_connector_columns.CONNECTOR_FIELD_CONTRACT`` -- see
  that module's docstring for why this differs from the production-facing
  ``RAW_SCHEMA_CONTRACT`` (task 2.6).
- ``raw.retrosheet_plays``/``batting``/``gameinfo``/``allplayers`` come
  straight from Retrosheet's own CSV headers, so the connector's field list
  *is* whatever the fixture's real CSV header says -- checked here against
  ``RAW_SCHEMA_CONTRACT`` directly, no separate pin needed.

Each family also gets a renamed-column case, proving the mechanism actually
detects drift rather than only ever seeing a match.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from mlb_baseball import chadwick_tools
from mlb_baseball.connectors import retrosheet
from mlb_baseball.connectors import retrosheet_event as event
from mlb_baseball.tieout import check_columns
from mlb_baseball.tieout_connector_columns import (
    CONNECTOR_FIELD_CONTRACT,
    OPTIONAL_CONNECTOR_COLUMNS,
)
from mlb_baseball.tieout_run import fetch_actual_columns
from mlb_baseball.tieout_schema_contract import RAW_SCHEMA_CONTRACT

EVENT_FIXTURE_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet_event" / "decade.zip"
)
CSV_FIXTURE_ZIP = (
    Path(__file__).resolve().parent.parent / "fixtures" / "retrosheet" / "2025csvs.zip"
)

CSV_CONTRACT = {
    table: RAW_SCHEMA_CONTRACT[table]
    for table in (
        "raw.retrosheet_plays",
        "raw.retrosheet_batting",
        "raw.retrosheet_gameinfo",
        "raw.retrosheet_allplayers",
    )
}

pytestmark = pytest.mark.skipif(
    bool(chadwick_tools.missing_tools()),
    reason=f"cwevent/cwgame not installed: {chadwick_tools.missing_tools()}",
)


def _without_optional(actual):
    """Drop columns only some Chadwick builds emit (see OPTIONAL_CONNECTOR_COLUMNS)."""
    return {
        table: columns - OPTIONAL_CONNECTOR_COLUMNS.get(table, frozenset())
        for table, columns in actual.items()
    }


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    def _drop() -> None:
        db_conn.rollback()
        with db_conn.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS {event.EVENT_TABLE}")
            cur.execute(f"DROP TABLE IF EXISTS {event.GAME_TABLE}")
            for name in retrosheet.CSV_NAMES:
                cur.execute(f"DROP TABLE IF EXISTS raw.retrosheet_{name}")
        db_conn.commit()

    _drop()
    yield
    _drop()


@pytest.fixture(autouse=True)
def _isolated_manifests(tmp_path, monkeypatch):
    # Same reasoning as test_retrosheet_event_load.py / test_retrosheet_load.py:
    # keep the real production manifest.json files untouched.
    monkeypatch.setattr(event.manifest, "DOWNLOADS_ROOT", tmp_path)
    monkeypatch.setattr(retrosheet.manifest, "DOWNLOADS_ROOT", tmp_path)


def test_a_real_event_and_game_load_matches_the_connectors_pinned_columns(db_conn):
    with patch.object(event.manifest, "download", return_value=EVENT_FIXTURE_ZIP):
        event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
    db_conn.commit()

    actual = _without_optional(
        fetch_actual_columns(db_conn, ["retrosheet_event", "retrosheet_game"])
    )
    problems = check_columns(actual, CONNECTOR_FIELD_CONTRACT)

    assert problems == []


def test_a_column_renamed_by_cwevent_is_caught(db_conn):
    real_run_cwevent = chadwick_tools.run_cwevent

    def renamed_run_cwevent(event_dir, year):
        df = real_run_cwevent(event_dir, year)
        return df.rename(columns={"BAT_ID": "BATTER_ID"})

    with (
        patch.object(event.manifest, "download", return_value=EVENT_FIXTURE_ZIP),
        patch.object(event.chadwick_tools, "run_cwevent", side_effect=renamed_run_cwevent),
    ):
        event._load_archive(db_conn, "decade.zip", "https://example.com/decade.zip", "pbp")
    db_conn.commit()

    actual = _without_optional(
        fetch_actual_columns(db_conn, ["retrosheet_event", "retrosheet_game"])
    )
    problems = check_columns(actual, CONNECTOR_FIELD_CONTRACT)

    assert any("raw.retrosheet_event is missing column(s)" in p and "bat_id" in p for p in problems)
    assert any(
        "raw.retrosheet_event has unexpected column(s)" in p and "batter_id" in p for p in problems
    )


def test_a_real_csv_load_matches_the_pinned_columns(db_conn):
    with patch.object(retrosheet, "_download_year", return_value=CSV_FIXTURE_ZIP):
        retrosheet._load_year(db_conn, 2025)
    db_conn.commit()

    actual = fetch_actual_columns(
        db_conn,
        ["retrosheet_plays", "retrosheet_batting", "retrosheet_gameinfo", "retrosheet_allplayers"],
    )
    problems = check_columns(actual, CSV_CONTRACT)

    assert problems == []


def test_a_column_renamed_in_the_csv_source_is_caught(db_conn):
    real_extract_csvs = retrosheet._extract_csvs

    def renamed_extract_csvs(year, zip_path):
        tables = real_extract_csvs(year, zip_path)
        tables["plays"] = tables["plays"].rename(columns={"gid": "game_id"})
        return tables

    with (
        patch.object(retrosheet, "_download_year", return_value=CSV_FIXTURE_ZIP),
        patch.object(retrosheet, "_extract_csvs", side_effect=renamed_extract_csvs),
    ):
        retrosheet._load_year(db_conn, 2025)
    db_conn.commit()

    actual = fetch_actual_columns(db_conn, ["retrosheet_plays"])
    problems = check_columns(actual, {"raw.retrosheet_plays": CSV_CONTRACT["raw.retrosheet_plays"]})

    assert any("raw.retrosheet_plays is missing column(s) gid" in p for p in problems)
    assert any("raw.retrosheet_plays has unexpected column(s) game_id" in p for p in problems)
