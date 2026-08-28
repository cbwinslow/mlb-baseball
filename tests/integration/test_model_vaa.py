"""Entering four-seam VAA from Statcast kinematics (WIRE of VAA-01)."""

from mlb_baseball.model import vaa


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM gold.prediction")
        cur.execute("DELETE FROM gold.game_feature")
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_pitch WHERE pitcher = '201001'")
        cur.execute("DELETE FROM core.game")
        cur.execute("DELETE FROM core.player WHERE id IN (201, 202)")
        cur.execute(
            "DELETE FROM core.team_alias a USING core.team t "
            "WHERE a.team_id = t.id AND t.retro_team_id IN ('BOS', 'NYA')"
        )
        cur.execute("DELETE FROM core.team WHERE retro_team_id IN ('BOS', 'NYA')")
    db_conn.commit()


def _ensure_statcast(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.statcast_pitch ("
                "game_pk text, pitcher text, pitch_type text, "
                "vy0 text, ay text, vz0 text, az text)"
            )
        for col in ("vy0", "ay", "vz0", "az", "pitcher", "pitch_type", "game_pk"):
            cur.execute(f"ALTER TABLE raw.statcast_pitch ADD COLUMN IF NOT EXISTS {col} text")
        cur.execute("DELETE FROM raw.statcast_pitch WHERE pitcher = '201001'")
    db_conn.commit()


def test_compute_is_point_in_time_and_matches_python_formula(db_conn):
    _reset(db_conn)
    _ensure_statcast(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE gold.game_feature ADD COLUMN IF NOT EXISTS home_starter_ff_vaa numeric"
        )
        cur.execute(
            "ALTER TABLE gold.game_feature ADD COLUMN IF NOT EXISTS away_starter_ff_vaa numeric"
        )
        cur.execute(
            "INSERT INTO core.team "
            "(retro_team_id, city, nickname, first_year, last_year, mlb_team_id) "
            "VALUES ('BOS', 'Boston', 'Red Sox', 1901, 2025, 111), "
            "('NYA', 'New York', 'Yankees', 1913, 2025, 147) "
            "RETURNING id, retro_team_id"
        )
        teams = {retro: i for i, retro in cur.fetchall()}
        cur.execute(
            "INSERT INTO core.player (id, retro_id, mlbam_id, first_name, last_name) "
            "VALUES (201, 'vaa001', '201001', 'Test', 'Starter') "
            "ON CONFLICT (id) DO UPDATE SET mlbam_id = '201001'"
        )
        cur.execute(
            "INSERT INTO core.game "
            "(retro_game_id, game_pk, season, game_date, home_team_id, away_team_id, "
            "home_score, away_score, game_type) VALUES "
            "('V1', '88001', 2024, '2024-04-01', %(bos)s, %(nya)s, 5, 3, 'regular'), "
            "('V2', '88002', 2024, '2024-04-08', %(bos)s, %(nya)s, 4, 2, 'regular') "
            "RETURNING id, retro_game_id",
            {"bos": teams["BOS"], "nya": teams["NYA"]},
        )
        games = {retro: i for i, retro in cur.fetchall()}
        for key, gid, pk in (("G1", games["V1"], "88001"), ("G2", games["V2"], "88002")):
            cur.execute(
                "INSERT INTO gold.game_feature "
                "(game_id, mlb_game_pk, game_instance_key, season, game_date, "
                "home_team_id, away_team_id, home_starter_id, home_win) "
                "VALUES (%s, %s, %s, 2024, '2024-04-01', %s, %s, 201, TRUE)",
                (gid, pk, key, teams["BOS"], teams["NYA"]),
            )
        cur.execute(
            "UPDATE gold.game_feature SET game_date = '2024-04-08' WHERE game_instance_key = 'G2'"
        )
        for _ in range(20):
            cur.execute(
                "INSERT INTO raw.statcast_pitch "
                "(game_pk, pitcher, pitch_type, vy0, ay, vz0, az) "
                "VALUES ('88001', '201001', 'FF', '-130', '30', '-8', '-20')"
            )
    db_conn.commit()

    expected = vaa.pitch_vaa_degrees(vy0=-130.0, ay=30.0, vz0=-8.0, az=-20.0)
    rows = vaa.compute(db_conn)
    assert rows >= 1
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT game_instance_key, home_starter_ff_vaa "
            "FROM gold.game_feature ORDER BY game_instance_key"
        )
        got = dict(cur.fetchall())
    assert got["G1"] is None
    assert expected is not None
    assert abs(float(got["G2"]) - expected) < 0.01

    _reset(db_conn)


def test_compute_noops_when_statcast_kinematics_are_missing(db_conn):
    _reset(db_conn)
    assert vaa.compute(db_conn) == 0
    _reset(db_conn)
