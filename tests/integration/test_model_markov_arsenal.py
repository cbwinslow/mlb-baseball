"""Integration tests for pitch arsenal & batter pitch-type database fetching
in Markov module (PLN-04, ADR-100).
"""

from datetime import date

import pytest

from mlb_baseball.model import markov


def _ensure_arsenal_tables(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitcher_arsenal_stat')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.statcast_pitcher_arsenal_stat ("
                "player_id text, pitch_type text, pitch_usage text, "
                "run_value_per_100 text, woba text, whiff_percent text, _season text)"
            )
        cur.execute("SELECT to_regclass('raw.statcast_batter_arsenal')")
        if not cur.fetchone()[0]:
            cur.execute(
                "CREATE TABLE raw.statcast_batter_arsenal ("
                "player_id text, pitch_type text, pitches text, "
                "run_value_per_100 text, woba text, whiff_percent text, _season text)"
            )
    db_conn.commit()


def _reset(db_conn):
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw.statcast_pitcher_arsenal_stat')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_pitcher_arsenal_stat")
        cur.execute("SELECT to_regclass('raw.statcast_batter_arsenal')")
        if cur.fetchone()[0]:
            cur.execute("DELETE FROM raw.statcast_batter_arsenal")
    db_conn.commit()


def test_fetch_pitcher_and_batter_arsenal(db_conn):
    _reset(db_conn)
    _ensure_arsenal_tables(db_conn)

    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitcher_arsenal_stat "
            "(player_id, pitch_type, pitch_usage, run_value_per_100, woba, whiff_percent, _season) "
            "VALUES ('544931', 'CU', '30.7', '2.3', '0.208', '38.8', '2019'), "
            "('544931', 'FF', '28.6', '0.4', '0.334', '23.9', '2019')"
        )
        cur.execute(
            "INSERT INTO raw.statcast_batter_arsenal "
            "(player_id, pitch_type, pitches, run_value_per_100, woba, whiff_percent, _season) "
            "VALUES ('518692', 'CU', '243', '3.5', '0.479', '26.2', '2019'), "
            "('518692', 'FF', '986', '2.2', '0.430', '18.6', '2019')"
        )
    db_conn.commit()

    pitcher = markov.fetch_pitcher_arsenal(db_conn, "544931", 2019)
    batter = markov.fetch_batter_arsenal(db_conn, "518692", 2019)

    assert pitcher is not None
    assert pitcher.player_id == "544931"
    assert pitcher.season == 2019
    assert abs(pitcher.pitch_usage["CU"] - 0.307) < 1e-4
    assert abs(pitcher.run_values_per_100["CU"] - 2.3) < 1e-4

    assert batter is not None
    assert batter.player_id == "518692"
    assert batter.pitches_seen["FF"] == 986
    assert abs(batter.run_values_per_100["FF"] - 2.2) < 1e-4

    edge = markov.compute_arsenal_matchup_edge(pitcher, batter)
    # Norm usage: CU = 30.7 / (30.7 + 28.6) = 30.7 / 59.3 = 0.5177
    #            FF = 28.6 / 59.3 = 0.4823
    # Edge = 0.5177 * (3.5 - 2.3) + 0.4823 * (2.2 - 0.4)
    #      = 0.5177 * 1.2 + 0.4823 * 1.8 = 0.62124 + 0.86814 = 1.48938
    assert abs(edge - 1.4894) < 1e-3

    _reset(db_conn)


def test_fetch_returns_none_when_tables_missing(db_conn):
    _reset(db_conn)
    with db_conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS raw.statcast_pitcher_arsenal_stat")
        cur.execute("DROP TABLE IF EXISTS raw.statcast_batter_arsenal")
    db_conn.commit()

    assert markov.fetch_pitcher_arsenal(db_conn, "544931", 2019) is None
    assert markov.fetch_batter_arsenal(db_conn, "518692", 2019) is None
    _reset(db_conn)


def test_fetch_pitcher_arsenal_rejects_invalid_season(db_conn):
    """fetch_pitcher_arsenal must validate the season argument. The upper
    bound is dynamic (this year + 1), so a year comfortably past it and a
    year before the first pro season are both out of range, always."""
    _reset(db_conn)
    _ensure_arsenal_tables(db_conn)
    this_year = date.today().year
    with pytest.raises(ValueError):
        markov.fetch_pitcher_arsenal(db_conn, "544931", 1870)
    with pytest.raises(ValueError):
        markov.fetch_pitcher_arsenal(db_conn, "544931", this_year + 2)  # just past the bound
    with pytest.raises(ValueError):
        markov.fetch_pitcher_arsenal(db_conn, "544931", "not-a-year")
    with pytest.raises(ValueError):
        markov.fetch_pitcher_arsenal(db_conn, "544931", 2019.9)  # float is not coerced
    with pytest.raises(ValueError):
        markov.fetch_pitcher_arsenal(db_conn, "544931", True)  # bool is not coerced
    _reset(db_conn)


def test_fetch_batter_arsenal_rejects_invalid_season(db_conn):
    """fetch_batter_arsenal must validate the season argument."""
    _reset(db_conn)
    _ensure_arsenal_tables(db_conn)
    this_year = date.today().year
    with pytest.raises(ValueError):
        markov.fetch_batter_arsenal(db_conn, "518692", 1870)
    with pytest.raises(ValueError):
        markov.fetch_batter_arsenal(db_conn, "518692", this_year + 2)  # just past the bound
    with pytest.raises(ValueError):
        markov.fetch_batter_arsenal(db_conn, "518692", "not-a-year")
    with pytest.raises(ValueError):
        markov.fetch_batter_arsenal(db_conn, "518692", 2019.9)  # float is not coerced
    with pytest.raises(ValueError):
        markov.fetch_batter_arsenal(db_conn, "518692", True)  # bool is not coerced
    _reset(db_conn)


def test_fetch_arsenal_still_accepts_a_numeric_string_season(db_conn):
    """Regression: the season guard must not reject "2019" — the arsenal
    SQL binds str(season) either way, so that shape worked before the
    guard and rejecting it now would be a needless breaking change."""
    _reset(db_conn)
    _ensure_arsenal_tables(db_conn)
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw.statcast_pitcher_arsenal_stat "
            "(player_id, pitch_type, pitch_usage, run_value_per_100, woba, "
            "whiff_percent, _season) VALUES ('544931', 'CU', '30.7', '2.3', "
            "'0.208', '38.8', '2019')"
        )
    db_conn.commit()

    assert markov.fetch_pitcher_arsenal(db_conn, "544931", "2019") is not None
    assert markov.fetch_batter_arsenal(db_conn, "518692", "2019") is None  # no rows, not an error
    _reset(db_conn)


def test_fetch_arsenal_accepts_next_year_at_the_dynamic_upper_bound(db_conn):
    """The upper bound is this year + 1: next year is in range (no rows
    yet, so None), the year after is out of range (ValueError)."""
    _reset(db_conn)
    _ensure_arsenal_tables(db_conn)
    next_year = date.today().year + 1
    for fetch in (markov.fetch_pitcher_arsenal, markov.fetch_batter_arsenal):
        assert fetch(db_conn, "544931", next_year) is None
        with pytest.raises(ValueError):
            fetch(db_conn, "544931", next_year + 1)
    _reset(db_conn)
