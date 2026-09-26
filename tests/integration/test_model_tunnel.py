"""Integration coverage for mlb_baseball.model.tunnel.tunnel_pair_from_statcast --
computes real pitch tunneling from a pitcher's real release/trajectory kinematics
(raw.statcast_pitch), replacing the poc_factor=0.30 approximation for the
real-data path (metric-catalog triage, 2026-09-23; see
mlb_baseball/metrics/pitch_tunneling_engine.yaml).
"""

from mlb_baseball.model.tunnel import DATA_SOURCE_STATCAST, tunnel_pair_from_statcast


def _ensure_statcast_pitch_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute(
            "CREATE TABLE raw.statcast_pitch ("
            "game_pk text, pitcher text, pitch_type text, game_date text, "
            "release_pos_x text, release_pos_z text, "
            "vx0 text, vy0 text, vz0 text, ax text, ay text, az text, "
            "plate_x text, plate_z text, game_year text)"
        )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_pitch")
    db_conn.commit()


def _row(game_pk, pitcher, pitch_type, game_date, x0, z0, vx0, vy0, vz0, ax, ay, az, px, pz):
    return (
        f"('{game_pk}', '{pitcher}', '{pitch_type}', '{game_date}', "
        f"'{x0}', '{z0}', '{vx0}', '{vy0}', '{vz0}', '{ax}', '{ay}', '{az}', "
        f"'{px}', '{pz}', '2024')"
    )


def test_tunnel_pair_from_statcast_computes_real_kinematics_separation(db_conn):
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    rows = [
        # Two FF pitches, nearly identical release/kinematics.
        _row(
            "7001",
            "1001",
            "FF",
            "2024-04-05",
            -2.0,
            6.0,
            4.0,
            -130.0,
            -6.0,
            -2.0,
            25.0,
            -16.0,
            0.3,
            2.5,
        ),
        _row(
            "7002",
            "1001",
            "FF",
            "2024-04-06",
            -2.0,
            6.0,
            4.2,
            -130.5,
            -5.8,
            -2.1,
            25.2,
            -16.2,
            0.4,
            2.6,
        ),
        # Two SL pitches, same release point as FF but different late break (ax/az/plate).
        _row(
            "7003",
            "1001",
            "SL",
            "2024-04-05",
            -2.0,
            6.0,
            3.0,
            -120.0,
            -6.5,
            4.0,
            22.0,
            -30.0,
            -0.8,
            1.0,
        ),
        _row(
            "7004",
            "1001",
            "SL",
            "2024-04-06",
            -2.0,
            6.0,
            3.2,
            -120.2,
            -6.3,
            4.2,
            22.2,
            -30.2,
            -0.7,
            1.1,
        ),
        # Different pitcher: must not affect the result.
        _row(
            "7005",
            "1002",
            "FF",
            "2024-04-05",
            -1.0,
            6.5,
            5.0,
            -135.0,
            -5.0,
            -1.0,
            24.0,
            -15.0,
            0.0,
            2.8,
        ),
    ]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, pitch_type, game_date, release_pos_x, release_pos_z, "
            "vx0, vy0, vz0, ax, ay, az, plate_x, plate_z, game_year) "
            f"VALUES {', '.join(rows)}"
        )
    db_conn.commit()

    result = tunnel_pair_from_statcast(
        pitcher_mlbam_id="1001",
        pitch_type_a="FF",
        pitch_type_b="SL",
        date_from="2024-04-01",
        date_to="2024-04-30",
        conn=db_conn,
    )

    assert result is not None
    assert result.data_source == DATA_SOURCE_STATCAST
    assert result.pitch_pair_label == "FF-SL"
    assert result.release_distance_in < 1.0  # near-identical real release points
    assert result.plate_break_separation_in > 0.0
    assert result.tunnel_distance_at_poc_in >= 0.0
    assert result.break_tunnel_ratio != 0.0

    _reset(db_conn)


def test_tunnel_pair_from_statcast_returns_none_when_no_coverage(db_conn):
    """A pitcher/pitch-type/date-range with no kinematics coverage gets an honest None."""
    _reset(db_conn)


def test_tunnel_pair_from_statcast_anchors_kinematics_at_plate_not_release(db_conn):
    """A release-coordinate difference alone cannot create tunnel separation.

    Statcast's velocity/acceleration vectors use y=50 ft as their reference
    plane, while release_pos_* is recorded earlier in flight.  These pitches
    have identical kinematics and measured plate positions but deliberately
    different release positions; the real tunnel point must therefore match.
    """
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    rows = [
        _row(
            "7010",
            "1003",
            "FF",
            "2024-04-05",
            -2.0,
            6.0,
            4.0,
            -130.0,
            -6.0,
            -2.0,
            25.0,
            -16.0,
            0.3,
            2.5,
        ),
        _row(
            "7011",
            "1003",
            "SL",
            "2024-04-05",
            -4.0,
            4.0,
            4.0,
            -130.0,
            -6.0,
            -2.0,
            25.0,
            -16.0,
            0.3,
            2.5,
        ),
    ]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, pitch_type, game_date, release_pos_x, release_pos_z, "
            "vx0, vy0, vz0, ax, ay, az, plate_x, plate_z, game_year) "
            f"VALUES {', '.join(rows)}"
        )
    db_conn.commit()

    result = tunnel_pair_from_statcast(
        pitcher_mlbam_id="1003",
        pitch_type_a="FF",
        pitch_type_b="SL",
        date_from="2024-04-01",
        date_to="2024-04-30",
        conn=db_conn,
    )

    assert result is not None
    assert result.release_distance_in > 20.0
    assert result.tunnel_distance_at_poc_in == 0.0

    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    result = tunnel_pair_from_statcast(
        pitcher_mlbam_id="9999",
        pitch_type_a="FF",
        pitch_type_b="SL",
        date_from="2024-04-01",
        date_to="2024-04-30",
        conn=db_conn,
    )

    assert result is None

    _reset(db_conn)
