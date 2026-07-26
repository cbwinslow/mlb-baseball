"""conform.py has no network to mock — it's a pure in-database transform
reading already-landed raw tables, so this seeds raw.* directly with small,
hand-built rows (not reused connector fixtures — those don't carry
cross-referencing IDs) and asserts the join logic and idempotency on the
real test database. raw.register_people comes from a migration (always
present); raw.retrosheet_team/raw.retrosheet_gameinfo are dynamically
created by load_dataframe in production, so this test creates them itself
and drops them afterward, matching test_retrosheet_load.py's convention."""

import pytest

from mlb_baseball import conform

DYNAMIC_RAW_TABLES = ["raw.retrosheet_team", "raw.retrosheet_gameinfo"]


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in DYNAMIC_RAW_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("TRUNCATE raw.register_people")
        cur.execute("TRUNCATE core.game, core.team, core.player")
    db_conn.commit()


def _seed_raw_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('ATL', 'NL', 'Atlanta', 'Braves', '1966', '2025')"
        )

        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504010', '2025', '20250401', '0', 'NYM', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', "
            "'smitj001', 'jonet001', '')"
        )
        # No team seeded for NYM, and no player seeded for "unresolvable" —
        # both are real gaps found in production (see migration 0005's
        # comments), so this must resolve gracefully to NULL, not fail.
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504020', '2025', '20250402', '0', 'NYM', 'ATL', "
            "'1', '2', 'regular', 'ATL03', '34000', '175', 'D', "
            "'unresolvable', 'jonet001', '')"
        )

        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first, birth_year, birth_month, birth_day) "
            "VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', "
            "'Smith', 'John', '1990', '5', '10'), "
            "('jonet001', '234567', 'jonet01', '1002', 'uuid-2', "
            "'Jones', 'Tim', '1988', '7', '20')"
        )
    db_conn.commit()


def test_run_populates_team_player_and_game(db_conn):
    _seed_raw_tables(db_conn)

    counts = conform.run()

    assert counts == {"core.team": 1, "core.player": 2, "core.game": 2}
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, away_team_id, home_team_id, "
            "winning_pitcher_id, losing_pitcher_id "
            "FROM core.game ORDER BY retro_game_id"
        )
        rows = cur.fetchall()

    resolved, unresolved = rows
    assert resolved[0] == "ATL202504010"
    assert resolved[1] is None  # NYM never seeded into core.team
    assert resolved[2] is not None  # ATL resolves
    assert resolved[3] is not None  # smitj001 resolves
    assert resolved[4] is not None  # jonet001 resolves

    assert unresolved[0] == "ATL202504020"
    assert unresolved[3] is None  # "unresolvable" has no core.player row


def test_rerunning_replaces_instead_of_duplicating(db_conn):
    _seed_raw_tables(db_conn)

    conform.run()
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.game")
        assert cur.fetchone() == (2,)
        cur.execute("SELECT count(*) FROM core.team")
        assert cur.fetchone() == (1,)
        cur.execute("SELECT count(*) FROM core.player")
        assert cur.fetchone() == (2,)


def test_run_raises_actionable_error_when_raw_data_is_missing(db_conn):
    # raw.retrosheet_team/raw.retrosheet_gameinfo not created at all here —
    # the state of a genuinely fresh clone that's run `mlb migrate` but
    # never `mlb ingest`.
    with pytest.raises(RuntimeError) as exc_info:
        conform.run()

    assert "raw.retrosheet_team does not exist" in str(exc_info.value)
    assert "mlb ingest retrosheet_reference" in str(exc_info.value)
