"""Regression coverage for mlb_baseball.model.enrich_feature_stage --
proves the enrichment modules (team_rate, offense, starter, bullpen,
starter_workload, park, oaa, speed, framing, war) are actually wired into
the same rebuild path `mlb predict` runs daily, not just runnable by hand.

Issue: a real production incident (2026-08-19, see plans/PROGRESS.md
"Production incident found and fixed") found every enrichment column in
gold.game_feature NULL for all 217,196 rows after a routine gold.game_feature
rebuild, because the modules were only ever run as a manual, one-off
script -- never called from mlb_baseball.model.run() (`mlb predict`), which
IS what the daily cron (scripts/mlb_daily_update.sh, 06:00 UTC) actually
calls. Without this fix, the next daily rebuild wipes every enrichment
column right back to NULL, on a recurring basis -- caught during PR review
of the 2026-08-19 backfill (issue #48), not caught by any prior test.

Doesn't re-prove any individual module's math (each already has its own
exhaustive tests) -- only that enrich_feature_stage() actually calls real
compute() functions that write real, non-NULL data, end to end.
"""

from mlb_baseball.model import enrich_feature_stage, features


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        for table in ("raw.retrosheet_event", "raw.retrosheet_gameinfo"):
            cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.team")
        cur.execute("DELETE FROM core.venue WHERE retro_park_id = 'ATL01'")
    db_conn.commit()


def test_enrich_feature_stage_populates_columns_from_multiple_real_modules(db_conn):
    # park.compute() needs only core.game's own scores (zero-leakage,
    # zero external dependency by design, ADR-035) -- the simplest module
    # to prove end to end. team_rate.compute() needs real retrosheet event
    # data too, proving a second, independently-gated module is also
    # actually invoked, not just the first one in the dispatch order.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        # Wide enough for every Retrosheet-derived module enrich_feature_stage
        # calls (team_rate, offense, starter, starter_workload, bullpen), not
        # just the two this test asserts on -- the table EXISTS, so each
        # module's own to_regclass gate won't save it from a real
        # UndefinedColumn crash if a column it queries is missing (issue #37's
        # exact failure shape).
        cur.execute(
            "CREATE TABLE raw.retrosheet_event ("
            "game_id text, bat_home_id text, resp_pit_id text, "
            "resp_pit_start_fl text, event_cd text, ab_fl text, "
            "sf_fl text, bat_event_fl text, event_outs_ct text, _season text)"
        )
        cur.execute(
            "CREATE TABLE raw.retrosheet_gameinfo "
            "(gid text, gametype text, visteam text, hometeam text, _season text)"
        )
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.venue (retro_park_id, name, city, first_year, last_year) "
            "VALUES ('ATL01', 'Test Park', 'Atlanta', 1966, 2025) RETURNING id"
        )
        (venue,) = cur.fetchone()
        # park.compute()'s formula (park_factor_update.sql) needs, for the
        # SAME team, both a home split (games at this venue) and a road
        # split (games anywhere) in the same season to compute a rate --
        # G4 gives ATL a road game so its 2019 road_splits row exists;
        # without it, park.compute() silently finds nothing to update
        # (0 rows), not a crash -- confirmed by running this fixture
        # without G4 first and watching this exact assertion fail with
        # `assert 0 > 0` before adding it.
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type, venue_id) VALUES "
            "('G1', 2019, '2019-04-01', %(atl)s, %(nya)s, 5, 3, 'regular', %(venue)s), "
            "('G2', 2019, '2019-04-08', %(atl)s, %(nya)s, 4, 2, 'regular', %(venue)s), "
            "('G4', 2019, '2019-04-15', %(nya)s, %(atl)s, 2, 4, 'regular', %(venue)s), "
            "('G3', 2020, '2020-04-01', %(atl)s, %(nya)s, 6, 1, 'regular', %(venue)s)",
            {"atl": atl, "nya": nya, "venue": venue},
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_gameinfo (gid, gametype) "
            "VALUES ('G1', 'regular'), ('G2', 'regular'), ('G3', 'regular'), ('G4', 'regular')"
        )
        cur.execute(
            "INSERT INTO raw.retrosheet_event "
            "(game_id, bat_home_id, event_cd, ab_fl, sf_fl, bat_event_fl, _season) VALUES "
            "('G1', '1', '20', 'T', 'F', 'T', '2019'), "
            "('G1', '0', '2', 'T', 'F', 'T', '2019'), "
            "('G2', '1', '20', 'T', 'F', 'T', '2019'), "
            "('G2', '0', '2', 'T', 'F', 'T', '2019'), "
            "('G4', '1', '20', 'T', 'F', 'T', '2019'), "
            "('G4', '0', '2', 'T', 'F', 'T', '2019'), "
            "('G3', '1', '20', 'T', 'F', 'T', '2020'), "
            "('G3', '0', '2', 'T', 'F', 'T', '2020')"
        )
    db_conn.commit()

    # No commit between these two calls -- matches production's real
    # transaction boundary exactly (run() commits once, after both stages;
    # see mlb_baseball/model/__init__.py). Same-session reads already see
    # a connection's own uncommitted writes, so this isn't required for
    # enrich_feature_stage() to see features.build()'s rows -- it's here
    # so this test's own structure actually proves what run() does, not
    # a looser approximation of it.
    features.build(db_conn)
    counts = enrich_feature_stage(db_conn)
    db_conn.commit()

    assert counts["gold.game_feature (park_factor)"] > 0
    assert counts["gold.game_feature (team_rate)"] > 0

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.park_factor, f.home_pa "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "WHERE g.retro_game_id IN ('G2', 'G3') ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # Two different games on purpose, not one: team_rate.compute()'s
    # rolling window partitions by (team_id, season), so G3 (season 2020)
    # starts a fresh partition with no prior 2020 games -- its own home_pa
    # is legitimately NULL regardless of team_rate having run correctly.
    # G2 (ATL's second game within season 2019) is team_rate's real
    # entering-value proof instead. park_factor's own trailing window
    # spans seasons by design (ADR-035), so G3 -- the only game with a
    # real prior season (2019) behind it -- is the right one to check
    # there. Both non-NULL values prove their respective modules actually
    # ran and actually wrote real data, not just that the dispatch
    # function returned without error. home_pa (not home_obp)
    # specifically because it's ungated -- always populated once
    # team_rate.compute() runs, unlike home_obp, which needs MIN_PA=10
    # prior plate appearances this small fixture doesn't clear.
    assert rows["G3"][0] is not None  # park_factor
    assert rows["G2"][1] is not None  # home_pa

    _reset(db_conn)


def test_enrich_feature_stage_returns_zero_without_retrosheet_tables(db_conn):
    # Matches every individual enrichment module's own "not ready yet"
    # contract (to_regclass gate returning 0, not raising) -- the
    # aggregator must not crash just because one dependency isn't
    # bootstrapped yet on a fresh clone.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 2025, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', 2020, '2020-04-01', %(atl)s, %(nya)s, 5, 3, 'regular')",
            {"atl": atl, "nya": nya},
        )
    db_conn.commit()

    features.build(db_conn)
    counts = enrich_feature_stage(db_conn)
    db_conn.commit()

    assert counts["gold.game_feature (team_rate)"] == 0

    _reset(db_conn)
