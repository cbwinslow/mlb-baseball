"""conform.py has no network to mock — it's a pure in-database transform
reading already-landed raw tables, so this seeds raw.* directly with small,
hand-built rows (not reused connector fixtures — those don't carry
cross-referencing IDs) and asserts the join logic and idempotency on the
real test database. raw.register_people comes from a migration (always
present); raw.retrosheet_team/raw.retrosheet_gameinfo are dynamically
created by load_dataframe in production, so this test creates them itself
and drops them afterward, matching test_retrosheet_load.py's convention."""

from decimal import Decimal

import pytest

from mlb_baseball import conform

DYNAMIC_RAW_TABLES = ["raw.retrosheet_team", "raw.retrosheet_gameinfo"]


def _reset_dynamic_tables(conn):
    """The actual cleanup logic, extracted so it's directly testable —
    see test_reset_dynamic_tables_survives_an_aborted_transaction below.

    Real bug found in this review: without the rollback() first, a test
    whose own setup failed mid-transaction leaves the connection in
    InFailedSqlTransaction state, and every statement below fails too
    (Postgres refuses any command until the aborted transaction is rolled
    back) — silently skipping cleanup entirely and leaving a dynamic table
    behind permanently, which then poisons every later, unrelated test run
    with a spurious "already exists" error. Matches drop_tables_after's own
    existing "drop any lingering read-only transaction first" precedent in
    conftest.py.

    DELETE, not TRUNCATE (GitHub issue #2): core.play/core.pitch are
    season-partitioned (~150+ partitions each, migration 0011) --
    TRUNCATE-ing them (even just listed explicitly, no CASCADE needed)
    still has to fsync every individual partition file, observed directly
    taking 3+ hours across this file's ~40 tests where it used to take a
    few minutes. Fixture rows are always a handful per test, so a plain
    DELETE (ordinary WAL-logged DML, no per-partition-file operation) is
    correct and fast regardless of partition count. Order matters here in
    a way TRUNCATE's single combined statement didn't need to worry about:
    each DELETE must run after every table that references it is already
    cleared, or it fails on a live FK -- play/pitch/market/game_feature
    all reference game, so game can't be cleared first; venue is
    referenced by game, so venue must be last, not first."""
    conn.rollback()
    with conn.cursor() as cur:
        for table in DYNAMIC_RAW_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("TRUNCATE raw.register_people")
        for table in (
            "core.play", "core.pitch", "core.market", "gold.game_feature",
            "gold.prediction", "core.game", "core.team_alias",
            "core.player_war", "core.standing", "core.player", "core.team",
            "core.venue",
        ):
            cur.execute(f"DELETE FROM {table}")
    conn.commit()


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    _reset_dynamic_tables(db_conn)


def test_reset_dynamic_tables_survives_an_aborted_transaction(db_conn):
    # Regression: found the hard way while verifying an unrelated schema
    # change — a stray raw.retrosheet_team left behind by one broken test
    # run silently poisoned every subsequent, otherwise-unrelated test run
    # in this file with a spurious "already exists" error, since cleanup
    # itself was failing (and being ignored) every time.
    with db_conn.cursor() as cur:
        # Defensive, not redundant: this test's whole premise is "cleanup
        # must work even from a dirty state" — starting from a guaranteed-
        # clean slate here (rather than assuming one) keeps the test itself
        # deterministic regardless of what a prior, unrelated run left
        # behind.
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_team")
        cur.execute("CREATE TABLE raw.retrosheet_team (team_id text)")
    db_conn.commit()
    with db_conn.cursor() as cur, pytest.raises(Exception, match="does not exist"):
        cur.execute("SELECT * FROM raw.a_table_that_does_not_exist")
    # db_conn is now in InFailedSqlTransaction state — exactly the state a
    # test whose own setup raised mid-transaction would leave behind.

    _reset_dynamic_tables(db_conn)  # must not raise

    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_team')")
        assert cur.fetchone() == (None,)
        cur.execute("SELECT 1")  # connection is usable again, not still aborted
        assert cur.fetchone() == (1,)


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
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504010', '2025', '20250401', '0', 'NYM', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', "
            "'smitj001', 'jonet001', '', "
            "'72', 'fromlf', '10', 'sunny', 'none', 'dry')"
        )
        # No team seeded for NYM, and no player seeded for "unresolvable" —
        # both are real gaps found in production (see migration 0005's
        # comments), so this must resolve gracefully to NULL, not fail.
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504020', '2025', '20250402', '0', 'NYM', 'ATL', "
            "'1', '2', 'regular', 'ATL03', '34000', '175', 'D', "
            "'unresolvable', 'jonet001', '', "
            "'unknown', 'unknown', 'unknown', 'unknown', 'unknown', 'unknown')"
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


def test_build_games_normalizes_gametype_casing(db_conn):
    # Real production data: raw.retrosheet_gameinfo has exactly one row
    # (HOM193508100, a 1935 Homestead Grays game) with gametype "Regular"
    # instead of "regular" (see mlb doctor's gametype-casing check in
    # retrosheet.py). core.game.game_type must come out lowercased so a
    # case-sensitive `WHERE game_type = 'regular'` downstream doesn't
    # silently miss this game.
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE raw.retrosheet_gameinfo SET gametype = 'Regular' WHERE gid = 'ATL202504010'"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT game_type FROM core.game WHERE retro_game_id = 'ATL202504010'")
        assert cur.fetchone() == ("regular",)


def test_run_populates_team_player_and_game(db_conn):
    _seed_raw_tables(db_conn)

    counts = conform.run()

    # No raw.retrosheet_event/raw.mlb_playbyplay/raw.statcast_pitch/
    # raw.polymarket_*/raw.kalshi_*/raw.bref_war_*/raw.retrosheet_park/
    # raw.mlb_standing seeded in this test — every optional build step
    # must degrade to 0, not fail.
    assert counts == {
        "core.team": 1,
        "core.venue": 0,
        "core.team_alias": 1,  # ATL's own Kalshi ticker alias ("ATL" -> "ATL")
        "core.player": 2,
        "core.game": 2,
        "core.standing": 0,
        "core.play": 0,
        "core.pitch": 0,
        "core.market": 0,
        "core.player_war": 0,
    }
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


def test_rerunning_does_not_crash_when_gold_game_feature_references_a_game(db_conn):
    # Regression: gold.game_feature.game_id REFERENCES core.game(id)
    # (migration 0014, Phase 2's gold layer) -- Postgres refuses to
    # TRUNCATE core.game at all while that FK exists, purely because the
    # FK exists, regardless of how many rows gold.game_feature actually
    # has. run()'s own TRUNCATE statement had never been updated to
    # include gold.game_feature, found while adding a later Phase 2
    # feature and confirmed directly against a real FeatureNotSupported
    # error before being fixed here.
    _seed_raw_tables(db_conn)
    conform.run()
    with db_conn.cursor() as cur:
        cur.execute("SELECT id, season FROM core.game LIMIT 1")
        game_id, season = cur.fetchone()
        cur.execute(
            "INSERT INTO gold.game_feature (game_id, season, game_date) "
            "VALUES (%s, %s, '2025-04-01')",
            (game_id, season),
        )
    db_conn.commit()

    conform.run()  # must not raise psycopg.errors.FeatureNotSupported

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.game")
        assert cur.fetchone() == (2,)


def test_build_plays_and_pitches_unify_both_sources(db_conn):
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        # _seed_raw_tables deliberately leaves NYM (the away team) unresolved
        # to test the nullable-FK path elsewhere — this test needs both teams
        # resolved so the game_pk backfill's away_team_id/home_team_id IS NOT
        # NULL condition can actually match.
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('NYM', 'NL', 'New York', 'Mets', '1962', '2025')"
        )

        # raw.retrosheet_event: one play for the already-seeded, resolved game.
        cur.execute(
            "CREATE TABLE raw.retrosheet_event "
            "(game_id text, _season text, event_id text, inn_ct text, "
            "bat_home_id text, bat_id text, pit_id text, event_cd text, "
            "event_tx text, away_score_ct text, home_score_ct text, _scope text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event VALUES "
            "('ATL202504010', '2025', '1', '1', '0', 'smitj001', 'jonet001', "
            "'2', '43/G34', '0', '0', '2025_pbp')"
        )
        # Real production bug found via a genuine data collision: 1,872
        # historical games are published byte-identical in both Retrosheet's
        # general play-by-play archive and its dedicated Negro League
        # archive (same game_id/event_id, different _scope) — confirmed
        # directly, not assumed. Uncoalesced, this violates core.play's
        # UNIQUE(game_id, source, play_index). This second row simulates
        # that exact collision for the same game/event_id as above.
        cur.execute(
            "INSERT INTO raw.retrosheet_event VALUES "
            "('ATL202504010', '2025', '1', '1', '0', 'smitj001', 'jonet001', "
            "'2', '43/G34', '0', '0', '2025_negro_league')"
        )

        # raw.mlb_schedule + raw.mlb_playbyplay: a separate game, sourced
        # from MLB API instead — proves game_pk backfill + the mlb_api half
        # of core.play, and feeds core.pitch via the same game_pk.
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('999001', '2025-04-02', 'New York Mets', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '0', 'Truist Park', '1', '2')"
        )
        # This _season (2025) already has raw.retrosheet_gameinfo coverage
        # in this test, so _build_games' NOT EXISTS guard must exclude this
        # row from becoming a *new* core.game row — it only feeds the
        # game_pk backfill onto the already-Retrosheet-sourced game below.
        # core.game's ATL202504020 row is home=ATL/away=NYM on 2025-04-02 —
        # matches raw.mlb_schedule's away_name/home_name via city||nickname.

        cur.execute(
            "CREATE TABLE raw.mlb_playbyplay "
            "(game_pk text, _season text, at_bat_index text, inning text, "
            "half_inning text, batter_id text, pitcher_id text, "
            "event_type text, event text, away_score text, home_score text, "
            "balls text, strikes text, outs text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay VALUES "
            "('999001', '2025', '0', '1', 'top', '234567', '123456', "
            "'field_out', 'Groundout', '0', '0', '0', '0', '1')"
        )

        cur.execute(
            "CREATE TABLE raw.statcast_pitch "
            "(game_pk text, game_year text, at_bat_number text, "
            "pitch_number text, inning text, batter text, pitcher text, "
            "pitch_type text, pitch_name text, release_speed text, "
            "release_spin_rate text, launch_speed text, launch_angle text, "
            "hit_distance_sc text, description text, events text)"
        )
        cur.execute(
            "INSERT INTO raw.statcast_pitch VALUES "
            "('999001', '2025', '0', '1', '1', '234567', '123456', "
            "'FF', 'Four-Seam Fastball', '95.2', '2200', '', '', '', "
            "'called_strike', '')"
        )
    db_conn.commit()

    counts = conform.run()

    assert counts["core.play"] == 2
    assert counts["core.pitch"] == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT source, batter_id, pitcher_id, event_code, event_desc "
            "FROM core.play ORDER BY source"
        )
        rows = {row[0]: row for row in cur.fetchall()}
    assert rows["mlb_api"][1] is not None  # batter (jonet001's mlbam_id) resolved
    assert rows["mlb_api"][3] == "field_out"
    assert rows["retrosheet"][3] == "2"
    assert rows["retrosheet"][4] == "43/G34"

    with db_conn.cursor() as cur:
        cur.execute("SELECT game_pk FROM core.game WHERE retro_game_id = 'ATL202504020'")
        assert cur.fetchone() == ("999001",)
        cur.execute("SELECT pitch_type, release_speed FROM core.pitch")
        assert cur.fetchone() == ("FF", Decimal("95.2"))

    with db_conn.cursor() as cur:
        for table in [
            "raw.retrosheet_event",
            "raw.mlb_schedule",
            "raw.mlb_playbyplay",
            "raw.statcast_pitch",
        ]:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("TRUNCATE core.play, core.pitch")
    db_conn.commit()


def test_build_games_fills_seasons_retrosheet_has_not_published_yet(db_conn):
    # Real production gap found this session: raw.retrosheet_gameinfo tops
    # out at 2025 (Retrosheet's most recently published season) — without
    # this, core.game has zero rows for 2026, and the MLB-API half of
    # core.play (joined via game_pk) silently drops every current-season
    # row instead of erroring. This game (2026, Orioles home vs Yankees
    # away) has no Retrosheet coverage at all, only raw.mlb_schedule.
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2026'), "
            # _seed_raw_tables' ATL row only covers through 2025 (deliberately,
            # for its own tests) — a separate 2026 era row here, same city/
            # nickname, to let this test's home-team resolution succeed too.
            "('ATL', 'NL', 'Atlanta', 'Braves', '2026', '2026')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('888001', '2026-04-05', 'New York Yankees', 'Atlanta Braves', "
            "'2026', 'Final', 'R', '0', 'Truist Park', '3', '4')"
        )
    db_conn.commit()

    counts = conform.run()

    assert counts["core.game"] == 3  # 2 Retrosheet-sourced + 1 new MLB-API-sourced
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_pk, season, away_score, home_score, "
            "away_team_id, home_team_id, winning_pitcher_id, game_type "
            "FROM core.game WHERE season = 2026"
        )
        row = cur.fetchone()
    assert row[0] == "MLB888001"  # synthesized ID, never collides with a real Retrosheet one
    assert row[1] == "888001"
    assert row[2] == 2026
    assert row[3] == 3  # away_score
    assert row[4] == 4  # home_score
    assert row[5] is not None  # away (Yankees) resolved
    assert row[6] is not None  # home (Braves) resolved
    assert row[7] is None  # no pitcher ID resolution attempted for MLB-API-sourced games
    # MLB API's game_type is a single letter ("R") in the same column
    # Retrosheet uses a full word ("regular") for — confirmed against real
    # dated games (e.g. F=2025-09-30 Tigers@Guardians was the Wild Card
    # game), not guessed. Must map to Retrosheet's vocabulary so a
    # case-consistent `WHERE game_type = 'regular'` downstream doesn't
    # silently miss every MLB-API-sourced game.
    assert row[8] == "regular"

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        # play/pitch/market reference game — must truncate together, see run()'s comment.
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_run_raises_actionable_error_when_raw_data_is_missing(db_conn):
    # raw.retrosheet_team/raw.retrosheet_gameinfo not created at all here —
    # the state of a genuinely fresh clone that's run `mlb migrate` but
    # never `mlb ingest`.
    with pytest.raises(RuntimeError) as exc_info:
        conform.run()

    assert "raw.retrosheet_team does not exist" in str(exc_info.value)
    assert "mlb ingest retrosheet_reference" in str(exc_info.value)


def test_build_teams_treats_the_files_shared_max_last_year_as_open_ended(db_conn):
    # Real bug found extending conform.py, not hypothetical: Retrosheet's
    # own TEAMABR.TXT caps every currently-active team's last_year at the
    # same value (confirmed in production: exactly 30 rows -- the real
    # current MLB team count -- share it), silently NULLing every team
    # match for any season past that value. Two teams sharing the file's
    # own max get treated as still active (9999); a team with a genuinely
    # earlier, distinct last_year (a real relocation/rename, like MON's
    # 2004) keeps its real value.
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('ATL', 'NL', 'Atlanta', 'Braves', '1966', '2021'), "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2021'), "
            "('MON', 'NL', 'Montreal', 'Expos', '1969', '2004')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202104010', '2021', '20210401', '0', 'NYA', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT retro_team_id, last_year FROM core.team ORDER BY retro_team_id")
        rows = dict(cur.fetchall())
    assert rows["ATL"] == 9999
    assert rows["NYA"] == 9999
    assert rows["MON"] == 2004


def test_build_plays_includes_win_probability_for_mlb_api_rows(db_conn):
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('NYM', 'NL', 'New York', 'Mets', '1962', '2025')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('999001', '2025-04-02', 'New York Mets', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '0', 'Truist Park', '1', '2')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_playbyplay "
            "(game_pk text, _season text, at_bat_index text, inning text, "
            "half_inning text, batter_id text, pitcher_id text, "
            "event_type text, event text, away_score text, home_score text, "
            "balls text, strikes text, outs text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay VALUES "
            "('999001', '2025', '0', '1', 'top', '234567', '123456', "
            "'field_out', 'Groundout', '0', '0', '0', '0', '1')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_win_prob "
            "(game_pk text, at_bat_index text, inning text, half_inning text, "
            "home_win_probability text, away_win_probability text, "
            "home_win_probability_added text, _season text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_win_prob VALUES "
            "('999001', '0', '1', 'top', '52.2', '47.8', '2.2', NULL)"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_win_probability, away_win_probability "
            "FROM core.play WHERE source = 'mlb_api'"
        )
        assert cur.fetchone() == (Decimal("52.2"), Decimal("47.8"))

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule, raw.mlb_playbyplay, raw.mlb_win_prob")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def _seed_market_game(db_conn):
    """One resolvable core.game row (Yankees @ Braves, 2026-05-23) plus a
    Polymarket event and a Kalshi market both referring to it — the shared
    fixture for every core.market test below."""
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('ATL', 'NL', 'Atlanta', 'Braves', '1966', '2021'), "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2021')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202605230', '2026', '20260523', '0', 'NYA', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )

        cur.execute(
            "CREATE TABLE raw.polymarket_event "
            "(id text, slug text, sport text, teams text, closed text)"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_event VALUES ("
            "'1', 'mlb-nyy-atl-2026-05-23', "
            "'{''id'': 8, ''sport'': ''mlb''}', "
            "'[{''name'': ''New York Yankees'', ''ordering'': ''away''}, "
            "{''name'': ''Atlanta Braves'', ''ordering'': ''home''}]', "
            "'False')"
        )
        cur.execute("CREATE TABLE raw.polymarket_market (id text, event_id text, volume text)")
        cur.execute("INSERT INTO raw.polymarket_market VALUES ('10', '1', '5000')")
        cur.execute(
            "CREATE TABLE raw.polymarket_outcome (market_id text, outcome text, price text)"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_outcome VALUES "
            "('10', 'New York Yankees', '0.4'), "
            "('10', 'Atlanta Braves', '0.6')"
        )

        cur.execute(
            "CREATE TABLE raw.kalshi_market "
            "(ticker text, event_ticker text, status text, volume_fp text, "
            "yes_bid_dollars text, yes_ask_dollars text, last_price_dollars text)"
        )
        cur.execute(
            "INSERT INTO raw.kalshi_market VALUES "
            "('KXMLBGAME-26MAY231905NYAATL-ATL', 'KXMLBGAME-26MAY231905NYAATL', "
            "'finalized', '1000', '0.58', '0.62', '0.60')"
        )
    db_conn.commit()


def _drop_market_fixtures(db_conn):
    with db_conn.cursor() as cur:
        for table in [
            "raw.polymarket_event",
            "raw.polymarket_market",
            "raw.polymarket_outcome",
            "raw.kalshi_market",
        ]:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    db_conn.commit()


def test_build_market_matches_polymarket_and_kalshi_to_a_core_game(db_conn):
    _seed_market_game(db_conn)

    counts = conform.run()

    # 2 Polymarket outcome rows (away + home) + 1 Kalshi market row.
    assert counts["core.market"] == 3
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT m.source, m.market_ref, m.implied_probability, m.status, t.retro_team_id "
            "FROM core.market m JOIN core.team t ON t.id = m.team_id "
            "WHERE m.game_id IS NOT NULL "
            "ORDER BY m.source, t.retro_team_id"
        )
        rows = cur.fetchall()
    by_team = {(source, team): (ref, price, status) for source, ref, price, status, team in rows}

    assert by_team[("kalshi", "ATL")] == (
        "KXMLBGAME-26MAY231905NYAATL-ATL",
        Decimal("0.60"),
        "finalized",
    )
    assert by_team[("polymarket", "ATL")][1] == Decimal("0.6")
    assert by_team[("polymarket", "NYA")][1] == Decimal("0.4")

    _drop_market_fixtures(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_market_leaves_market_ref_unique_across_both_outcome_rows(db_conn):
    # Regression: Polymarket's away/home outcome rows share the same
    # underlying market id — core.market's UNIQUE(source, market_ref)
    # would reject the second row if market_ref were just that id.
    _seed_market_game(db_conn)

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT market_ref) FROM core.market WHERE source = 'polymarket'"
        )
        assert cur.fetchone() == (2,)

    _drop_market_fixtures(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_market_leaves_kalshi_price_as_bid_ask_midpoint_when_untraded(db_conn):
    # Real production case: a newly-listed Kalshi market has real bid/ask
    # quotes but last_price_dollars is still its zero-value placeholder
    # (never traded yet) -- the midpoint is the honest fallback, not 0.
    _seed_market_game(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("UPDATE raw.kalshi_market SET last_price_dollars = '0.0000'")
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT implied_probability FROM core.market WHERE source = 'kalshi'")
        assert cur.fetchone() == (Decimal("0.60"),)  # (0.58 + 0.62) / 2

    _drop_market_fixtures(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_market_rerunning_replaces_instead_of_duplicating(db_conn):
    _seed_market_game(db_conn)

    conform.run()
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.market")
        assert cur.fetchone() == (3,)

    _drop_market_fixtures(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_player_war_lands_batting_and_pitching_rows(db_conn):
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.bref_war_batting "
            "(name_common text, mlb_id text, player_id text, year_id text, "
            "team_id text, stint_id text, lg_id text, pitcher text, g text, "
            "pa text, salary text, runs_above_avg text, runs_above_avg_off text, "
            "runs_above_avg_def text, war_rep text, waa text, war text)"
        )
        cur.execute(
            "INSERT INTO raw.bref_war_batting VALUES "
            "('John Smith', '123456', 'smitj01', '2025', 'ATL', '1', 'NL', "
            "'N', '150', '600', '1000000', '10.5', '6.0', '4.5', '0.5', '3.2', '3.7')"
        )
        cur.execute(
            "CREATE TABLE raw.bref_war_pitching "
            "(name_common text, mlb_id text, player_id text, year_id text, "
            "team_id text, stint_id text, lg_id text, g text, gs text, "
            "ra text, xra text, bip text, bip_perc text, salary text, "
            "era_plus text, war_rep text, waa text, waa_adj text, war text)"
        )
        cur.execute(
            "INSERT INTO raw.bref_war_pitching VALUES "
            "('Tim Jones', '234567', 'jonet01', '2025', 'ATL', '1', 'NL', "
            "'30', '30', '80', '85', '500', '0.15', '2000000', "
            "'120', '0.3', '1.1', '1.0', '1.4')"
        )
    db_conn.commit()

    counts = conform.run()

    assert counts["core.player_war"] == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT p.retro_id, w.is_pitcher, w.war, w.runs_above_avg "
            "FROM core.player_war w JOIN core.player p ON p.id = w.player_id "
            "ORDER BY w.is_pitcher"
        )
        rows = cur.fetchall()
    assert rows[0] == ("smitj001", False, Decimal("3.7"), Decimal("10.5"))
    assert rows[1] == ("jonet001", True, Decimal("1.4"), None)  # pitching has no runs_above_avg

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.bref_war_batting, raw.bref_war_pitching")
        cur.execute("TRUNCATE core.player_war")
    db_conn.commit()


def test_build_team_aliases_seeds_only_the_current_team_era(db_conn):
    # _TEAM_ALIAS_SEED's WHERE clause requires last_year = 9999 (the "still
    # active" sentinel _build_teams assigns) -- a retro_team_id that only
    # exists as a past, ended era (Montreal's 'MON', which never became the
    # Nationals in Retrosheet's own vocabulary -- 'WAS' is a separate
    # retro_team_id) must not get an alias row: core.team_alias.alias is
    # UNIQUE, and an ended era isn't the team Polymarket/Kalshi mean today.
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('ATL', 'NL', 'Atlanta', 'Braves', '1966', '2025'), "
            "('MON', 'NL', 'Montreal', 'Expos', '1969', '2004')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504010', '2025', '20250401', '0', 'ATL', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
    db_conn.commit()

    counts = conform.run()

    assert counts["core.team_alias"] == 1  # only ATL (last_year=9999), not MON
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT a.alias FROM core.team_alias a "
            "JOIN core.team t ON t.id = a.team_id WHERE t.retro_team_id = 'MON'"
        )
        assert cur.fetchall() == []
        cur.execute(
            "SELECT a.alias FROM core.team_alias a "
            "JOIN core.team t ON t.id = a.team_id WHERE t.retro_team_id = 'ATL'"
        )
        assert cur.fetchone() == ("ATL",)


def test_build_team_aliases_rerunning_replaces_instead_of_duplicating(db_conn):
    _seed_raw_tables(db_conn)

    conform.run()
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.team_alias")
        assert cur.fetchone() == (1,)


def _seed_mlb_team_id_scenario(db_conn):
    """OAK/TEX, 3 Retrosheet-sourced 2024 games (one with a deliberately
    noisy/wrong MLB id, matching the shape of the real 2004 Hurricane
    Frances Cubs/Marlins anomaly confirmed in production) plus one 2025
    MLB-API-sourced game where the Athletics are listed under their bare,
    mid-relocation name "Athletics" (no city) -- the real 42-row production
    gap this design exists to fix."""
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('OAK', 'AL', 'Oakland', 'Athletics', '1968', '2025'), "
            "('TEX', 'AL', 'Texas', 'Rangers', '1972', '2025')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('OAK202404010', '2024', '20240401', '0', 'TEX', 'OAK', "
            "'3', '5', 'regular', 'OAK01', '10000', '180', 'N', '', '', '', "
            "'', '', '', '', '', ''), "
            "('OAK202404020', '2024', '20240402', '0', 'TEX', 'OAK', "
            "'1', '2', 'regular', 'OAK01', '11000', '175', 'N', '', '', '', "
            "'', '', '', '', '', ''), "
            "('OAK202404030', '2024', '20240403', '0', 'TEX', 'OAK', "
            "'4', '6', 'regular', 'OAK01', '12000', '190', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )

        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, away_score text, home_score text, "
            "away_id text, home_id text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('500001', '2024-04-01', 'Texas Rangers', 'Oakland Athletics', "
            "'2024', 'Final', 'R', '0', 'Oakland Coliseum', '3', '5', '140', '133'), "
            "('500002', '2024-04-02', 'Texas Rangers', 'Oakland Athletics', "
            "'2024', 'Final', 'R', '0', 'Oakland Coliseum', '1', '2', '140', '133'), "
            # Deliberately wrong home_id for this one game -- the noisy
            # outlier vote the majority-vote logic must not be swayed by.
            "('500003', '2024-04-03', 'Texas Rangers', 'Oakland Athletics', "
            "'2024', 'Final', 'R', '0', 'Oakland Coliseum', '4', '6', '140', '999'), "
            # 2025: no Retrosheet coverage for this season at all (nothing
            # inserted into raw.retrosheet_gameinfo above for it), and
            # away_name is the bare 'Athletics' MLB's schedule really uses
            # mid-relocation -- can't string-match 'Oakland Athletics'.
            "('500004', '2025-04-01', 'Athletics', 'Texas Rangers', "
            "'2025', 'Final', 'R', '0', 'Globe Life Field', '2', '1', '133', '140')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
    db_conn.commit()


def test_backfill_mlb_team_id_uses_majority_vote_despite_a_noisy_outlier(db_conn):
    _seed_mlb_team_id_scenario(db_conn)

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT retro_team_id, mlb_team_id FROM core.team ORDER BY retro_team_id")
        team_ids = dict(cur.fetchall())
    assert team_ids["OAK"] == 133  # majority (2 votes) beats the noisy 999 (1 vote)
    assert team_ids["TEX"] == 140

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_backfill_team_ids_via_mlb_id_fixes_bare_name_mismatch(db_conn):
    _seed_mlb_team_id_scenario(db_conn)

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT t.retro_team_id FROM core.game g "
            "JOIN core.team t ON t.id = g.away_team_id WHERE g.game_pk = '500004'"
        )
        assert cur.fetchone() == ("OAK",)  # resolved despite the bare "Athletics" name

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_backfill_mlb_team_id_degrades_gracefully_without_away_id_column(db_conn):
    # A raw.mlb_schedule present but missing away_id/home_id (an older
    # snapshot, or a partially-migrated deployment) must not crash the
    # whole conform run -- same "optional dependency not ready yet"
    # tolerance as the table not existing at all.
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, away_score text, home_score text)"
        )
    db_conn.commit()

    conform.run()  # must not raise

    with db_conn.cursor() as cur:
        cur.execute("SELECT mlb_team_id FROM core.team")
        assert cur.fetchone() == (None,)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_market_matches_polymarket_rebrand_alias(db_conn):
    # Regression for a real production gap: Retrosheet's own TEAMABR.TXT
    # still lists Tampa Bay under 'Rays' as its nickname but Polymarket's
    # own event data uses 'Tampa Bay Rays' consistently with no
    # abbreviation issue -- the actual real mismatches are Devil
    # Rays/Anaheim Angels/Cleveland Indians vs. today's names. This test
    # uses the Angels (core.team nickname stays "Angels" going back to
    # Retrosheet's 'ANA' era while Polymarket's event data says "Los
    # Angeles Angels") to exercise the "rebrand" alias path end to end.
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('ANA', 'AL', 'Anaheim', 'Angels', '1997', '2025'), "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2025')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ANA202605230', '2026', '20260523', '0', 'NYA', 'ANA', "
            "'3', '5', 'regular', 'ANA01', '35000', '185', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
        cur.execute(
            "CREATE TABLE raw.polymarket_event "
            "(id text, slug text, sport text, teams text, closed text)"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_event VALUES ("
            "'1', 'mlb-nyy-laa-2026-05-23', "
            "'{''id'': 8, ''sport'': ''mlb''}', "
            "'[{''name'': ''New York Yankees'', ''ordering'': ''away''}, "
            "{''name'': ''Los Angeles Angels'', ''ordering'': ''home''}]', "
            "'False')"
        )
        cur.execute("CREATE TABLE raw.polymarket_market (id text, event_id text, volume text)")
        cur.execute("INSERT INTO raw.polymarket_market VALUES ('10', '1', '5000')")
        cur.execute(
            "CREATE TABLE raw.polymarket_outcome (market_id text, outcome text, price text)"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_outcome VALUES ('10', 'Los Angeles Angels', '0.55')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT m.implied_probability FROM core.market m "
            "JOIN core.team t ON t.id = m.team_id WHERE t.retro_team_id = 'ANA'"
        )
        assert cur.fetchone() == (Decimal("0.55"),)

    _drop_market_fixtures(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_market_matches_kalshi_athletics_ticker_via_alias(db_conn):
    # Regression for the exact bug this test suite caught before it ever
    # reached production: _TEAM_ALIAS_SEED's first entry originally had
    # its (retro_team_id, alias) tuple order backwards ("ATH" mapped to
    # itself instead of to "OAK"), which would have silently made every
    # Kalshi "ATH" ticker fail to match any team.
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('OAK', 'AL', 'Oakland', 'Athletics', '1968', '2025'), "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2025')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('OAK202605230', '2026', '20260523', '0', 'NYA', 'OAK', "
            "'3', '5', 'regular', 'OAK01', '10000', '180', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
        cur.execute(
            "CREATE TABLE raw.kalshi_market "
            "(ticker text, event_ticker text, status text, volume_fp text, "
            "yes_bid_dollars text, yes_ask_dollars text, last_price_dollars text)"
        )
        cur.execute(
            "INSERT INTO raw.kalshi_market VALUES "
            "('KXMLBGAME-26MAY231905NYAOAK-ATH', 'KXMLBGAME-26MAY231905NYAOAK', "
            "'finalized', '1000', '0.30', '0.34', '0.32')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT m.implied_probability FROM core.market m "
            "JOIN core.team t ON t.id = m.team_id WHERE t.retro_team_id = 'OAK'"
        )
        assert cur.fetchone() == (Decimal("0.32"),)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.kalshi_market")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def _seed_retrosheet_park(db_conn, parkid="ATL03", name="Truist Park"):
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_park "
            "(parkid text, name text, city text, state text, league text, "
            'start text, "end" text)'
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_park VALUES (%s, %s, "
            "'Atlanta', 'GA', 'NL', '04/14/2017', NULL)",
            (parkid, name),
        )
    db_conn.commit()


def test_build_venues_links_to_game_and_lands_retrosheet_weather(db_conn):
    # raw.retrosheet_gameinfo's own weather columns (temp/wind/sky/precip/
    # field condition) were confirmed landed in production, 97%+ filled for
    # wind/sky/precip, 71% for temp (1900-2025), but sat entirely unused
    # until this change — see migration 0010. Real venue-name join test:
    # ATL03 in raw.retrosheet_gameinfo.site must resolve to the same-code
    # row in raw.retrosheet_park via an exact match, no fuzzy string
    # matching involved.
    _seed_raw_tables(db_conn)
    _seed_retrosheet_park(db_conn)

    counts = conform.run()

    assert counts["core.venue"] == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT v.retro_park_id, g.temp_f, g.wind_dir, g.wind_speed_mph, "
            "g.sky, g.precip, g.field_cond "
            "FROM core.game g JOIN core.venue v ON v.id = g.venue_id "
            "WHERE g.retro_game_id = 'ATL202504010'"
        )
        assert cur.fetchone() == ("ATL03", 72, "fromlf", 10, "sunny", "none", "dry")

    with db_conn.cursor() as cur:
        # The second seeded game has 'unknown' in every weather column —
        # must come out honestly NULL, not the literal string "unknown".
        cur.execute(
            "SELECT temp_f, wind_dir, sky, precip, field_cond FROM core.game "
            "WHERE retro_game_id = 'ATL202504020'"
        )
        assert cur.fetchone() == (None, None, None, None, None)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_park")
    db_conn.commit()


def test_build_venues_enriches_from_mlb_venue_by_exact_name_match_only(db_conn):
    _seed_raw_tables(db_conn)
    _seed_retrosheet_park(db_conn, name="Truist Park")
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.mlb_venue "
            "(venue_id text, name text, latitude text, longitude text, "
            "capacity text, turf_type text, roof_type text, "
            "left_line text, center text, right_line text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_venue VALUES "
            "('4705', 'Truist Park', '33.8908', '-84.4678', '41084', "
            "'Grass', 'Open', '335', '400', '325')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT mlb_venue_id, latitude, longitude, capacity, turf_type, "
            "roof_type, left_line, center, right_line "
            "FROM core.venue WHERE retro_park_id = 'ATL03'"
        )
        row = cur.fetchone()
    assert row == (
        4705,
        Decimal("33.8908"),
        Decimal("-84.4678"),
        41084,
        "Grass",
        "Open",
        335,
        400,
        325,
    )

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_park, raw.mlb_venue")
    db_conn.commit()


def test_build_venues_leaves_enrichment_null_when_no_exact_name_match(db_conn):
    # "leave it NULL, don't guess" — same precedent as core.game.game_pk's
    # own backfill. A near-but-not-exact name (e.g. a rebrand/typo) must
    # not get guessed at.
    _seed_raw_tables(db_conn)
    _seed_retrosheet_park(db_conn, name="Truist Park")
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.mlb_venue "
            "(venue_id text, name text, latitude text, longitude text, "
            "capacity text, turf_type text, roof_type text, "
            "left_line text, center text, right_line text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_venue VALUES "
            "('4705', 'SunTrust Park', '33.8908', '-84.4678', '41084', "
            "'Grass', 'Open', '335', '400', '325')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT mlb_venue_id FROM core.venue WHERE retro_park_id = 'ATL03'")
        assert cur.fetchone() == (None,)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_park, raw.mlb_venue")
    db_conn.commit()


def test_build_venues_rerunning_replaces_instead_of_duplicating(db_conn):
    _seed_raw_tables(db_conn)
    _seed_retrosheet_park(db_conn)

    conform.run()
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.venue")
        assert cur.fetchone() == (1,)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_park")
    db_conn.commit()


def _seed_mlb_standing_rows(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.mlb_standing "
            "(division_id text, div_name text, team_id text, div_rank text, "
            "w text, l text, gb text, wc_rank text, wc_gb text, "
            "league_rank text, sport_rank text, _season text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_standing VALUES "
            "('200', 'AL West', '133', '1', '95', '67', '-', '1', '-', "
            "'1', '2', '2024'), "
            # TEX's wc_rank is '-' here -- "not ranked" (out of wildcard
            # contention entirely), a real production value distinct from
            # gb/wc_gb's own '-' meaning "0 games back". Confirmed
            # directly: crashed conform.py the first time this ran against
            # real production data (InvalidTextRepresentation casting '-'
            # to integer) before wc_rank got the same digits-only guard
            # div_rank/league_rank/sport_rank already had.
            "('200', 'AL West', '140', '2', '85', '77', '10.0', '-', '5.5', "
            "'8', '15', '2024')"
        )
    db_conn.commit()


def test_build_standings_resolves_team_via_mlb_team_id(db_conn):
    # core.standing resolves team_id via core.team.mlb_team_id (the same
    # numeric anchor ADR-029 built for exactly this kind of join), not a
    # second round of name matching — reuses the OAK=133/TEX=140
    # mlb_team_id scenario already exercised by the ADR-029 tests above.
    _seed_mlb_team_id_scenario(db_conn)
    _seed_mlb_standing_rows(db_conn)

    counts = conform.run()

    assert counts["core.standing"] == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT t.retro_team_id, s.div_rank, s.wins, s.losses, "
            "s.games_back, s.wildcard_rank, s.wildcard_games_back "
            "FROM core.standing s JOIN core.team t ON t.id = s.team_id "
            "ORDER BY s.div_rank"
        )
        rows = cur.fetchall()
    # '-' (the division/wildcard leader's own "0 games back" marker) must
    # resolve to 0, not NULL — a plain unsigned-digits regex would
    # silently drop exactly the leader rows.
    assert rows[0] == ("OAK", 1, 95, 67, Decimal("0"), 1, Decimal("0"))
    # TEX's wc_rank of '-' means "not ranked" (out of contention) here —
    # an honest NULL, not a guessed 0 (that's gb/wc_gb's own '-' meaning).
    assert rows[1] == ("TEX", 2, 85, 77, Decimal("10.0"), None, Decimal("5.5"))

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule, raw.mlb_standing")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_standings_rerunning_replaces_instead_of_duplicating(db_conn):
    _seed_mlb_team_id_scenario(db_conn)
    _seed_mlb_standing_rows(db_conn)

    conform.run()
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.standing")
        assert cur.fetchone() == (2,)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule, raw.mlb_standing")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_player_war_leaves_unmatched_bref_row_as_null_instead_of_dropping(db_conn):
    # Real bug found in this review: an inner JOIN here silently dropped
    # any bref row whose bbref_id didn't resolve to a core.player row (517
    # of 126,418 real production batting rows, confirmed directly) with no
    # trace at all. A LEFT JOIN brings this in line with every other
    # optional resolution in this file (core.game.game_pk, etc.) — land
    # the row with an honest NULL player_id instead of vanishing it.
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.bref_war_batting "
            "(name_common text, mlb_id text, player_id text, year_id text, "
            "team_id text, stint_id text, lg_id text, pitcher text, g text, "
            "pa text, salary text, runs_above_avg text, runs_above_avg_off text, "
            "runs_above_avg_def text, war_rep text, waa text, war text)"
        )
        cur.execute(
            "INSERT INTO raw.bref_war_batting VALUES "
            "('Nobody Resolvable', '999999', 'nobod01', '2025', 'ATL', '1', "
            "'NL', 'N', '10', '20', '100000', '0.1', '0.1', '0.0', "
            "'0.0', '0.1', '0.1')"
        )
    db_conn.commit()

    counts = conform.run()

    assert counts["core.player_war"] == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT player_id, war FROM core.player_war")
        assert cur.fetchone() == (None, Decimal("0.1"))


def test_backfill_game_pk_does_not_overwrite_an_already_correct_value(db_conn):
    # Real bug found in production, one step past the doubleheader fix
    # above: the UPDATE had no guard against touching a row that already
    # got its correct game_pk from _build_games' second INSERT (the
    # MLB-API-only path, for seasons Retrosheet hasn't published). MLB's
    # own suspended-and-resumed-game quirk (documented in _build_games'
    # own comment, confirmed directly: game 824912 listed under both
    # 2026-06-16 and 2026-06-17) means two genuinely distinct schedule
    # game_ids can share the same date/teams/game_num — before this fix,
    # the ambiguous match let one already-correct row get clobbered with
    # the other's game_pk, producing a duplicate (confirmed in production:
    # game_pk 824912 ended up on both retro_game_id MLB824912 *and*
    # MLB824913).
    _seed_raw_tables(db_conn)  # retrosheet_gameinfo only covers 2025
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2026'), "
            "('ATL', 'NL', 'Atlanta', 'Braves', '2026', '2026')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, away_score text, home_score text)"
        )
        # Two distinct game_ids, same date/teams/game_num — each creates
        # its own core.game row via the second INSERT, each with its own
        # correct game_pk from the start.
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('900001', '2026-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2026', 'Final', 'R', '1', 'Truist Park', '3', '5'), "
            "('900002', '2026-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2026', 'Final', 'R', '1', 'Truist Park', '3', '5')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_pk FROM core.game "
            "WHERE retro_game_id IN ('MLB900001', 'MLB900002') "
            "ORDER BY retro_game_id"
        )
        rows = dict(cur.fetchall())
    assert rows["MLB900001"] == "900001"
    assert rows["MLB900002"] == "900002"

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_backfill_game_pk_distinguishes_doubleheader_games(db_conn):
    # Real bug found in this review: matching on (game_date, away team,
    # home team) alone can't distinguish the two games of a doubleheader —
    # raw.mlb_schedule correctly has two separate rows (confirmed directly
    # against real production data: 1925-07-07 Cardinals@Braves is game_id
    # 100003/game_num 1 and game_id 100004/game_num 2), but without
    # game_num in the match, both core.game rows collided onto the same
    # game_pk in production (12,662 distinct game_pk values shared by 2
    # rows each, 25,347 rows total — every one a doubleheader).
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('ATL', 'NL', 'Atlanta', 'Braves', '1966', '2025'), "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2025')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504010', '2025', '20250401', '1', 'NYA', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', '', '', '', "
            "'', '', '', '', '', ''), "
            "('ATL202504012', '2025', '20250401', '2', 'NYA', 'ATL', "
            "'1', '2', 'regular', 'ATL03', '30000', '175', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('700001', '2025-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '1', 'Truist Park', '3', '5'), "
            "('700002', '2025-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '2', 'Truist Park', '1', '2')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_pk FROM core.game "
            "WHERE retro_game_id IN ('ATL202504010', 'ATL202504012') "
            "ORDER BY retro_game_id"
        )
        rows = dict(cur.fetchall())
    assert rows["ATL202504010"] == "700001"
    assert rows["ATL202504012"] == "700002"
    assert rows["ATL202504010"] != rows["ATL202504012"]

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_build_pitches_leaves_unmatched_statcast_row_as_null_instead_of_dropping(db_conn):
    # Real bug found in this review: an inner JOIN here silently dropped
    # every raw.statcast_pitch row whose game_pk didn't resolve to a
    # core.game row (2,535,802 of 13,396,090 real production rows, 18.9%,
    # confirmed directly) with no trace at all. A LEFT JOIN brings this in
    # line with core.game.game_pk's own "leave it NULL, don't guess"
    # precedent — same fix already applied to core.player_war above.
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.statcast_pitch "
            "(game_pk text, game_year text, at_bat_number text, "
            "pitch_number text, inning text, batter text, pitcher text, "
            "pitch_type text, pitch_name text, release_speed text, "
            "release_spin_rate text, launch_speed text, launch_angle text, "
            "hit_distance_sc text, description text, events text)"
        )
        cur.execute(
            "INSERT INTO raw.statcast_pitch VALUES "
            "('999999999', '2025', '0', '1', '1', '123456', '234567', "
            "'FF', 'Four-Seam Fastball', '95.2', '2200', '', '', '', "
            "'called_strike', '')"
        )
    db_conn.commit()

    counts = conform.run()

    assert counts["core.pitch"] == 1
    with db_conn.cursor() as cur:
        cur.execute("SELECT game_id, pitch_type FROM core.pitch")
        assert cur.fetchone() == (None, "FF")

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute("TRUNCATE core.pitch")
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.bref_war_batting")
        cur.execute("TRUNCATE core.player_war")
    db_conn.commit()


def test_health_check_lahman_reconciliation_matches_real_win_totals(db_conn):
    # Exercises the actual SQL wired into conform.py's health_check(), not
    # just the generic check logic (already covered in test_health.py).
    # _seed_raw_tables' two games both have ATL as the (resolved) home
    # team and ATL winning both (5>3, then 2>1) — a real raw.lahman_teams
    # row claiming exactly 2 wins should reconcile cleanly.
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.lahman_teams "
            "(teamidretro text, yearid text, w text, l text, g text, lgid text)"
        )
        cur.execute("INSERT INTO raw.lahman_teams VALUES ('ATL', '2025', '2', '0', '2', 'NL')")
    db_conn.commit()

    conform.run()

    check = next(
        c for c in conform.health_check() if c.name == "core.game team-season wins vs Lahman"
    )
    assert check.ok, check.detail

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.lahman_teams")
    db_conn.commit()


def test_health_check_lahman_reconciliation_flags_a_real_mismatch(db_conn):
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.lahman_teams "
            "(teamidretro text, yearid text, w text, l text, g text, lgid text)"
        )
        # Claims 20 wins where core.game only has 2 -- well beyond the
        # tolerance=3 allowance for legitimate historical discrepancies.
        cur.execute("INSERT INTO raw.lahman_teams VALUES ('ATL', '2025', '20', '0', '20', 'NL')")
    db_conn.commit()

    conform.run()

    check = next(
        c for c in conform.health_check() if c.name == "core.game team-season wins vs Lahman"
    )
    assert not check.ok
    assert "ATL-2025" in check.detail

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.lahman_teams")
    db_conn.commit()


def test_health_check_lahman_team_count_matches_and_flags_mismatch(db_conn):
    # _seed_raw_tables only resolves one team (ATL) for 2025 -- NYM is
    # deliberately left unresolved, so core.game's team-count for that
    # season is exactly 1. Filtered to lgid IN ('AL','NL') because
    # raw.lahman_teams also carries Negro League team-seasons that
    # core.game's game_type='regular' scope was never meant to include
    # (confirmed directly against production: 1932 alone has 22
    # Negro-League teamidretro values mixed in).
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.lahman_teams "
            "(teamidretro text, yearid text, w text, l text, g text, lgid text)"
        )
        cur.execute("INSERT INTO raw.lahman_teams VALUES ('ATL', '2025', '2', '0', '2', 'NL')")
    db_conn.commit()
    conform.run()

    check = next(
        c for c in conform.health_check() if c.name == "core.game team count vs Lahman"
    )
    assert check.ok, check.detail

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.lahman_teams VALUES "
            "('NYA', '2025', '90', '72', '162', 'AL'), "
            "('BOS', '2025', '85', '77', '162', 'AL')"
        )
    db_conn.commit()

    check = next(
        c for c in conform.health_check() if c.name == "core.game team count vs Lahman"
    )
    assert not check.ok
    assert "2025" in check.detail

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.lahman_teams")
    db_conn.commit()


def test_health_check_doubleheader_identity_flags_a_collision(db_conn):
    # Regression, end to end: before migration 0011's game_pk-overwrite
    # guard, this exact scenario (two games, same date/teams, distinct
    # game_number, both landing on the same game_pk) produced a real
    # duplicate in production. conform.run() itself should no longer
    # produce one (see test_backfill_game_pk_distinguishes_doubleheader_games
    # above) -- this seeds the collision directly into core.game (same
    # date, same teams, distinct game_number -- a real doubleheader shape)
    # to prove the health check would actually catch it if the fix ever
    # regressed.
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('ATL', 'NL', 'Atlanta', 'Braves', '1966', '2025'), "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2025')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, "
            "temp text, winddir text, windspeed text, sky text, "
            "precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504011', '2025', '20250401', '1', 'NYA', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', '', '', '', "
            "'', '', '', '', '', ''), "
            "('ATL202504012', '2025', '20250401', '2', 'NYA', 'ATL', "
            "'1', '2', 'regular', 'ATL03', '30000', '175', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )
        # A conform.run() hard prerequisite -- forgetting this makes
        # _check_prerequisites reject the whole run before it ever builds
        # core.game, regardless of how correct the rest of this fixture is.
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
    db_conn.commit()
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE core.game SET game_pk = '999999' "
            "WHERE retro_game_id IN ('ATL202504011', 'ATL202504012')"
        )
    db_conn.commit()

    check = next(c for c in conform.health_check() if c.name == "core.game doubleheader identity")

    assert not check.ok
    assert "colliding identity" in check.detail

    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_health_check_play_natural_key_flags_a_partition_split_duplicate(db_conn):
    # Migration 0011 partitioned core.play by season, which forced its
    # UNIQUE (game_id, source, play_index) constraint to become UNIQUE
    # (season, game_id, source, play_index) -- required by Postgres for
    # partitioning, but it means the DB itself no longer rejects two rows
    # sharing (game_id, source, play_index) if they land in different
    # season partitions. Seeds exactly that scenario directly (bypassing
    # conform.run() -- no realistic play-level fixture needed to prove the
    # check catches a same-natural-key-different-season collision).
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game (retro_game_id, season, game_date) "
            "VALUES ('ATL202504011', 2025, '2025-04-01') RETURNING id"
        )
        game_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO core.play (game_id, season, source, play_index) "
            "VALUES (%s, 2025, 'retrosheet', 1), (%s, 2024, 'retrosheet', 1)",
            (game_id, game_id),
        )
    db_conn.commit()

    check = next(
        c for c in conform.health_check()
        if c.name == "core.play natural-key uniqueness (partition-key-independent)"
    )

    assert not check.ok
    assert "colliding identity" in check.detail

    with db_conn.cursor() as cur:
        cur.execute("TRUNCATE core.play, core.pitch, core.market, core.game")
    db_conn.commit()


def test_health_check_includes_join_integrity_safeguards():
    # Verifies the wiring, not full realistic data — every check must be
    # present and callable without crashing, even against a DB with none of
    # the optional raw tables loaded (the fresh-clone case every other
    # check here already tolerates).
    names = {check.name for check in conform.health_check()}
    assert "core.game.game_pk uniqueness" in names
    assert "core.play retrosheet coverage" in names
    assert "core.play mlb_api coverage" in names
    assert "core.pitch coverage" in names
    assert "core.player_war batting coverage" in names
    assert "core.player_war pitching coverage" in names
    assert "core.game team-season wins vs Lahman" in names
    assert "core.game doubleheader identity" in names
    assert "core.game team count vs Lahman" in names
