"""Integration coverage for mlb_baseball.model.babip.babip_from_statcast --
computes real actual BABIP and real Statcast-xBA-based expected BABIP from
raw.statcast_pitch, replacing the uncited linear xBABIP formula (metric-catalog
triage, 2026-09-23; see mlb_baseball/metrics/babip_luck_scanner.yaml).
"""

from mlb_baseball.model.babip import DATA_SOURCE_STATCAST, babip_from_statcast


def _ensure_statcast_pitch_table(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitch")
        cur.execute(
            "CREATE TABLE raw.statcast_pitch ("
            "game_pk text, batter text, player_name text, game_date text, "
            "events text, bb_type text, estimated_ba_using_speedangle text, game_year text)"
        )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitch')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_pitch")
    db_conn.commit()


def _row(game_pk, batter, name, game_date, events, bb_type, xba):
    bb_type_sql = f"'{bb_type}'" if bb_type is not None else "NULL"
    xba_sql = f"'{xba}'" if xba is not None else "NULL"
    return (
        f"('{game_pk}', '{batter}', '{name}', '{game_date}', "
        f"'{events}', {bb_type_sql}, {xba_sql}, '2024')"
    )


def test_babip_from_statcast_computes_real_actual_and_expected_babip(db_conn):
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    rows = [
        _row("7001", "3001", "Real Batter", "2024-04-05", "single", "line_drive", "0.700"),
        _row("7002", "3001", "Real Batter", "2024-04-06", "field_out", "ground_ball", "0.100"),
        _row("7003", "3001", "Real Batter", "2024-04-07", "double", "line_drive", "0.600"),
        # Home run: has bb_type set but must be excluded from BIP/hits (BABIP excludes HR).
        _row("7004", "3001", "Real Batter", "2024-04-08", "home_run", "fly_ball", "0.900"),
        # Strikeout and walk: no bb_type, must be excluded entirely.
        _row("7005", "3001", "Real Batter", "2024-04-09", "strikeout", None, None),
        _row("7006", "3001", "Real Batter", "2024-04-10", "walk", None, None),
        # Out of the requested date window: must not affect the result.
        _row("7007", "3001", "Real Batter", "2024-05-01", "single", "line_drive", "0.800"),
        # Different batter: must not affect the result.
        _row("7008", "3002", "Other Batter", "2024-04-06", "single", "line_drive", "0.750"),
    ]
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, batter, player_name, game_date, events, bb_type, "
            "estimated_ba_using_speedangle, game_year) "
            f"VALUES {', '.join(rows)}"
        )
    db_conn.commit()

    result = babip_from_statcast(
        batter_mlbam_id="3001",
        date_from="2024-04-01",
        date_to="2024-04-30",
        conn=db_conn,
    )

    assert result is not None
    assert result.data_source == DATA_SOURCE_STATCAST
    assert result.batter_name == "Real Batter"
    # BIP (non-HR) = single, field_out, double = 3; hits = single, double = 2
    assert result.balls_in_play == 3
    assert result.actual_babip == round(2 / 3, 3)
    # Expected = mean xBA over the same 3 BIP rows = (0.700+0.100+0.600)/3
    assert result.expected_xbabip == round((0.700 + 0.100 + 0.600) / 3, 3)
    assert result.regression_tier == "SEVERE_NEGATIVE_REGRESSION"
    assert result.is_buy_low_candidate is False

    _reset(db_conn)


def test_babip_from_statcast_returns_none_when_no_coverage(db_conn):
    """A batter/date range with no batted-ball data (e.g. pre-2015) gets an honest None."""
    _reset(db_conn)
    _ensure_statcast_pitch_table(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitch "
            "(game_pk, batter, player_name, game_date, events, bb_type, "
            "estimated_ba_using_speedangle, game_year) "
            "VALUES ('7010', '4001', 'Old Timer', '2010-05-01', 'strikeout', NULL, NULL, '2010')"
        )
    db_conn.commit()

    result = babip_from_statcast(
        batter_mlbam_id="4001",
        date_from="2010-01-01",
        date_to="2010-12-31",
        conn=db_conn,
    )

    assert result is None

    _reset(db_conn)
