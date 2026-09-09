"""The two store-level leakage checks (feature-store-v1, task 6.1).
No model, no sklearn. Hand-built feat.* tables.
"""

import sys
from datetime import datetime, timedelta

import duckdb
import pytest
from mlb_research.leakage_checks import (
    check_clock_consistency,
    check_doubleheader_ordering,
    run_all,
)

_COLS = (
    "player_id BIGINT, event_ts TIMESTAMP, available_ts TIMESTAMP, "
    "created_ts TIMESTAMP, visible_ts TIMESTAMP, feature_version TEXT, k_pct_30d DOUBLE"
)


def _db(tmp_path, player_rows, pitcher_rows=None):
    con = duckdb.connect(str(tmp_path / "mlb.duckdb"))
    con.execute("CREATE SCHEMA feat")
    for rel in ("player_form", "pitcher_form"):
        con.execute(f"CREATE TABLE feat.{rel} ({_COLS})")
    if player_rows:
        con.executemany("INSERT INTO feat.player_form VALUES (?,?,?,?,?,?,?)", player_rows)
    if pitcher_rows:
        con.executemany("INSERT INTO feat.pitcher_form VALUES (?,?,?,?,?,?,?)", pitcher_rows)
    con.close()
    return tmp_path / "mlb.duckdb"


def _clean_row(pid, day, dh=0):
    ev = datetime(2024, 6, day) + timedelta(hours=3 * dh)
    av = ev + timedelta(hours=6)
    cr = datetime(2024, 1, 1)
    return (pid, ev, av, cr, max(av, cr), "v1", 0.2)


# --- clock consistency ---


def test_clock_check_passes_on_a_clean_build(tmp_path):
    db = _db(tmp_path, [_clean_row(1, 1), _clean_row(1, 8)])
    assert check_clock_consistency(db).ok


def test_clock_check_fails_when_available_precedes_event(tmp_path):
    ev = datetime(2024, 6, 10)
    backdated = (
        1,
        ev,
        ev - timedelta(days=2),
        datetime(2024, 1, 1),
        ev - timedelta(days=2),
        "v1",
        0.2,
    )
    db = _db(tmp_path, [backdated])
    r = check_clock_consistency(db)
    assert not r.ok
    assert len(r.evidence) == 1


def test_clock_check_fails_when_created_after_visible(tmp_path):
    ev = datetime(2024, 6, 10)
    av = ev + timedelta(hours=6)
    bad = (1, ev, av, ev + timedelta(days=30), av, "v1", 0.2)  # created_ts > visible_ts
    db = _db(tmp_path, [bad])
    assert not check_clock_consistency(db).ok


# --- doubleheader ordering ---


def test_doubleheader_check_passes_when_game1_available_after_game2_starts(tmp_path):
    db = _db(tmp_path, [_clean_row(1, 5, dh=1), _clean_row(1, 5, dh=2)])
    r = check_doubleheader_ordering(db)
    assert r.ok, r.evidence.to_dict()


def test_doubleheader_check_fails_when_game1_leaks_into_game2(tmp_path):
    g1_ev = datetime(2024, 6, 5, 3)
    g1_avail = g1_ev + timedelta(hours=1)  # available before game 2 starts -> leak
    g2_ev = datetime(2024, 6, 5, 6)
    rows = [
        (1, g1_ev, g1_avail, datetime(2024, 1, 1), max(g1_avail, datetime(2024, 1, 1)), "v1", 0.2),
        (
            1,
            g2_ev,
            g2_ev + timedelta(hours=6),
            datetime(2024, 1, 1),
            g2_ev + timedelta(hours=6),
            "v1",
            0.2,
        ),
    ]
    db = _db(tmp_path, rows)
    r = check_doubleheader_ordering(db)
    assert not r.ok
    assert len(r.evidence) == 1


def test_doubleheader_check_ignores_games_a_day_apart(tmp_path):
    db = _db(tmp_path, [_clean_row(1, 5), _clean_row(1, 6)])
    assert check_doubleheader_ordering(db).ok


# --- run_all / no sklearn ---


def test_run_all_returns_both_checks(tmp_path):
    db = _db(tmp_path, [_clean_row(1, 1)])
    results = run_all(db)
    assert [r.name for r in results] == ["clock_consistency", "doubleheader_ordering"]
    assert all(results)


def test_module_imports_without_sklearn_or_xgboost():
    assert "sklearn" not in sys.modules
    assert "xgboost" not in sys.modules


def test_missing_build_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="mlb build"):
        check_clock_consistency(tmp_path / "nope.duckdb")
