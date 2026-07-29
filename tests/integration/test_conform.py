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


@pytest.fixture(autouse=True)
def _clean_tables(db_conn):
    yield
    with db_conn.cursor() as cur:
        for table in DYNAMIC_RAW_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("TRUNCATE raw.register_people")
        # play/pitch/market reference game — must be truncated together
        # with it, not in a separate statement (Postgres requires this,
        # same as conform.py's run() — see its comment there).
        cur.execute(
            "TRUNCATE core.play, core.pitch, core.market, core.game, "
            "core.team, core.player, core.player_war"
        )
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
    # raw.polymarket_*/raw.kalshi_*/raw.bref_war_* seeded in this test —
    # every optional build step must degrade to 0, not fail.
    assert counts == {
        "core.team": 1,
        "core.player": 2,
        "core.game": 2,
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
            "daynight text, wp text, lp text, save text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202104010', '2021', '20210401', '0', 'NYA', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', '', '', '')"
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
            "daynight text, wp text, lp text, save text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202605230', '2026', '20260523', '0', 'NYA', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', '', '', '')"
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
