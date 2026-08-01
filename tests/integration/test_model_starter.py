"""Regression coverage for mlb_baseball.model.starter -- true FIP and
K%/BB%/HR% computed from raw.retrosheet_event (ADR-034).

Every value in the fixture below is hand-computed and checked in the test
itself (see the comment above each assertion) -- same discipline as
features.py/elo.py's tests, and the same discipline this module's own
docstring documents against real production data (Jacob deGrom's 2018
season, and a full-scale reconciliation against raw.bref_pitching).
"""

from decimal import Decimal

from mlb_baseball.model import features, starter


def _ensure_retrosheet_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.retrosheet_event')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.retrosheet_event ("
                "game_id text, bat_home_id text, resp_pit_id text, "
                "resp_pit_start_fl text, bat_event_fl text, event_cd text, "
                "event_outs_ct text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.retrosheet_gameinfo')")
        if not cur.fetchone()[0]:
            cur.execute("CREATE TABLE raw.retrosheet_gameinfo (gid text, gametype text)")
    db_conn.commit()


def _seed_teams_and_players(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        cur.execute(
            "INSERT INTO core.player (retro_id, first_name, last_name) "
            "VALUES ('startp1', 'Start', 'PitcherOne'), "
            "('startp2', 'Start', 'PitcherTwo') "
            "RETURNING id, retro_id"
        )
        players = {retro_id: player_id for player_id, retro_id in cur.fetchall()}
    return teams, players


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in (
            "raw.retrosheet_event",
            "raw.retrosheet_gameinfo",
            "raw.mlb_schedule",
            "raw.mlb_probable",
            "raw.mlb_playbyplay",
        ):
            cur.execute("SELECT to_regclass(%s)", (table,))
            if cur.fetchone()[0]:
                cur.execute(f"DELETE FROM {table}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_rolling_fip_and_rates_match_hand_calculation(db_conn):
    # startp1 (ATL, home) pitches game G1: 1 K, 1 BB, 1 HR, 3 generic outs
    # (all batter events, 4 outs total) plus one non-batter-event out (a
    # caught stealing -- must still count toward outs, per this module's
    # own docstring finding from deGrom's real data) -- 5 outs total, 6
    # batters faced.
    #
    # Entering G2 (7 days later), startp1's rolling line is exactly:
    # BF=6, K=1, BB=1, HR=1, outs=5 -- so:
    #   k_pct = 1/6 = 0.16667, bb_pct = 1/6, hr_pct = 1/6
    #   fip = (13*1 + 3*(1+0) - 2*1) / (5/3) + 3.10 = 8.4 + 3.10 = 11.5
    _reset(db_conn)
    _ensure_retrosheet_tables(db_conn)
    teams, players = _seed_teams_and_players(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', 2020, '2020-04-08', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, resp_pit_id, resp_pit_start_fl, "
            "bat_event_fl, event_cd, event_outs_ct, _season) VALUES "
            # startp1 (ATL's starter) pitching to the away team (bat_home_id=0)
            "('G1', '0', 'startp1', 'T', 'T', '3', '1', '2020'), "  # K
            "('G1', '0', 'startp1', 'T', 'T', '14', '0', '2020'), "  # BB
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "  # generic out
            "('G1', '0', 'startp1', 'T', 'T', '23', '0', '2020'), "  # HR
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "  # generic out
            "('G1', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "  # generic out
            "('G1', '0', 'startp1', 'T', 'F', '6', '1', '2020'), "  # caught stealing
            # startp2 (NYA's starter) pitching to the home team (bat_home_id=1)
            # -- minimal, just enough to be identifiable as the away starter.
            "('G1', '1', 'startp2', 'T', 'T', '2', '1', '2020'), "
            # G2: same two starters again, so we can check startp1's rolling
            # entering-G2 line without it needing any events of its own yet.
            "('G2', '0', 'startp1', 'T', 'T', '2', '1', '2020'), "
            "('G2', '1', 'startp2', 'T', 'T', '2', '1', '2020')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = starter.compute(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_id, f.home_starter_era, "
            "f.home_starter_k_pct, f.home_starter_bb_pct, f.home_starter_hr_pct, "
            "f.home_starter_rest "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: startp1's first appearance -- nothing prior, everything NULL
    # except the identity itself.
    g1 = rows["G1"]
    assert g1[0] == players["startp1"]
    assert g1[1:5] == (None, None, None, None)

    # G2: entering it, startp1's rolling line from G1 alone.
    g2 = rows["G2"]
    assert g2[0] == players["startp1"]
    assert g2[1] == Decimal("11.5")
    assert abs(g2[2] - Decimal("1") / Decimal("6")) < Decimal("0.0001")
    assert abs(g2[3] - Decimal("1") / Decimal("6")) < Decimal("0.0001")
    assert abs(g2[4] - Decimal("1") / Decimal("6")) < Decimal("0.0001")
    assert g2[5] == 7  # 2020-04-08 minus 2020-04-01

    _reset(db_conn)


def test_compute_returns_zero_without_retrosheet_event_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.retrosheet_event")
    db_conn.commit()

    assert starter.compute(db_conn) == 0


def test_health_check_runs_cleanly_against_an_empty_database():
    # Not asserting on the result -- just that it returns cleanly even
    # when raw.bref_pitching/raw.retrosheet_event don't exist yet (the
    # real, at-scale reconciliation only means against
    # production data, see this module's own docstring).
    checks = starter.health_check()
    assert len(checks) == 3
    assert all(c.name for c in checks)


def _ensure_playbyplay_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_playbyplay')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_playbyplay ("
                "game_pk text, at_bat_index text, inning text, half_inning text, "
                "pitcher_id text, event_type text, outs text, _season text)"
            )
    db_conn.commit()


def _ensure_mlb_schedule_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_schedule')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_schedule ("
                "game_id text, _season text, game_date text, game_type text, "
                "status text, home_id text, away_id text, game_num text, "
                "venue_id text)"
            )
    db_conn.commit()


def _ensure_probable_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.mlb_probable')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.mlb_probable "
                "(game_pk text, side text, pitcher_id text, pitcher_name text, "
                "_loaded_at timestamptz NOT NULL DEFAULT now())"
            )
    db_conn.commit()


def test_compute_live_rolling_fip_and_rates_match_hand_calculation(db_conn):
    # G1 (2026-04-01, game_pk=900001): home starter startp1 (top half)
    # faces 2 batters -- 1 K (outs 0->1), 1 field_out (outs 1->2) --
    # BF=2, K=1, BB=0, HR=0, outs=2. Away starter startp2 (bottom half)
    # gets one minimal field_out, just enough to be identifiable.
    #
    # Entering G2, startp1's rolling line is exactly G1's:
    #   k_pct = 1/2 = 0.5, bb_pct = 0, hr_pct = 0
    #   fip = (13*0 + 3*0 - 2*1) / (2/3) + 3.10 = -3.0 + 3.10 = 0.10
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    teams, _players = _seed_teams_and_players(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('livep001', '5001', 'Live', 'PitcherOne'), "
            "('livep002', '5002', 'Live', 'PitcherTwo')"
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('MLB900001', '900001', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('MLB900002', '900002', 2026, '2026-04-08', %(atl)s, %(nya)s, 2, 1, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            "('900001', '0', '1', 'top', '5001', 'strikeout', '1', '2026'), "
            "('900001', '1', '1', 'top', '5001', 'field_out', '2', '2026'), "
            "('900001', '2', '1', 'bottom', '5002', 'field_out', '1', '2026'), "
            "('900002', '0', '1', 'top', '5001', 'field_out', '1', '2026'), "
            "('900002', '1', '1', 'bottom', '5002', 'field_out', '1', '2026')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = starter.compute_live(db_conn)
    db_conn.commit()

    assert updated == 2
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_id, f.home_starter_era, "
            "f.home_starter_k_pct, f.home_starter_bb_pct, f.home_starter_hr_pct "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # G1: startp1's first appearance -- nothing prior, everything NULL
    # except the identity itself.
    g1 = rows["MLB900001"]
    assert g1[1:4] == (None, None, None)

    # G2: entering it, startp1's rolling line from G1 alone.
    g2 = rows["MLB900002"]
    assert g2[1] == Decimal("0.1")
    assert g2[2] == Decimal("0.5")
    assert g2[3] == Decimal("0")

    _reset(db_conn)


def test_compute_live_returns_zero_without_playbyplay_table(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
    db_conn.commit()

    assert starter.compute_live(db_conn) == 0


def test_compute_live_does_not_overwrite_retrosheet_derived_values(db_conn):
    # compute_live() must only fill the NULL gap compute() leaves --
    # a game already resolved via raw.retrosheet_event (any season
    # through 2025) must never be touched by the playbyplay path, even
    # if a raw.mlb_playbyplay row happens to exist for it too.
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    teams, _players = _seed_teams_and_players(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) "
            "VALUES ('MLB900003', '900003', 2026, '2026-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.game_feature SET home_starter_era = 3.33 "
            "WHERE mlb_game_pk = '900003'"
        )
    db_conn.commit()

    starter.compute_live(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute("SELECT home_starter_era FROM gold.game_feature WHERE mlb_game_pk = '900003'")
        (era,) = cur.fetchone()
    assert era == Decimal("3.33")

    _reset(db_conn)


def _extend_team_range_to_2026(db_conn, *team_ids):
    # _seed_teams_and_players's teams run through 2025 (matching the
    # Retrosheet-scoped tests that share that helper) -- features.py's
    # upcoming-games union additionally requires
    # `ms._season::integer BETWEEN home.first_year AND home.last_year`
    # (see its own docstring), so a 2026 raw.mlb_schedule row needs the
    # team's range extended, or it's silently excluded from
    # gold.game_feature entirely -- found the hard way, not assumed.
    with db_conn.cursor() as cur:
        cur.execute("UPDATE core.team SET last_year = 2026 WHERE id = ANY(%s)", (list(team_ids),))
    db_conn.commit()


def _seed_probable_pitchers(db_conn):
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('probp1', '7001', 'Probable', 'Home'), "
            "('probp2', '7002', 'Probable', 'Away') "
            "RETURNING id, mlbam_id"
        )
        return {mlbam_id: player_id for player_id, mlbam_id in cur.fetchall()}


def test_compute_probable_populates_upcoming_game_from_latest_announced_probable(db_conn):
    # ADR-047: home's probable (mlbam_id 7001) has exactly the same real
    # prior 2026 line as the compute_live test above (BF=2, K=1, outs=2 --
    # k_pct=0.5, fip=0.10) entering its next (not yet played) start on
    # 2026-04-15. away's probable (7002) has zero prior 2026 history (a
    # rookie/debut probable) -- identity must still resolve, but every rate
    # stays honestly NULL, not guessed. A stale, scratched announcement for
    # home (pitcher_id 555555, captured a day earlier) must lose to the
    # current one, not win by being inserted first.
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    _ensure_probable_table(db_conn)
    teams, _players = _seed_teams_and_players(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _extend_team_range_to_2026(db_conn, atl, nya)
    probables = _seed_probable_pitchers(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id) VALUES "
            "('900030', '2026', '2026-04-01', 'R', 'Final', '144', '147'), "
            "('900031', '2026', '2026-04-15', 'R', 'Scheduled', '144', '147')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            "('900030', '0', '1', 'top', '7001', 'strikeout', '1', '2026'), "
            "('900030', '1', '1', 'top', '7001', 'field_out', '2', '2026')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_probable (game_pk, side, pitcher_id, pitcher_name, _loaded_at) "
            "VALUES "
            "('900031', 'home', '555555', 'Scratched', now() - interval '1 day'), "
            "('900031', 'home', '7001', 'Real Starter', now()), "
            "('900031', 'away', '7002', 'Rookie Debut', now())"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    updated = starter.compute_probable(db_conn)
    db_conn.commit()

    assert updated == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_id, home_starter_era, home_starter_k_pct, "
            "home_starter_bb_pct, home_starter_hr_pct, "
            "away_starter_id, away_starter_era, away_starter_k_pct "
            "FROM gold.game_feature WHERE mlb_game_pk = '900031'"
        )
        row = cur.fetchone()

    (home_id, home_era, home_k, home_bb, home_hr, away_id, away_era, away_k) = row
    # The stale scratched announcement (555555, not in core.player at all)
    # must NOT have won -- if it had, home_id would be NULL instead.
    assert home_id == probables["7001"]
    assert home_era == Decimal("0.1")
    assert home_k == Decimal("0.5")
    assert home_bb == Decimal("0")
    assert home_hr == Decimal("0")
    # away's probable resolves identity but has no prior history to derive
    # a rate from -- NULL, not guessed.
    assert away_id == probables["7002"]
    assert away_era is None
    assert away_k is None

    # Idempotent: re-running against unchanged raw data must not change
    # anything or blow up.
    updated_again = starter.compute_probable(db_conn)
    db_conn.commit()
    assert updated_again == 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_id, home_starter_era FROM gold.game_feature "
            "WHERE mlb_game_pk = '900031'"
        )
        assert cur.fetchone() == (probables["7001"], Decimal("0.1"))

    _reset(db_conn)


def test_compute_probable_only_uses_history_strictly_before_target_game_date(db_conn):
    # Point-in-time discipline: a pitcher's OWN appearance dated on/after
    # the target game's date must never leak into that game's rolling
    # stat, even though it's technically already sitting in
    # raw.mlb_playbyplay (e.g. a same-day earlier game, or -- as tested
    # here -- a later game that for whatever reason already has data).
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    _ensure_probable_table(db_conn)
    teams, _players = _seed_teams_and_players(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _extend_team_range_to_2026(db_conn, atl, nya)
    probables = _seed_probable_pitchers(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id) VALUES "
            "('900040', '2026', '2026-04-01', 'R', 'Final', '144', '147'), "
            "('900041', '2026', '2026-04-15', 'R', 'Scheduled', '144', '147'), "
            "('900042', '2026', '2026-04-20', 'R', 'Final', '144', '147')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            # Prior (before the target's 2026-04-15 date): BF=2, K=1, outs=2.
            "('900040', '0', '1', 'top', '7001', 'strikeout', '1', '2026'), "
            "('900040', '1', '1', 'top', '7001', 'field_out', '2', '2026'), "
            # After the target's date -- must NOT count toward it. If it did,
            # the k_pct below would shift down (2 K out of 4 BF instead of
            # 1 out of 2), a real, detectable difference.
            "('900042', '0', '1', 'top', '7001', 'strikeout', '1', '2026'), "
            "('900042', '1', '1', 'top', '7001', 'field_out', '2', '2026')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_probable (game_pk, side, pitcher_id, pitcher_name) "
            "VALUES ('900041', 'home', '7001', 'Real Starter')"
        )
    db_conn.commit()

    features.build(db_conn)
    db_conn.commit()
    starter.compute_probable(db_conn)
    db_conn.commit()

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT home_starter_id, home_starter_k_pct FROM gold.game_feature "
            "WHERE mlb_game_pk = '900041'"
        )
        home_id, k_pct = cur.fetchone()
    assert home_id == probables["7001"]
    assert k_pct == Decimal("0.5")  # 1 K / 2 BF from the prior game only

    _reset(db_conn)


def test_compute_probable_returns_zero_without_probable_or_playbyplay_table(db_conn):
    _reset(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.mlb_probable")
        cur.execute("DROP TABLE IF EXISTS raw.mlb_playbyplay")
    db_conn.commit()

    assert starter.compute_probable(db_conn) == 0

    _ensure_probable_table(db_conn)
    assert starter.compute_probable(db_conn) == 0  # playbyplay still missing

    _reset(db_conn)


def test_health_check_flags_missing_probable_coverage(db_conn):
    # A probable is announced (and its pitcher has real, qualifying prior
    # 2026 history to compute a rate from), but home_starter_era never got
    # filled in -- exactly what a broken compute_probable() run, or a
    # broken core.player.mlbam_id crosswalk, would look like. Six upcoming
    # games, not one: check_join_coverage's tolerance (5, see starter.py's
    # own health_check docstring) absorbs a handful of mismatches as a
    # known, accepted edge case (a pitcher whose only prior appearance
    # recorded zero outs) -- a single missed row must not trip a doctor
    # alert on that basis alone, but six genuinely should.
    _reset(db_conn)
    _ensure_playbyplay_table(db_conn)
    _ensure_mlb_schedule_table(db_conn)
    _ensure_probable_table(db_conn)
    teams, _players = _seed_teams_and_players(db_conn)
    atl, nya = teams["ATL"], teams["NYA"]
    _extend_team_range_to_2026(db_conn, atl, nya)
    _seed_probable_pitchers(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.mlb_schedule "
            "(game_id, _season, game_date, game_type, status, home_id, away_id) VALUES "
            "('900050', '2026', '2026-04-01', 'R', 'Final', '144', '147')"
        )
        cur.execute(
            "INSERT INTO raw.mlb_playbyplay "
            "(game_pk, at_bat_index, inning, half_inning, pitcher_id, event_type, outs, _season) "
            "VALUES "
            "('900050', '0', '1', 'top', '7001', 'strikeout', '1', '2026'), "
            "('900050', '1', '1', 'top', '7001', 'field_out', '2', '2026')"
        )
        for i in range(6):
            game_id = f"90006{i}"
            cur.execute(
                "INSERT INTO raw.mlb_schedule "
                "(game_id, _season, game_date, game_type, status, home_id, away_id) "
                "VALUES (%s, '2026', '2026-04-15', 'R', 'Scheduled', '144', '147')",
                (game_id,),
            )
            cur.execute(
                "INSERT INTO raw.mlb_probable (game_pk, side, pitcher_id, pitcher_name) "
                "VALUES (%s, 'home', '7001', 'Real Starter')",
                (game_id,),
            )
    db_conn.commit()
    features.build(db_conn)
    db_conn.commit()
    # Deliberately NOT calling starter.compute_probable() -- home_starter_era
    # stays NULL for all six despite a real, resolvable probable/history
    # existing for every one of them.

    checks = starter.health_check()
    check = next(
        c
        for c in checks
        if c.name == "upcoming games with an announced probable get a resolved starter feature"
    )
    assert not check.ok

    _reset(db_conn)
