"""conform.py has no network to mock — it's a pure in-database transform
reading already-landed raw tables, so this seeds raw.* directly with small,
hand-built rows (not reused connector fixtures — those don't carry
cross-referencing IDs) and asserts the join logic and idempotency on the
real test database. raw.register_people comes from a migration (always
present); raw.retrosheet_team/raw.retrosheet_gameinfo are dynamically
created by load_dataframe in production, so this test creates them itself
and drops them afterward, matching test_retrosheet_load.py's convention.

Every test only needs to clean up tables *it* created directly (dynamic raw
tables, mostly, via DROP TABLE IF EXISTS) — core.play/pitch/market/
gold.game_feature/core.game/team/player/venue/standing/team_alias/
player_war are already reset after every test by the autouse
_clean_tables fixture below (see _reset_dynamic_tables). Do not add a
per-test TRUNCATE/DELETE for any of those; a prior version of this file did
that redundantly (a second, unnecessary pass truncating core.play/pitch's
~150+ partitions per test, see GitHub issue #2) before it was removed."""

from datetime import UTC, date, datetime
from decimal import Decimal

import psycopg
import pytest

from mlb_baseball import audit, conform

# Every raw relation read by conform that is not created by a migration.  The
# suite seeds these selectively, so cleanup must remove all of them; leaving
# even one from an interrupted or prior run makes an "optional source absent"
# assertion depend on test execution history.
DYNAMIC_RAW_TABLES = [
    "raw.bref_war_batting",
    "raw.bref_war_pitching",
    "raw.kalshi_candle",
    "raw.kalshi_market",
    "raw.kalshi_snapshot",
    "raw.lahman_teams",
    "raw.mlb_playbyplay",
    "raw.mlb_schedule",
    "raw.mlb_standing",
    "raw.mlb_team_history",
    "raw.mlb_venue",
    "raw.mlb_win_prob",
    "raw.polymarket_event",
    "raw.polymarket_market",
    "raw.polymarket_outcome",
    "raw.polymarket_price",
    "raw.polymarket_snapshot",
    "raw.retrosheet_event",
    "raw.retrosheet_gameinfo",
    "raw.retrosheet_gamelog",
    "raw.retrosheet_park",
    "raw.retrosheet_team",
    "raw.retrosheet_team0",
    "raw.statcast_pitch",
]


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
            "core.play",
            "core.pitch",
            "core.market",
            "gold.game_feature",
            "gold.prediction",
            "core.game",
            "core.team_alias",
            "core.player_war",
            "core.standing",
            "core.player",
            "core.team",
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
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_team, raw.retrosheet_gameinfo")
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

        cur.execute("DELETE FROM raw.register_people WHERE key_retro IN ('smitj001', 'jonet001')")
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


def test_conform_uses_official_supplemental_retrosheet_team_identities(db_conn):
    """TEAM{year}.TXT extends team coverage without matching display names."""
    _reset_dynamic_tables(db_conn)
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('NYA', 'AL', 'New York', 'Yankees', '1903', '2025')"
        )
        cur.execute(
            "UPDATE raw.retrosheet_gameinfo SET gid = 'ATH202504010', hometeam = 'ATH' "
            "WHERE gid = 'ATL202504010'"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_team0 "
            "(team text, city text, nickname text, first_g text, last_g text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team0 VALUES "
            "('ATH', 'Sacramento', 'Athletics', '20250327', '20250928'), "
            "('CAG', 'Chicago', 'American Giants', '19130503', '19490612')"
        )
        cur.execute("CREATE TABLE raw.mlb_team_history (team_code text, team_id text, season text)")
        cur.execute("INSERT INTO raw.mlb_team_history VALUES ('ath', '133', '2024')")
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_team_id, city, nickname, first_year, last_year, mlb_team_id "
            "FROM core.team WHERE retro_team_id IN ('ATH', 'CAG') ORDER BY retro_team_id"
        )
        assert cur.fetchall() == [
            ("ATH", "Sacramento", "Athletics", 2025, 2025, 133),
            ("CAG", "Chicago", "American Giants", 1913, 1949, None),
        ]
        cur.execute("SELECT home_team_id FROM core.game WHERE retro_game_id = 'ATH202504010'")
        assert cur.fetchone()[0] is not None


def test_conform_adds_only_completed_spring_games_and_links_statcast_pitches(db_conn):
    _reset_dynamic_tables(db_conn)
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('NYA', 'AL', 'New York', 'Yankees', '1903', '2025')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "away_id text, home_id text, _season text, status text, game_type text, "
            "game_num text, venue_name text, venue_id text, "
            "away_score text, home_score text)"
        )
        # The regular game establishes each official numeric team ID.  The
        # spring rows have no Retrosheet counterparts and must be admitted
        # only after their terminal MLB schedule state is present.
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('910000', '2025-04-01', 'New York Yankees', 'Atlanta Braves', '147', '144', "
            "'2025', 'Final', 'R', '1', 'Truist Park', '', '3', '5'), "
            "('910001', '2024-03-01', 'New York Yankees', 'Atlanta Braves', '147', '144', "
            "'2024', 'Postponed', 'S', '1', 'Park', '', '', ''), "
            "('910001', '2024-03-02', 'New York Yankees', 'Atlanta Braves', '147', '144', "
            "'2024', 'Final', 'S', '1', 'Park', '', '4', '3'), "
            "('910002', '2024-03-03', 'New York Yankees', 'Atlanta Braves', '147', '144', "
            "'2024', 'Scheduled', 'S', '1', 'Park', '', '', ''), "
            "('910003', '2024-03-04', 'New York Yankees', 'Atlanta Braves', '147', '144', "
            "'2024', 'In Progress', 'S', '1', 'Park', '', '1', '0')"
        )
        # issue #78: another test file may have left raw.statcast_pitch with a
        # different column set; drop unconditionally rather than relying on a
        # guard + collection order.
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute(
            "CREATE TABLE raw.statcast_pitch "
            "(game_pk text, game_year text, at_bat_number text, pitch_number text, inning text, "
            "batter text, pitcher text, pitch_type text, pitch_name text, release_speed text, "
            "release_spin_rate text, launch_speed text, launch_angle text, hit_distance_sc text, "
            "description text, events text)"
        )
        cur.execute(
            "INSERT INTO raw.statcast_pitch VALUES "
            "('910001', '2024', '1', '1', '1', '', '', 'FF', '4-Seam Fastball', "
            "'', '', '', '', '', 'ball', '')"
        )
    db_conn.commit()

    conform.run()
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_type, away_score, home_score, away_team_id, home_team_id "
            "FROM core.game WHERE game_pk = '910001'"
        )
        game = cur.fetchone()
        assert game[:4] == (None, "spring", 4, 3)
        assert game[4] is not None and game[5] is not None
        cur.execute("SELECT count(*) FROM core.game WHERE game_pk IN ('910002', '910003')")
        assert cur.fetchone() == (0,)
        cur.execute(
            "SELECT game_id, source_game_pk FROM core.pitch WHERE source_game_pk = '910001'"
        )
        pitch_game_id, source_key = cur.fetchone()
        assert pitch_game_id is not None
        assert source_key == "910001"


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
            "INSERT INTO gold.game_feature (game_id, game_instance_key, season, game_date) "
            "VALUES (%s, 'test:conform-fk', %s, '2025-04-01')",
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
            "venue_name text, venue_id text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('999001', '2025-04-02', 'New York Mets', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '0', 'Truist Park', '', '1', '2')"
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

        # issue #78: drop unconditionally, don't rely on collection order.
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
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
            "('NYN', 'NL', 'New York', 'Mets', '1962', '2026'), "
            "('CHN', 'NL', 'Chicago', 'Cubs', '1876', '2026'), "
            # _seed_raw_tables' ATL row only covers through 2025 (deliberately,
            # for its own tests) — a separate 2026 era row here, same city/
            # nickname, to let this test's home-team resolution succeed too.
            "('ATL', 'NL', 'Atlanta', 'Braves', '2026', '2026')"
        )
        # A real venue, resolvable via mlb_venue_id -- proves the MLB-API
        # game path resolves venue_id, not just stores the venue name as
        # text. Seeded via the actual raw tables _build_venues reads
        # (not inserted into core.venue directly -- run()'s own
        # consolidated TRUNCATE would just wipe that out before
        # _build_venues gets a chance to run). See conform.py's own
        # comment on the venue JOIN for the separate, narrower gap this
        # doesn't solve (recently-renamed venues whose name no longer
        # matches Retrosheet's own park file).
        cur.execute(
            "CREATE TABLE raw.retrosheet_park "
            "(parkid text, name text, city text, state text, league text, "
            'start text, "end" text)'
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_park VALUES "
            "('ATL03', 'Truist Park', 'Atlanta', 'GA', 'NL', '04/14/2017', ''), "
            "('CHI11', 'Wrigley Field', 'Chicago', 'IL', 'NL', '04/20/1916', ''), "
            "('LOS02', 'Wrigley Field', 'Los Angeles', 'CA', 'NL', '09/29/1925', '09/30/1965')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_venue "
            "(venue_id text, name text, active text, address1 text, city text, "
            "state text, postal_code text, latitude text, longitude text, "
            "capacity text, turf_type text, roof_type text, "
            "left_line text, center text, right_line text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_venue (venue_id, name) VALUES "
            "('4705', 'Truist Park'), ('17', 'Wrigley Field')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, venue_id text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('888001', '2026-04-05', 'New York Yankees', 'Atlanta Braves', "
            "'2026', 'Final', 'R', '0', 'Truist Park', '4705', '3', '4'), "
            "('888002', '2026-04-06', 'New York Mets', 'Chicago Cubs', "
            "'2026', 'Final', 'R', '0', 'Wrigley Field', '17', '1', '2'), "
            "('888003', '2026-04-07', 'New York Mets', 'Chicago Cubs', "
            "'2026', 'Completed Early', 'R', '0', 'Wrigley Field', '17', '1', '2'), "
            "('888004', '2026-04-08', 'New York Mets', 'Chicago Cubs', "
            "'2026', 'Scheduled', 'R', '0', 'Wrigley Field', '17', '', ''), "
            "('888005', '2026-04-09', 'New York Mets', 'Chicago Cubs', "
            "'2026', 'In Progress', 'R', '0', 'Wrigley Field', '17', '1', '0')"
        )
    db_conn.commit()

    counts = conform.run()

    assert counts["core.game"] == 5  # 2 Retrosheet-sourced + 3 completed MLB-API games
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_pk, season, away_score, home_score, "
            "away_team_id, home_team_id, winning_pitcher_id, game_type, venue_id "
            "FROM core.game WHERE game_pk = '888001'"
        )
        row = cur.fetchone()
    assert row[0] is None  # MLB supplied no Retrosheet-native ID
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
    # Real gap found and fixed this session: the MLB-API game path never
    # resolved venue_id at all (only stored the venue name as free text),
    # silently starving park_factor/wRC+'s 2026 coverage. Resolved via
    # raw.mlb_schedule's own numeric venue_id matched against
    # core.venue.mlb_venue_id (populated here by _build_venues itself,
    # from raw.retrosheet_park + the raw.mlb_venue enrichment), not
    # name-matching.
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM core.venue WHERE retro_park_id = 'ATL03'")
        (expected_venue_id,) = cur.fetchone()
    assert row[9] == expected_venue_id

    # `core.game` is a completed-facts table. A known completed exception
    # lands, while scheduled and live rows must wait for a later conform run.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT game_pk FROM core.game "
            "WHERE game_pk IN ('888003', '888004', '888005') ORDER BY 1"
        )
        assert cur.fetchall() == [("888003",)]

    # Regression: MLB venue id 17 maps to both historical Los Angeles and
    # active Chicago Wrigley Field rows. The schedule row must remain one
    # synthetic game and resolve the season-valid Chicago venue, not fan out.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), min(v.retro_park_id) "
            "FROM core.game g JOIN core.venue v ON v.id = g.venue_id "
            "WHERE g.game_pk = '888002'"
        )
        assert cur.fetchone() == (1, "CHI11")

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule, raw.retrosheet_park, raw.mlb_venue")
        # core.play/pitch/market/game_feature/game/venue are all reset by
        # the autouse _clean_tables fixture right after this test returns
        # (see _reset_dynamic_tables) — no need to also do it here.
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
            "('ATL202504010', '2025', '20250401', '0', 'NYA', 'ATL', "
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
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT away_team_id IS NOT NULL, home_team_id IS NOT NULL "
            "FROM core.game WHERE retro_game_id = 'ATL202504010'"
        )
        assert cur.fetchone() == (True, True)


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
            "venue_name text, venue_id text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('999001', '2025-04-02', 'New York Mets', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '0', 'Truist Park', '', '1', '2')"
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
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
    db_conn.commit()


def _seed_market_game(db_conn):
    """One resolvable core.game row (Yankees @ Braves, 2026-05-23, first
    pitch 23:05 UTC) plus a Polymarket event and a Kalshi market both
    referring to it — the shared fixture for every core.market test below.

    ADR-052 (issue #1): raw.polymarket_outcome.price/raw.kalshi_market's own
    bid/ask/last-price columns are deliberately seeded with an unrealistic
    "settled" value (0.99/0.98) that core.market.implied_probability must
    NOT end up with — the whole point of this fixture is to prove a real
    pre-game snapshot value is picked instead. raw.mlb_schedule supplies the
    game's real start time; raw.polymarket_snapshot/raw.kalshi_snapshot
    supply one snapshot captured well before it (the value tests assert on)
    and one captured after it (must be excluded, not just the settled
    columns)."""
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
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, venue_id text, away_score text, home_score text, "
            "game_datetime text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, game_date, away_name, home_name, _season, status, "
            "game_type, game_num, game_datetime) VALUES "
            "('900001', '2026-05-23', 'New York Yankees', 'Atlanta Braves', "
            "'2026', 'Final', 'R', '0', '2026-05-23T23:05:00Z')"
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
        # Deliberately a "settled" shape (near-certain, one-sided) -- must
        # NOT be what implied_probability ends up with.
        cur.execute(
            "INSERT INTO raw.polymarket_outcome VALUES "
            "('10', 'New York Yankees', '0.01'), "
            "('10', 'Atlanta Braves', '0.99')"
        )
        cur.execute(
            "CREATE TABLE raw.polymarket_snapshot "
            "(market_id text, outcome text, price text, captured_at text)"
        )
        cur.execute(
            "INSERT INTO raw.polymarket_snapshot VALUES "
            # Pre-game (2026-05-23 12:00Z, well before the 23:05Z first
            # pitch) -- the value tests below assert on.
            "('10', 'New York Yankees', '0.45', '2026-05-23T12:00:00+00:00'), "
            "('10', 'Atlanta Braves', '0.55', '2026-05-23T12:00:00+00:00'), "
            # Post-game (2026-05-24, after first pitch) -- must be excluded.
            "('10', 'New York Yankees', '0.02', '2026-05-24T06:00:00+00:00'), "
            "('10', 'Atlanta Braves', '0.98', '2026-05-24T06:00:00+00:00')"
        )

        cur.execute(
            "CREATE TABLE raw.kalshi_market "
            "(ticker text, event_ticker text, status text, volume_fp text, "
            "yes_bid_dollars text, yes_ask_dollars text, last_price_dollars text)"
        )
        cur.execute(
            "INSERT INTO raw.kalshi_market VALUES "
            "('KXMLBGAME-26MAY231905NYAATL-ATL', 'KXMLBGAME-26MAY231905NYAATL', "
            "'finalized', '1000', '0.97', '0.99', '0.98')"
        )
        cur.execute(
            "CREATE TABLE raw.kalshi_snapshot "
            "(ticker text, yes_bid_dollars text, yes_ask_dollars text, "
            "last_price_dollars text, captured_at text)"
        )
        cur.execute(
            "INSERT INTO raw.kalshi_snapshot VALUES "
            "('KXMLBGAME-26MAY231905NYAATL-ATL', '0.60', '0.64', '0.52', "
            "'2026-05-23T12:00:00+00:00'), "
            "('KXMLBGAME-26MAY231905NYAATL-ATL', '0.96', '0.99', '0.97', "
            "'2026-05-24T06:00:00+00:00')"
        )
    db_conn.commit()


def _drop_market_fixtures(db_conn):
    # Roll back first, exactly as _reset_dynamic_tables does: when this runs
    # as the market_game teardown after a test body failed on a SQL error,
    # db_conn is in an aborted transaction and every DROP below would itself
    # raise InFailedSqlTransaction -- leaving the raw tables behind and
    # cascading into the next market test, the very failure #114 removes.
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in [
            "raw.polymarket_event",
            "raw.polymarket_market",
            "raw.polymarket_outcome",
            "raw.polymarket_snapshot",
            "raw.kalshi_market",
            "raw.kalshi_snapshot",
            "raw.mlb_schedule",
        ]:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
    db_conn.commit()


@pytest.fixture
def market_game(db_conn):
    """Seed the shared core.market fixture (see _seed_market_game) and,
    critically, drop its raw tables again in teardown — which pytest runs
    whether the test body passed or raised.

    issue #114: every core.market test used to call _drop_market_fixtures
    only on its own last line, so a conform.run() error or a failed
    assertion partway left raw.polymarket_*/raw.kalshi_*/raw.mlb_schedule
    behind, and the next market test then failed on _seed_market_game's
    unconditional CREATE TABLE instead of on its own logic — turning one
    real failure into a cascade of unrelated ones."""
    _seed_market_game(db_conn)
    yield
    _drop_market_fixtures(db_conn)


def test_market_game_fixture_tears_down_after_a_test_body_sql_error(db_conn):
    # issue #114 regression: drive the market_game fixture's own generator
    # the way pytest's finalizer does — advance once for setup, then again
    # for teardown regardless of how the "test" ended. The realistic failure
    # is a SQL error mid-body (a bad conform.run(), a failed assertion after
    # a bad query): that leaves db_conn in an aborted transaction, and the
    # teardown must roll back before its DROPs or they all fail and the raw
    # tables leak to the next test. Reproduce that aborted state here.
    gen = market_game.__wrapped__(db_conn)
    next(gen)  # setup: _seed_market_game
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        assert cur.fetchone() != (None,)

    with db_conn.cursor() as cur, pytest.raises(psycopg.errors.UndefinedTable):
        cur.execute("SELECT * FROM raw.this_table_does_not_exist")
    # db_conn is now in InFailedSqlTransaction — every statement errors
    # until a rollback, so the teardown below only works if it rolls back.

    with pytest.raises(StopIteration):
        next(gen)  # teardown: _drop_market_fixtures

    with db_conn.cursor() as cur:
        for table in (
            "raw.mlb_schedule",
            "raw.polymarket_event",
            "raw.polymarket_market",
            "raw.polymarket_outcome",
            "raw.polymarket_snapshot",
            "raw.kalshi_market",
            "raw.kalshi_snapshot",
        ):
            cur.execute(f"SELECT to_regclass('{table}')")
            assert cur.fetchone() == (None,), table


def test_build_market_matches_polymarket_and_kalshi_to_a_core_game(db_conn, market_game):
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

    # These are the pre-game snapshot values, not raw.kalshi_market's own
    # 0.98 / raw.polymarket_outcome's own 0.99/0.01 "settled" prices --
    # see _seed_market_game's own docstring for why both are seeded.
    assert by_team[("kalshi", "ATL")] == (
        "KXMLBGAME-26MAY231905NYAATL-ATL",
        Decimal("0.52"),
        "finalized",
    )
    assert by_team[("polymarket", "ATL")][1] == Decimal("0.55")
    assert by_team[("polymarket", "NYA")][1] == Decimal("0.45")


def test_build_market_records_the_resolving_snapshot_capture_time(db_conn, market_game):
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT m.source, t.retro_team_id, m.implied_probability, m.observed_at "
            "FROM core.market m JOIN core.team t ON t.id = m.team_id "
            "WHERE m.game_id IS NOT NULL ORDER BY m.source, t.retro_team_id"
        )
        rows = cur.fetchall()

    # 2 Polymarket outcome rows + 1 Kalshi -- matches
    # test_build_market_matches_...'s counts["core.market"] == 3.
    assert len(rows) == 3
    pre_game = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)
    first_pitch = datetime(2026, 5, 23, 23, 5, tzinfo=UTC)
    for source, team, implied, observed in rows:
        assert implied is not None, (source, team)
        assert observed == pre_game, (source, team, observed)
        assert observed < first_pitch


def test_build_market_leaves_observed_at_null_when_no_pre_game_snapshot(db_conn, market_game):
    with db_conn.cursor() as cur:
        # Push every snapshot to after first pitch — nothing qualifies.
        cur.execute("UPDATE raw.polymarket_snapshot SET captured_at = '2026-05-24T06:00:00+00:00'")
        cur.execute("UPDATE raw.kalshi_snapshot SET captured_at = '2026-05-24T06:00:00+00:00'")
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT implied_probability, observed_at FROM core.market WHERE game_id IS NOT NULL"
        )
        rows = cur.fetchall()

    # 2 Polymarket outcome rows + 1 Kalshi -- matches
    # test_build_market_matches_...'s counts["core.market"] == 3.
    assert len(rows) == 3
    for implied, observed in rows:
        assert implied is None
        assert observed is None


def test_build_market_leaves_market_ref_unique_across_both_outcome_rows(db_conn, market_game):
    # Regression: Polymarket's away/home outcome rows share the same
    # underlying market id — core.market's UNIQUE(source, market_ref)
    # would reject the second row if market_ref were just that id.
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(DISTINCT market_ref) FROM core.market WHERE source = 'polymarket'"
        )
        assert cur.fetchone() == (2,)


def test_build_market_leaves_kalshi_price_as_bid_ask_midpoint_when_untraded(db_conn, market_game):
    # Real production case: a newly-listed Kalshi market has real bid/ask
    # quotes but last_price_dollars is still its zero-value placeholder
    # (never traded yet) -- the midpoint is the honest fallback, not 0.
    # ADR-052: this now applies to raw.kalshi_snapshot's own last_price
    # column (the pre-game source), not raw.kalshi_market's.
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE raw.kalshi_snapshot SET last_price_dollars = '0.0000' "
            "WHERE captured_at = '2026-05-23T12:00:00+00:00'"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT implied_probability FROM core.market WHERE source = 'kalshi'")
        assert cur.fetchone() == (Decimal("0.62"),)  # (0.60 + 0.64) / 2


def test_build_market_rerunning_replaces_instead_of_duplicating(db_conn, market_game):
    conform.run()
    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.market")
        assert cur.fetchone() == (3,)


def test_build_market_leaves_implied_probability_null_without_a_pregame_snapshot(
    db_conn, market_game
):
    # ADR-052: a market with real snapshot history, but none of it captured
    # before the game's own start time (only the post-game rows this
    # module's docstring warns about), must resolve NULL -- not silently
    # fall back to the leaky settled price, and not the post-game snapshot
    # either.
    with db_conn.cursor() as cur:
        cur.execute(
            "DELETE FROM raw.polymarket_snapshot WHERE captured_at = '2026-05-23T12:00:00+00:00'"
        )
        cur.execute(
            "DELETE FROM raw.kalshi_snapshot WHERE captured_at = '2026-05-23T12:00:00+00:00'"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT implied_probability FROM core.market ORDER BY source")
        assert cur.fetchall() == [(None,), (None,), (None,)]


def test_build_market_leaves_implied_probability_null_without_mlb_schedule(db_conn, market_game):
    # No raw.mlb_schedule at all -- no known game start time for ANY
    # market, so every implied_probability must resolve NULL, and the run
    # must not crash (same "optional dependency not ready yet" tolerance
    # every other degrade-gracefully path in this file has).
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE raw.mlb_schedule")
    db_conn.commit()

    conform.run()  # must not raise

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.market")
        assert cur.fetchone() == (3,)
        cur.execute("SELECT count(*) FROM core.market WHERE implied_probability IS NOT NULL")
        assert cur.fetchone() == (0,)


def test_build_market_degrades_gracefully_without_game_datetime_column(db_conn, market_game):
    # Real bug found running this against the full suite: raw.mlb_schedule
    # can exist (many fixtures throughout this file create one) without a
    # game_datetime column at all (an older snapshot, or a test/partial
    # deployment) -- _market_game_start_times's query must not crash the
    # whole conform() run over an UndefinedColumn, same tolerance
    # _backfill_mlb_team_id already has for that table's away_id/home_id.
    with db_conn.cursor() as cur:
        cur.execute("ALTER TABLE raw.mlb_schedule DROP COLUMN game_datetime")
    db_conn.commit()

    conform.run()  # must not raise

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.market WHERE implied_probability IS NOT NULL")
        assert cur.fetchone() == (0,)


def test_build_market_leaves_implied_probability_null_without_snapshot_tables(db_conn, market_game):
    # A fresh clone that's never run polymarket.py/kalshi.py's ADR-049
    # snapshot capture at all -- raw.polymarket_snapshot/raw.kalshi_snapshot
    # don't exist yet. Must not crash; every implied_probability resolves
    # NULL, same as the no-schedule case above.
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE raw.polymarket_snapshot")
        cur.execute("DROP TABLE raw.kalshi_snapshot")
    db_conn.commit()

    conform.run()  # must not raise

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM core.market WHERE implied_probability IS NOT NULL")
        assert cur.fetchone() == (0,)


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
            "DROP TABLE IF EXISTS raw.mlb_schedule, raw.retrosheet_team, raw.retrosheet_gameinfo"
        )
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
            "'', '', '', '', '', ''), "
            "('OAK202404040', '2024', '20240404', '0', 'TEX', 'OAK', "
            "'2', '3', 'regular', 'OAK01', '13000', '180', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )

        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, venue_id text, away_score text, home_score text, "
            "away_id text, home_id text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('500001', '2024-04-01', 'Texas Rangers', 'Oakland Athletics', "
            "'2024', 'Final', 'R', '0', 'Oakland Coliseum', '', '3', '5', '140', '133'), "
            "('500002', '2024-04-02', 'Texas Rangers', 'Oakland Athletics', "
            "'2024', 'Final', 'R', '0', 'Oakland Coliseum', '', '1', '2', '140', '133'), "
            # Deliberately wrong home_id for this one game -- the noisy
            # outlier vote the majority-vote logic must not be swayed by.
            "('500003', '2024-04-03', 'Texas Rangers', 'Oakland Athletics', "
            "'2024', 'Final', 'R', '0', 'Oakland Coliseum', '', '4', '6', '140', '999'), "
            # Production-shape regression: Retrosheet represents an
            # ordinary game as number=0, MLB represents it as game_num=1,
            # and MLB's display name no longer matches the historical
            # Retrosheet city+nickname. The second numeric-ID pass must
            # resolve this after the first three games establish the team
            # crosswalk.
            "('500005', '2024-04-04', 'Texas Rangers', 'Athletics', "
            "'2024', 'Final', 'R', '1', 'Oakland Coliseum', '', '2', '3', '140', '133'), "
            # 2025: no Retrosheet coverage for this season at all (nothing
            # inserted into raw.retrosheet_gameinfo above for it), and
            # away_name is the bare 'Athletics' MLB's schedule really uses
            # mid-relocation -- can't string-match 'Oakland Athletics'.
            "('500004', '2025-04-01', 'Athletics', 'Texas Rangers', "
            "'2025', 'Final', 'R', '0', 'Globe Life Field', '', '2', '1', '133', '140')"
        )
        cur.execute("DELETE FROM raw.register_people WHERE key_retro = 'smitj001'")
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
    db_conn.commit()


def test_seed_mlb_team_id_scenario_survives_preexisting_mlb_schedule(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        cur.execute("CREATE TABLE raw.mlb_schedule (game_id text)")
    db_conn.commit()

    _seed_mlb_team_id_scenario(db_conn)

    with db_conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw.mlb_schedule")
        assert cur.fetchone()[0] == 5

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
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
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
    db_conn.commit()


def test_game_pk_backfill_ignores_postponed_schedule_history(db_conn):
    """A postponed observation cannot attach its key to another played game."""
    _seed_mlb_team_id_scenario(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('OAK202404050', '2024', '20240405', '0', 'TEX', 'OAK', "
            "'4', '6', 'regular', 'OAK01', '12000', '180', 'N', '', '', '', "
            "'', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('500001', '2024-04-05', 'Texas Rangers', 'Oakland Athletics', "
            "'2024', 'Postponed', 'R', '1', 'Oakland Coliseum', '', '', '', '140', '133')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_pk FROM core.game "
            "WHERE retro_game_id IN ('OAK202404010', 'OAK202404050') "
            "ORDER BY retro_game_id"
        )
        assert cur.fetchall() == [("OAK202404010", "500001"), ("OAK202404050", None)]


def test_schedule_team_id_backfill_survives_incompatible_optional_history(db_conn):
    """A stale optional history landing cannot suppress valid schedule votes."""
    _seed_mlb_team_id_scenario(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("CREATE TABLE raw.mlb_team_history (unexpected_column text)")
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT retro_team_id, mlb_team_id FROM core.team ORDER BY retro_team_id")
        team_ids = dict(cur.fetchall())
    assert team_ids["OAK"] == 133
    assert team_ids["TEX"] == 140


def test_team_history_resolves_modern_retro_name_drift(db_conn):
    """MLB's numeric team history bridges current names without guessing."""
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('ANA', 'AL', 'Anaheim', 'Angels', '1997', '2021'), "
            "('OAK', 'AL', 'Oakland', 'Athletics', '1968', '2021'), "
            "('TBA', 'AL', 'Tampa Bay', 'Devil Rays', '1998', '2021')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, temp text, winddir text, "
            "windspeed text, sky text, precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ANA202504010', '2025', '20250401', '0', 'TBA', 'ANA', "
            "'3', '5', 'regular', 'ANA01', '', '', '', '', '', '', '', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, name_last, name_first) "
            "VALUES ('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, venue_id text, away_score text, home_score text, "
            "away_id text, home_id text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('510001', '2025-04-01', 'Tampa Bay Rays', 'Los Angeles Angels', "
            "'2025', 'Final', 'R', '0', '', '', '3', '5', '139', '108'), "
            "('510002', '2026-04-01', 'Athletics', 'Tampa Bay Rays', "
            "'2026', 'Final', 'R', '0', '', '', '2', '1', '133', '139')"
        )
        cur.execute("CREATE TABLE raw.mlb_team_history (team_id text, season text, team_code text)")
        cur.execute(
            "INSERT INTO raw.mlb_team_history VALUES "
            "('108', '2005', 'ana'), ('133', '2024', 'oak'), ('139', '2025', 'tba')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT retro_team_id, mlb_team_id FROM core.team ORDER BY retro_team_id")
        assert dict(cur.fetchall()) == {"ANA": 108, "OAK": 133, "TBA": 139}
        cur.execute(
            "SELECT game_pk, away_team_id IS NOT NULL, home_team_id IS NOT NULL "
            "FROM core.game ORDER BY game_pk"
        )
        assert cur.fetchall() == [("510001", True, True), ("510002", True, True)]


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
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
    db_conn.commit()


def test_backfill_game_pk_via_mlb_id_handles_name_and_single_game_number_drift(db_conn):
    _seed_mlb_team_id_scenario(db_conn)

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT game_pk FROM core.game WHERE retro_game_id = 'OAK202404040'")
        assert cur.fetchone() == ("500005",)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
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
            "venue_name text, venue_id text, away_score text, home_score text)"
        )
    db_conn.commit()

    conform.run()  # must not raise

    with db_conn.cursor() as cur:
        cur.execute("SELECT mlb_team_id FROM core.team")
        assert cur.fetchone() == (None,)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
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

    # This test is about alias resolution, not price mechanics (see
    # ADR-052/test_build_market_matches_polymarket_and_kalshi_to_a_core_game
    # for that) -- no raw.mlb_schedule/raw.polymarket_snapshot seeded here,
    # so implied_probability correctly resolves NULL; a resolved
    # core.market row under the ANA team is what actually proves the
    # rebrand alias worked.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM core.market m "
            "JOIN core.team t ON t.id = m.team_id WHERE t.retro_team_id = 'ANA'"
        )
        assert cur.fetchone() == (1,)

    # core.play/pitch/market/game_feature/game are reset by the autouse
    # _clean_tables fixture right after this test — no need here too.
    _drop_market_fixtures(db_conn)


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

    # This test is about ticker-alias resolution, not price mechanics (see
    # ADR-052/test_build_market_matches_polymarket_and_kalshi_to_a_core_game
    # for that) -- no raw.mlb_schedule/raw.kalshi_snapshot seeded here, so
    # implied_probability correctly resolves NULL; a resolved core.market
    # row under the OAK team is what actually proves the "ATH" ticker
    # resolved to the right team.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM core.market m "
            "JOIN core.team t ON t.id = m.team_id WHERE t.retro_team_id = 'OAK'"
        )
        assert cur.fetchone() == (1,)

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.kalshi_market")
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
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


def test_build_venues_uses_lowest_mlb_id_for_duplicate_exact_names(db_conn):
    _seed_raw_tables(db_conn)
    _seed_retrosheet_park(db_conn, name="Municipal Stadium")
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.mlb_venue "
            "(venue_id text, name text, latitude text, longitude text, "
            "capacity text, turf_type text, roof_type text, "
            "left_line text, center text, right_line text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_venue (venue_id, name) VALUES "
            "('900', 'Municipal Stadium'), ('100', 'Municipal Stadium')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT mlb_venue_id FROM core.venue WHERE retro_park_id = 'ATL03'")
        assert cur.fetchone() == (100,)
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
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
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
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
    db_conn.commit()


def test_build_standings_skips_an_incomplete_optional_raw_table(db_conn, capsys):
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        # An incomplete historical/raw-schema fixture must not prevent the
        # independent core-game rebuild from completing.
        cur.execute("CREATE TABLE raw.mlb_standing (team_id text)")
    db_conn.commit()

    counts = conform.run()

    assert counts["core.standing"] == 0
    assert "raw.mlb_standing not ready" in capsys.readouterr().out


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
            "venue_name text, venue_id text, away_score text, home_score text)"
        )
        # Two distinct game_ids, same date/teams/game_num — each creates
        # its own core.game row via the second INSERT, each with its own
        # correct game_pk from the start.
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('900001', '2026-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2026', 'Final', 'R', '1', 'Truist Park', '', '3', '5'), "
            "('900002', '2026-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2026', 'Final', 'R', '1', 'Truist Park', '', '3', '5')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT game_pk FROM core.game WHERE game_pk IN ('900001', '900002') ORDER BY game_pk"
        )
        rows = cur.fetchall()
    assert rows == [("900001",), ("900002",)]

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
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
            "venue_name text, venue_id text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('700001', '2025-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '1', 'Truist Park', '', '3', '5'), "
            "('700002', '2025-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '2', 'Truist Park', '', '1', '2')"
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
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
    db_conn.commit()


def test_backfill_game_pk_uses_an_exact_score_when_only_game_number_differs(db_conn):
    """An exact final score may resolve a documented 0-versus-2 number drift."""
    _reset_dynamic_tables(db_conn)
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('OAK', 'AL', 'Oakland', 'Athletics', '1968', '2025'), "
            "('BAL', 'AL', 'Baltimore', 'Orioles', '1901', '2025')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('BAL200809060', '2008', '20080906', '0', 'OAK', 'BAL', "
            "'5', '1', 'regular', 'BAL12', '', '', 'D', '', '', '', '', '', '', '', '', '')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "away_id text, home_id text, _season text, status text, game_type text, "
            "game_num text, venue_name text, venue_id text, "
            "away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('235881', '2008-09-06', 'Oakland Athletics', 'Baltimore Orioles', '133', '110', "
            "'2008', 'Final', 'R', '2', '', '', '5', '1')"
        )
        cur.execute("CREATE TABLE raw.mlb_team_history (team_code text, team_id text, season text)")
        cur.execute(
            "INSERT INTO raw.mlb_team_history VALUES ('oak', '133', '2008'), ('bal', '110', '2008')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute("SELECT game_pk FROM core.game WHERE retro_game_id = 'BAL200809060'")
        assert cur.fetchone() == ("235881",)


def test_backfill_game_pk_leaves_same_matchup_candidates_unresolved(db_conn):
    """Do not choose between two canonical rows matched by one schedule key."""
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
            "daynight text, wp text, lp text, save text, temp text, winddir text, "
            "windspeed text, sky text, precip text, fieldcond text)"
        )
        # A malformed/duplicated source history can yield two canonical
        # candidates at the same declared natural key.  A unique provider
        # game_pk must not be assigned to both just because the schedule
        # side has one plausible row.
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504010', '2025', '20250401', '1', 'NYA', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '', '', '', '', '', '', '', '', '', '', '', ''), "
            "('ATL202504011', '2025', '20250401', '1', 'NYA', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '', '', '', '', '', '', '', '', '', '', '', '')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, name_last, name_first) "
            "VALUES ('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "_season text, status text, game_type text, game_num text, "
            "venue_name text, venue_id text, away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('900003', '2025-04-01', 'New York Yankees', 'Atlanta Braves', "
            "'2025', 'Final', 'R', '1', 'Truist Park', '', '3', '5')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT game_pk FROM core.game WHERE retro_game_id IN "
            "('ATL202504010', 'ATL202504011') ORDER BY retro_game_id"
        )
        assert cur.fetchall() == [(None,), (None,)]


def test_exact_score_fallback_does_not_steal_an_already_claimed_game_pk(db_conn):
    """A doubleheader partner with an identical score must not get the same key.

    Real production bug (1941-09-14, Homestead Grays @ Newark Eagles): MLB's
    schedule only published a gamePk for game 2 of this doubleheader,
    correctly matched by the game-number-aware pass. Both games ended 6-4,
    so the score-only fallback -- which only checked that *its own*
    candidate set was unambiguous, not whether the schedule key was already
    claimed by game 2's row -- then handed game 1 that same already-used
    gamePk, producing a duplicate populated core.game.game_pk.
    """
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('HOM', 'NN', 'Homestead', 'Grays', '1935', '1948'), "
            "('NWK', 'NN', 'Newark', 'Eagles', '1936', '1948')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, "
            "visteam text, hometeam text, vruns text, hruns text, "
            "gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, temp text, winddir text, "
            "windspeed text, sky text, precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('NWK194109141', '1941', '19410914', '1', 'HOM', 'NWK', "
            "'6', '4', 'regular', 'NWK01', '', '', '', '', '', '', '', '', '', '', '', ''), "
            "('NWK194109142', '1941', '19410914', '2', 'HOM', 'NWK', "
            "'6', '4', 'regular', 'NWK01', '', '', '', '', '', '', '', '', '', '', '', '')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, "
            "away_id text, home_id text, _season text, status text, game_type text, "
            "game_num text, venue_name text, venue_id text, "
            "away_score text, home_score text)"
        )
        # Only game 2 has a published gamePk -- game 1's is genuinely
        # missing from MLB's schedule, not just unresolved by this pipeline.
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('802526', '1941-09-14', 'Homestead Grays', 'Newark Eagles', '9001', '9002', "
            "'1941', 'Final', 'R', '2', '', '', '6', '4')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, name_last, name_first) "
            "VALUES ('smitj001', '123456', 'smitj01', '1001', 'uuid-1', 'Smith', 'John')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_pk FROM core.game "
            "WHERE retro_game_id IN ('NWK194109141', 'NWK194109142') "
            "ORDER BY retro_game_id"
        )
        assert cur.fetchall() == [("NWK194109141", None), ("NWK194109142", "802526")]


def test_backfill_game_pk_leaves_ambiguous_final_id_null(db_conn):
    # Real bug found via mlb doctor's check_no_duplicate_key in production:
    # game_pk 123347 was shared by two genuinely distinct, real 1944 PIT
    # games a month apart (1944-07-02 and 1944-08-13) -- not a doubleheader
    # (test_backfill_game_pk_distinguishes_doubleheader_games above) and not
    # the suspended-and-resumed-game case
    # (test_backfill_game_pk_does_not_overwrite_an_already_correct_value
    # above). raw.mlb_schedule itself lists the same game_id under both
    # dates with both rows marked status='Final' -- confirmed against real
    # production data as a genuine, if rare, MLB Stats API quirk (216
    # distinct game_id values found with 2+ 'Final' rows). Each date
    # correctly matches its own real core.game row (date is part of the
    # join), but both would get set to the same now-ambiguous game_pk.
    # Expected fix: leave game_pk NULL for both rather than guess.
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, "
            "first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('PIT', 'NL', 'Pittsburgh', 'Pirates', '1887', '2025'), "
            "('BSN', 'NL', 'Boston', 'Braves', '1876', '1952')"
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
            "('PIT194407022', '1944', '19440702', '2', 'BSN', 'PIT', "
            "'3', '5', 'regular', 'PIT07', '5000', '150', 'D', '', '', '', "
            "'', '', '', '', '', ''), "
            "('PIT194408132', '1944', '19440813', '2', 'BSN', 'PIT', "
            "'1', '2', 'regular', 'PIT07', '4000', '145', 'D', '', '', '', "
            "'', '', '', '', '', '')"
        )
        # conform.run()'s own prerequisite check requires this non-empty --
        # content irrelevant here, just needs a row to exist.
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
            "venue_name text, venue_id text, away_score text, home_score text)"
        )
        # Same game_id (123347) under both real dates, both 'Final' -- the
        # actual production shape, not a fabricated edge case.
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('123347', '1944-07-02', 'Boston Braves', 'Pittsburgh Pirates', "
            "'1944', 'Final', 'R', '2', 'Forbes Field', '', '3', '5'), "
            "('123347', '1944-08-13', 'Boston Braves', 'Pittsburgh Pirates', "
            "'1944', 'Final', 'R', '2', 'Forbes Field', '', '1', '2')"
        )
    db_conn.commit()

    conform.run()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_pk FROM core.game "
            "WHERE retro_game_id IN ('PIT194407022', 'PIT194408132') "
            "ORDER BY retro_game_id"
        )
        rows = dict(cur.fetchall())
    assert rows["PIT194407022"] is None
    assert rows["PIT194408132"] is None

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM core.game GROUP BY game_pk "
            "HAVING game_pk IS NOT NULL AND count(*) > 1"
        )
        assert cur.fetchone() is None

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_schedule")
        # core.play/pitch/market/game_feature/game are reset by the autouse
        # _clean_tables fixture right after this test — no need here too.
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
        # issue #78: drop unconditionally, don't rely on collection order.
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
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
        cur.execute("SELECT game_id, source_game_pk, pitch_type FROM core.pitch")
        assert cur.fetchone() == (None, "999999999", "FF")

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        # core.pitch is reset by the autouse _clean_tables fixture right
        # after this test — no need here too.
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


def test_health_check_lahman_reconciliation_ignores_negro_league_rows(db_conn):
    # Real production case, 2026-08-14: raw.lahman_teams carries its own,
    # separately (and incompletely) compiled Negro League team-seasons
    # (lgid='NNL'/'NAL'/etc, not just 'AL'/'NL') -- e.g. CAG-1920: w=45 in
    # Lahman's own data. core.game's Retrosheet-sourced win count for the
    # same team-season is unrelated (both sources' Negro League coverage
    # is real but independently incomplete), so comparing them isn't a
    # meaningful reconciliation -- this check must exclude non-AL/NL
    # Lahman rows entirely, not just tolerate the gap. ATL(NL)'s own real
    # 2-win match still reconciles clean alongside it.
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.lahman_teams "
            "(teamidretro text, yearid text, w text, l text, g text, lgid text)"
        )
        cur.execute("INSERT INTO raw.lahman_teams VALUES ('ATL', '2025', '2', '0', '2', 'NL')")
        # core.game has zero games for CAG at all -- a Negro League row
        # this far off would fail loudly (tolerance=3) if not excluded.
        cur.execute("INSERT INTO raw.lahman_teams VALUES ('CAG', '1920', '45', '10', '55', 'NNL')")
    db_conn.commit()

    conform.run()

    check = next(
        c for c in conform.health_check() if c.name == "core.game team-season wins vs Lahman"
    )
    assert check.ok, check.detail

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

    check = next(c for c in conform.health_check() if c.name == "core.game team count vs Lahman")
    assert check.ok, check.detail

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.lahman_teams VALUES "
            "('NYA', '2025', '90', '72', '162', 'AL'), "
            "('BOS', '2025', '85', '77', '162', 'AL')"
        )
    db_conn.commit()

    check = next(c for c in conform.health_check() if c.name == "core.game team count vs Lahman")
    assert not check.ok
    assert "2025" in check.detail

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.lahman_teams")
    db_conn.commit()


def test_health_check_lahman_team_count_excludes_negro_league_teams(db_conn):
    # Proves Negro League teams with game_type='regular' games in core.game
    # are excluded from core_teams count by matching against Lahman's AL/NL scope.
    # Without this filter, core_teams would count both AL/NL and Negro League teams,
    # causing a false-positive mismatch against lahman_teams.
    _seed_raw_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('NYA', 'AL', 'New York', 'Yankees', '1903', '2025'), "
            "('CAG', 'NNL', 'Chicago', 'American Giants', '1920', '1950'), "
            "('HOM', 'NNL', 'Homestead', 'Grays', '1920', '1950')"
        )

        # 1 AL/NL game (NYA at ATL) and 1 Negro League game (CAG at HOM) for 1921
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL192104010', '1921', '19210401', '0', 'NYA', 'ATL', '3', '5', 'regular', "
            "'ATL01', '10000', '120', 'D', '', '', '', '', '', '', '', '', ''), "
            "('HOM192104020', '1921', '19210402', '0', 'CAG', 'HOM', '4', '2', 'regular', "
            "'HOM01', '5000', '110', 'D', '', '', '', '', '', '', '', '', '')"
        )

        cur.execute(
            "CREATE TABLE raw.lahman_teams "
            "(teamidretro text, yearid text, w text, l text, g text, lgid text)"
        )
        # Lahman has ATL (NL) and NYA (AL) for 1921, plus Negro League teams (NNL)
        cur.execute(
            "INSERT INTO raw.lahman_teams VALUES "
            "('ATL', '1921', '80', '70', '150', 'NL'), "
            "('NYA', '1921', '90', '60', '150', 'AL'), "
            "('CAG', '1921', '50', '30', '80', 'NNL'), "
            "('HOM', '1921', '40', '40', '80', 'NNL')"
        )
    db_conn.commit()

    conform.run()

    check = next(c for c in conform.health_check() if c.name == "core.game team count vs Lahman")
    assert check.ok, check.detail

    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.lahman_teams")
    db_conn.commit()


def test_database_rejects_a_doubleheader_game_pk_collision(db_conn):
    # Regression, end to end: before migration 0011's game_pk-overwrite
    # guard, this exact scenario (two games, same date/teams, distinct
    # game_number, both landing on the same game_pk) produced a real
    # duplicate in production. conform.run() itself should no longer
    # produce one (see test_backfill_game_pk_distinguishes_doubleheader_games
    # above) -- this seeds the collision directly into core.game (same
    # date, same teams, distinct game_number -- a real doubleheader shape)
    # to prove the database itself rejects it if the writer ever regresses.
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

    with pytest.raises(psycopg.errors.UniqueViolation):
        with db_conn.cursor() as cur:
            cur.execute(
                "UPDATE core.game SET game_pk = '999999' "
                "WHERE retro_game_id IN ('ATL202504011', 'ATL202504012')"
            )
    db_conn.rollback()

    # core.play/pitch/market/game_feature/game are reset by the autouse
    # _clean_tables fixture right after this test — no need here too.


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
        c
        for c in conform.health_check()
        if c.name == "core.play natural-key uniqueness (partition-key-independent)"
    )

    assert not check.ok
    assert "colliding identity" in check.detail

    # core.play/pitch/market/game_feature/game are reset by the autouse
    # _clean_tables fixture right after this test — no need here too.


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


def _seed_conformance_rehearsal(db_conn):
    """Land a small, multi-era raw population for the Plan 01 tie-out gate.

    This fixture is intentionally source-shaped rather than inserting core
    rows. It covers the minimum set of identity decisions a production
    conformance request must preserve: Retrosheet-only history, an MLB-keyed
    doubleheader, schedule history, a current completed game, excluded live
    data, and both resolved and unresolved pitch links.
    """
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE raw.retrosheet_team "
            "(team_id text, league text, city text, nickname text, first_year text, last_year text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_team VALUES "
            "('PIT', 'NL', 'Pittsburgh', 'Pirates', '1887', '2025'), "
            "('BSN', 'NL', 'Boston', 'Braves', '1876', '1952'), "
            "('ATL', 'NL', 'Atlanta', 'Braves', '1966', '2026'), "
            "('NYA', 'AL', 'New York', 'Yankees', '1913', '2026')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, _season text, date text, number text, visteam text, hometeam text, "
            "vruns text, hruns text, gametype text, site text, attendance text, timeofgame text, "
            "daynight text, wp text, lp text, save text, temp text, winddir text, windspeed text, "
            "sky text, precip text, fieldcond text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('PIT194407020', '1944', '19440702', '0', 'BSN', 'PIT', '3', '5', "
            "'regular', 'PIT07', '5000', '150', 'D', '', '', '', "
            "'unknown', 'unknown', 'unknown', 'unknown', 'unknown', 'unknown'), "
            "('ATL202504011', '2025', '20250401', '1', 'NYA', 'ATL', '3', '5', "
            "'regular', 'ATL03', '35000', '185', 'N', 'smitj001', 'jonet001', '', "
            "'72', 'fromlf', '10', 'sunny', 'none', 'dry'), "
            "('ATL202504012', '2025', '20250401', '2', 'NYA', 'ATL', '1', '2', "
            "'regular', 'ATL03', '30000', '175', 'N', 'smitj001', 'jonet001', '', "
            "'70', 'fromcf', '8', 'cloudy', 'none', 'dry')"
        )
        cur.execute(
            "INSERT INTO raw.register_people "
            "(key_retro, key_mlbam, key_bbref, key_fangraphs, key_uuid, "
            "name_last, name_first) VALUES "
            "('smitj001', '123456', 'smitj01', '1001', 'rehearsal-1', 'Smith', 'John'), "
            "('jonet001', '234567', 'jonet01', '1002', 'rehearsal-2', 'Jones', 'Tim')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_schedule "
            "(game_id text, game_date text, away_name text, home_name text, _season text, "
            "status text, game_type text, game_num text, venue_name text, venue_id text, "
            "away_score text, home_score text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_schedule VALUES "
            "('700001', '2025-04-01', 'New York Yankees', 'Atlanta Braves', '2025', "
            "'Final', 'R', '1', 'Truist Park', '', '3', '5'), "
            "('700002', '2025-04-01', 'New York Yankees', 'Atlanta Braves', '2025', "
            "'Final', 'R', '2', 'Truist Park', '', '1', '2'), "
            "('800001', '2026-04-10', 'New York Yankees', 'Atlanta Braves', '2026', "
            "'Postponed', 'R', '1', 'Truist Park', '', '', ''), "
            "('800001', '2026-04-12', 'New York Yankees', 'Atlanta Braves', '2026', "
            "'Final', 'R', '1', 'Truist Park', '', '2', '4'), "
            "('800002', '2026-04-13', 'New York Yankees', 'Atlanta Braves', '2026', "
            "'Scheduled', 'R', '1', 'Truist Park', '', '', ''), "
            "('800003', '2026-04-14', 'New York Yankees', 'Atlanta Braves', '2026', "
            "'In Progress', 'R', '1', 'Truist Park', '', '1', '0')"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_event "
            "(game_id text, _season text, event_id text, inn_ct text, bat_home_id text, "
            "bat_id text, pit_id text, event_cd text, event_tx text, away_score_ct text, "
            "home_score_ct text, _scope text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event VALUES "
            "('ATL202504011', '2025', '1', '1', '0', 'smitj001', 'jonet001', "
            "'2', '43/G34', '0', '0', '2025_pbp'), "
            "('ATL202504012', '2025', '1', '1', '0', 'smitj001', 'jonet001', "
            "'2', '43/G34', '0', '0', '2025_pbp')"
        )
        cur.execute(
            "CREATE TABLE raw.mlb_playbyplay "
            "(game_pk text, _season text, at_bat_index text, inning text, half_inning text, "
            "batter_id text, pitcher_id text, event_type text, event text, away_score text, "
            "home_score text, balls text, strikes text, outs text)"
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay VALUES "
            "('800001', '2026', '0', '1', 'top', '234567', '123456', "
            "'field_out', 'Groundout', '0', '0', '0', '0', '1')"
        )
        # issue #78: drop unconditionally, don't rely on collection order.
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute(
            "CREATE TABLE raw.statcast_pitch "
            "(game_pk text, game_year text, at_bat_number text, pitch_number text, inning text, "
            "batter text, pitcher text, pitch_type text, pitch_name text, release_speed text, "
            "release_spin_rate text, launch_speed text, launch_angle text, hit_distance_sc text, "
            "description text, events text)"
        )
        cur.execute(
            "INSERT INTO raw.statcast_pitch VALUES "
            "('700001', '2025', '1', '1', '1', '234567', '123456', 'FF', "
            "'Four-Seam Fastball', '95.2', '2200', '', '', '', 'called_strike', ''), "
            "('999999999', '2025', '1', '1', '1', '234567', '123456', 'FF', "
            "'Four-Seam Fastball', '95.2', '2200', '', '', '', 'called_strike', '')"
        )
    db_conn.commit()


def _rehearsal_snapshot(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT retro_game_id, game_pk, season, game_date, game_number, "
            "away_score, home_score, "
            "away_team_id IS NOT NULL, home_team_id IS NOT NULL, temp_f "
            "FROM core.game ORDER BY retro_game_id"
        )
        games = cur.fetchall()
        cur.execute(
            "SELECT g.game_pk, p.source, p.play_index, p.inning, p.half_inning, "
            "p.away_score, p.home_score "
            "FROM core.play p JOIN core.game g ON g.id = p.game_id "
            "ORDER BY g.game_pk NULLS FIRST, p.source, p.play_index"
        )
        plays = cur.fetchall()
        cur.execute(
            "SELECT source_game_pk, game_id IS NOT NULL, season, at_bat_number, pitch_number, "
            "batter_id IS NOT NULL, pitcher_id IS NOT NULL "
            "FROM core.pitch ORDER BY source_game_pk"
        )
        pitches = cur.fetchall()
        cur.execute(
            "SELECT (SELECT count(*) FROM raw.mlb_schedule), "
            "(SELECT count(*) FROM raw.retrosheet_gameinfo), "
            "(SELECT count(*) FROM raw.retrosheet_event), "
            "(SELECT count(*) FROM raw.mlb_playbyplay), "
            "(SELECT count(*) FROM raw.statcast_pitch)"
        )
        raw_counts = cur.fetchone()
    # The next conformance pass uses another connection and begins with a
    # TRUNCATE. Release this read transaction so the rehearsal proves writer
    # behavior rather than deadlocking itself on its own evidence query.
    db_conn.commit()
    return games, plays, pitches, raw_counts


def test_multi_source_conformance_rehearsal_ties_out_across_grains(db_conn):
    """Plan 01 R2/R3 gate: one repeatable fixture proves the whole core path."""
    _reset_dynamic_tables(db_conn)
    _seed_conformance_rehearsal(db_conn)

    first_counts = conform.run()
    first = _rehearsal_snapshot(db_conn)
    second_counts = conform.run()
    second = _rehearsal_snapshot(db_conn)

    assert first_counts == second_counts
    assert first == second  # rerun is idempotent and never mutates raw data
    games, plays, pitches, raw_counts = first
    assert raw_counts == (6, 3, 2, 1, 2)  # schedule history stays source-faithful
    assert games == [
        ("ATL202504011", "700001", 2025, date(2025, 4, 1), 1, 3, 5, True, True, 72),
        ("ATL202504012", "700002", 2025, date(2025, 4, 1), 2, 1, 2, True, True, 70),
        ("PIT194407020", None, 1944, date(1944, 7, 2), 0, 3, 5, True, True, None),
        (None, "800001", 2026, date(2026, 4, 12), 1, 2, 4, True, True, None),
    ]
    assert plays == [
        ("700001", "retrosheet", 1, 1, "top", 0, 0),
        ("700002", "retrosheet", 1, 1, "top", 0, 0),
        ("800001", "mlb_api", 0, 1, "top", 0, 0),
    ]
    assert pitches == [
        ("700001", True, 2025, 1, 1, True, True),
        ("999999999", False, 2025, 1, 1, True, True),
    ]

    findings = audit.run("game")
    failures = [finding for finding in findings if finding.status == "FAIL"]
    assert failures == []
    assert (
        next(
            finding for finding in findings if finding.name == "core.game doubleheader identity"
        ).status
        == "PASS"
    )
    assert (
        next(
            finding for finding in findings if finding.name == "core.pitch unresolved-key coverage"
        ).status
        == "WARN"
    )
    assert (
        next(
            finding for finding in findings if finding.name == "core.play controlled values"
        ).status
        == "PASS"
    )


def _core_play_pitch_index_names(cur) -> tuple[set[str], set[str]]:
    cur.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'core' AND tablename = 'play'")
    play_indexes = {row[0] for row in cur.fetchall()}
    cur.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'core' AND tablename = 'pitch'"
    )
    pitch_indexes = {row[0] for row in cur.fetchall()}
    return play_indexes, pitch_indexes


def test_conform_rebuilds_play_and_pitch_indexes(db_conn):
    """core.play/core.pitch's index set after a conform run must be identical to
    before it -- proves _drop_bulk_indexes/_rebuild_bulk_indexes is a true no-op
    from \\d core.play's perspective, not just that some hardcoded list exists.
    Comparing to the *live* pre-run set (not a hardcoded expected list) means
    this stays correct if a future migration adds or removes a real index,
    matching CodeRabbit's "verify nothing is silently lost" concern without
    Kilo's "brittle to legitimate future indexes" downside."""
    _reset_dynamic_tables(db_conn)
    _seed_raw_tables(db_conn)

    with db_conn.cursor() as cur:
        indexes_before = _core_play_pitch_index_names(cur)

    conform.run()

    with db_conn.cursor() as cur:
        indexes_after = _core_play_pitch_index_names(cur)

    assert indexes_after == indexes_before
    # Also assert the known unique/pkey indexes specifically survived --
    # a set-equality pass alone wouldn't distinguish "nothing changed" from
    # "everything changed to a different, still-equal-sized set."
    play_indexes_after, pitch_indexes_after = indexes_after
    assert {"play_pkey", "play_game_id_source_play_index_key"}.issubset(play_indexes_after)
    assert "pitch_pkey" in pitch_indexes_after
