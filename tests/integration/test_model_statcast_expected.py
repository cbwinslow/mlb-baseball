"""Regression coverage for mlb_baseball.model.statcast_expected -- Statcast
quality of contact & expected metrics (HardHit%, Barrel%, xBA, xSLG, xwOBA)
for starters, bullpens, and offenses (STA-03).

statcast_expected_update.sql reads Baseball Savant's own pre-computed
per-batted-ball expected-stat columns straight from raw.statcast_pitch
(estimated_ba_using_speedangle, estimated_slg_using_speedangle,
estimated_woba_using_speedangle, launch_speed, launch_speed_angle) -- it used
to derive a synthetic proxy from raw.retrosheet_event's coarse batted-ball-type
codes via an uncited constant table instead (see
mlb_baseball/metrics/statcast_expected_quality_of_contact.yaml). Deliberately,
no raw.retrosheet_event/raw.retrosheet_gameinfo table exists anywhere in this
file -- compute() succeeding without them is itself proof the module no
longer depends on that source.
"""

from decimal import Decimal

from mlb_baseball.model import statcast_expected


def _ensure_statcast_pitch_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute(
            "CREATE TABLE raw.statcast_pitch ("
            "game_pk text, pitcher text, inning_topbot text, events text, bb_type text, "
            "launch_speed text, launch_speed_angle text, "
            "estimated_ba_using_speedangle text, estimated_slg_using_speedangle text, "
            "estimated_woba_using_speedangle text, _season text)"
        )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_pitch")
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player")
        cur.execute("DELETE FROM core.team")
    db_conn.commit()


def test_compute_noop_when_statcast_pitch_missing(db_conn):
    # Regression: compute() used to gate on raw.retrosheet_event/
    # raw.retrosheet_gameinfo existing; it must now gate on raw.statcast_pitch,
    # the table this module actually reads.
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
    db_conn.commit()

    assert statcast_expected.compute(db_conn) == 0


def test_compute_reads_real_statcast_expected_stat_columns(db_conn):
    # G1: home starter (mlbam 1001) faces 12 PA:
    #   5 batted balls (bb_type populated):
    #     2 barrels (launch_speed=100 >= 95mph hard-hit, launch_speed_angle='6'
    #       -- Savant's own Barrel classification, not a reimplemented EV/LA
    #       window), each with real Savant per-BIP xBA=0.800/xSLG=2.000/
    #       xwOBA=1.200
    #     3 weak-contact balls (launch_speed=80, launch_speed_angle='2'
    #       "Topped" -- not hard-hit, not barrel), each xBA=0.100/xSLG=0.100/
    #       xwOBA=0.100
    #   5 strikeouts (events='strikeout' -- count toward AB/PA, contribute 0)
    #   1 walk (events='walk'), 1 HBP (events='hit_by_pitch')
    #
    # Entering G2 (only G1 precedes it):
    #   bip_cnt=5, hard_hit_cnt=2, barrel_cnt=2 -> hard_hit_pct = barrel_pct = 0.4000
    #   ab_cnt = 5 (BIP) + 5 (K) = 10
    #   xba_sum = 2*0.800 + 3*0.100 = 1.900 -> xba = 1.900 / 10 = 0.1900
    #   xslg_sum = 2*2.000 + 3*0.100 = 4.300 -> xslg = 4.300 / 10 = 0.4300
    #   pa_cnt = 10 (AB) + 1 (BB) + 1 (HBP) = 12
    #   xwoba_contact_sum = 2*1.200 + 3*0.100 = 2.700
    #   xwoba = (2.700 + 0.69*1 + 0.72*1) / 12 = 4.110 / 12 = 0.3425
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('ATL', 'Atlanta', 'Braves', 1966, 9999, 144), "
            "('NYA', 'New York', 'Yankees', 1913, 9999, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro_id: team_id for team_id, retro_id in cur.fetchall()}
        atl, nya = teams["ATL"], teams["NYA"]
        cur.execute(
            "INSERT INTO core.player (retro_id, mlbam_id, first_name, last_name) "
            "VALUES ('pitc001', '1001', 'Ace', 'Pitcher'), "
            "('pitc002', '1002', 'Away', 'Pitcher') "
            "RETURNING id, mlbam_id"
        )
        players = {mlbam_id: player_id for player_id, mlbam_id in cur.fetchall()}
        p1, p2 = players["1001"], players["1002"]
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('G1', '7001', 2024, '2024-04-01', %(atl)s, %(nya)s, 5, 3, 'regular'), "
            "('G2', '7002', 2024, '2024-04-08', %(atl)s, %(nya)s, 4, 2, 'regular')",
            {"atl": atl, "nya": nya},
        )
        cur.execute(
            "INSERT INTO gold.game_feature "
            "(game_instance_key, mlb_game_pk, season, game_date, home_team_id, away_team_id, "
            "home_starter_id, away_starter_id, game_id) "
            "SELECT g.retro_game_id, g.game_pk::bigint, g.season, g.game_date, "
            "g.home_team_id, g.away_team_id, %(p1)s, %(p2)s, g.id FROM core.game g",
            {"p1": p1, "p2": p2},
        )

        pitches = []
        # 2 barrels: hard-hit (EV >= 95) and Savant's own Barrel classification
        # (launch_speed_angle = '6'), not a home-grown EV/LA window.
        for _ in range(2):
            pitches.append(
                "('7001', '1001', 'Top', 'home_run', 'line_drive', "
                "'100.0', '6', '0.800', '2.000', '1.200', '2024')"
            )
        # 3 weak-contact outs: not hard-hit, not barrel.
        for _ in range(3):
            pitches.append(
                "('7001', '1001', 'Top', 'field_out', 'ground_ball', "
                "'80.0', '2', '0.100', '0.100', '0.100', '2024')"
            )
        # 5 strikeouts.
        for _ in range(5):
            pitches.append(
                "('7001', '1001', 'Top', 'strikeout', NULL, NULL, NULL, NULL, NULL, NULL, '2024')"
            )
        # 1 walk, 1 HBP.
        pitches.append(
            "('7001', '1001', 'Top', 'walk', NULL, NULL, NULL, NULL, NULL, NULL, '2024')"
        )
        pitches.append(
            "('7001', '1001', 'Top', 'hit_by_pitch', NULL, NULL, NULL, NULL, NULL, NULL, '2024')"
        )

        # G2 minimal row so the rolling window has a (game, pitcher) position
        # to attach the rolled-forward-from-G1 rate to -- the window excludes
        # the current row, so this pitch contributes nothing to its own game's
        # displayed rate.
        pitches.append(
            "('7002', '1001', 'Top', 'field_out', 'fly_ball', "
            "'70.0', '2', '0.050', '0.050', '0.050', '2024')"
        )
        pitches.append(
            "('7002', '1002', 'Bot', 'field_out', 'fly_ball', "
            "'70.0', '2', '0.050', '0.050', '0.050', '2024')"
        )

        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, inning_topbot, events, bb_type, launch_speed, "
            "launch_speed_angle, estimated_ba_using_speedangle, "
            "estimated_slg_using_speedangle, estimated_woba_using_speedangle, _season) "
            f"VALUES {', '.join(pitches)}"
        )
    db_conn.commit()

    updated = statcast_expected.compute(db_conn)
    db_conn.commit()
    assert updated >= 1

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT g.retro_game_id, f.home_starter_hard_hit_pct, f.home_starter_barrel_pct, "
            "f.home_starter_xba, f.home_starter_xslg, f.home_starter_xwoba "
            "FROM gold.game_feature f JOIN core.game g ON g.id = f.game_id "
            "ORDER BY g.retro_game_id"
        )
        rows = {r[0]: r[1:] for r in cur.fetchall()}

    # Zero lookahead: G1 has no preceding games, so every rate is NULL.
    assert rows["G1"] == (None, None, None, None, None)
    assert rows["G2"] == (
        Decimal("0.4000"),
        Decimal("0.4000"),
        Decimal("0.1900"),
        Decimal("0.4300"),
        Decimal("0.3425"),
    )

    _reset(db_conn)


def test_health_check_passes():
    checks = statcast_expected.health_check()
    assert len(checks) == 2
    domain_check = next(c for c in checks if c.name == "model.statcast_expected.domain")
    assert domain_check.ok is True
