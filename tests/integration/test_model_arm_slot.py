"""Integration coverage for mlb_baseball.model.arm_slot.arm_slot_from_statcast --
reads Baseball Savant's own published per-pitch Arm Angle (raw.statcast_pitch.arm_angle),
populated from the 2020 season on, instead of an uncited geometric estimate
(metric-catalog triage, 2026-09-23; see mlb_baseball/metrics/arm_slot_engine.yaml).
"""

from mlb_baseball.model.arm_slot import DATA_SOURCE_STATCAST, arm_slot_from_statcast


def _ensure_statcast_pitch_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute(
            "CREATE TABLE raw.statcast_pitch ("
            "game_pk text, pitcher text, player_name text, game_date text, "
            "arm_angle text, game_year text)"
        )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_pitch")
    db_conn.commit()


def test_arm_slot_from_statcast_averages_real_arm_angle(db_conn):
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    # 3 pitches with real Statcast arm_angle readings in-range, plus one
    # out-of-range (different pitcher) and one out-of-window (wrong date)
    # pitch that must not be included in the average.
    rows = [
        ("'7001'", "'1001'", "'Ace Pitcher'", "'2024-04-05'", "'34.0'", "'2024'"),
        ("'7001'", "'1001'", "'Ace Pitcher'", "'2024-04-06'", "'36.0'", "'2024'"),
        ("'7001'", "'1001'", "'Ace Pitcher'", "'2024-04-07'", "'35.0'", "'2024'"),
        ("'7002'", "'1002'", "'Other Pitcher'", "'2024-04-06'", "'70.0'", "'2024'"),
        ("'7003'", "'1001'", "'Ace Pitcher'", "'2024-05-01'", "'80.0'", "'2024'"),
    ]
    with db_conn.cursor() as cur:
        values = ", ".join(f"({', '.join(r)})" for r in rows)
        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, player_name, game_date, arm_angle, game_year) "
            f"VALUES {values}"
        )
    db_conn.commit()

    result = arm_slot_from_statcast(
        pitcher_mlbam_id="1001",
        date_from="2024-04-01",
        date_to="2024-04-30",
        conn=db_conn,
    )

    assert result is not None
    assert result.data_source == DATA_SOURCE_STATCAST
    assert result.pitcher_name == "Ace Pitcher"
    assert result.arm_slot_angle_deg == 35.0  # mean of 34.0/36.0/35.0, not the out-of-window 80.0
    assert result.sample_size == 3
    # Savant's arm_angle is degrees from HORIZONTAL (0=sidearm, 90=overhand);
    # _classify_tier expects degrees from VERTICAL (0=overhand, 90+=submarine),
    # so 35.0 real degrees converts to 90-35=55 before tiering (PR #242 review).
    assert result.arm_slot_tier == "LOW_THREE_QUARTERS"

    _reset(db_conn)


def test_arm_slot_from_statcast_low_angle_is_sidearm_not_over_the_top(db_conn):
    """A real LOW Savant arm_angle (near horizontal) must tier as SIDEARM, not OVER_THE_TOP.

    Regression for the inverted-convention bug (PR #242 CodeRabbit review):
    passing Savant's raw degrees straight into _classify_tier without
    converting from its horizontal convention to _classify_tier's vertical
    one silently flipped sidearm and over-the-top pitchers.
    """
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, player_name, game_date, arm_angle, game_year) "
            "VALUES ('7020', '1003', 'Low Slot Reliever', '2024-04-05', '8.0', '2024')"
        )
    db_conn.commit()

    result = arm_slot_from_statcast(
        pitcher_mlbam_id="1003",
        date_from="2024-04-01",
        date_to="2024-04-30",
        conn=db_conn,
    )

    assert result is not None
    assert result.arm_slot_angle_deg == 8.0
    assert result.arm_slot_tier == "SIDEARM"

    _reset(db_conn)


def test_arm_slot_from_statcast_high_angle_is_over_the_top_not_sidearm(db_conn):
    """A real HIGH Savant arm_angle (near vertical) must tier as OVER_THE_TOP, not SIDEARM."""
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, player_name, game_date, arm_angle, game_year) "
            "VALUES ('7021', '1004', 'Drop-and-Drive Starter', '2024-04-05', '82.0', '2024')"
        )
    db_conn.commit()

    result = arm_slot_from_statcast(
        pitcher_mlbam_id="1004",
        date_from="2024-04-01",
        date_to="2024-04-30",
        conn=db_conn,
    )

    assert result is not None
    assert result.arm_slot_angle_deg == 82.0
    assert result.arm_slot_tier == "OVER_THE_TOP"

    _reset(db_conn)


def test_arm_slot_from_statcast_returns_none_when_no_coverage(db_conn):
    """A pitcher/date range with no arm_angle data (e.g. pre-2020) gets an honest None."""
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, pitcher, player_name, game_date, arm_angle, game_year) "
            "VALUES ('7010', '2001', 'Old Timer', '2012-05-01', NULL, '2012')"
        )
    db_conn.commit()

    result = arm_slot_from_statcast(
        pitcher_mlbam_id="2001",
        date_from="2012-01-01",
        date_to="2012-12-31",
        conn=db_conn,
    )

    assert result is None

    _reset(db_conn)
