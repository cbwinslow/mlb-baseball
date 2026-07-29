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
        # play/pitch/market reference game, team_alias/player_war reference
        # team/player — all must be truncated together with what they
        # reference, not in a separate statement (Postgres requires this,
        # same as conform.py's run() — see its comment there).
        cur.execute(
            "TRUNCATE core.play, core.pitch, core.market, core.game, "
            "core.team, core.team_alias, core.player, core.player_war"
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
        "core.team_alias": 1,  # ATL's own Kalshi ticker alias ("ATL" -> "ATL")
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
            "daynight text, wp text, lp text, save text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ATL202504010', '2025', '20250401', '0', 'ATL', 'ATL', "
            "'3', '5', 'regular', 'ATL03', '35000', '185', 'N', '', '', '')"
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
            "daynight text, wp text, lp text, save text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('OAK202404010', '2024', '20240401', '0', 'TEX', 'OAK', "
            "'3', '5', 'regular', 'OAK01', '10000', '180', 'N', '', '', ''), "
            "('OAK202404020', '2024', '20240402', '0', 'TEX', 'OAK', "
            "'1', '2', 'regular', 'OAK01', '11000', '175', 'N', '', '', ''), "
            "('OAK202404030', '2024', '20240403', '0', 'TEX', 'OAK', "
            "'4', '6', 'regular', 'OAK01', '12000', '190', 'N', '', '', '')"
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
            "daynight text, wp text, lp text, save text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('ANA202605230', '2026', '20260523', '0', 'NYA', 'ANA', "
            "'3', '5', 'regular', 'ANA01', '35000', '185', 'N', '', '', '')"
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
            "daynight text, wp text, lp text, save text)"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo VALUES "
            "('OAK202605230', '2026', '20260523', '0', 'NYA', 'OAK', "
            "'3', '5', 'regular', 'OAK01', '10000', '180', 'N', '', '', '')"
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
