"""The two store-level leakage checks (feature-store-v1, task 6.1).
No model, no sklearn. Hand-built feat.* tables.
"""

import subprocess
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
    "created_ts TIMESTAMP, visible_ts TIMESTAMP, feature_version TEXT, "
    "k_pct_30d DOUBLE, pa_30d INTEGER, so_num_30d INTEGER"
)


def _db(tmp_path, player_rows, pitcher_rows=None):
    con = duckdb.connect(str(tmp_path / "mlb.duckdb"))
    con.execute("CREATE SCHEMA feat")
    for rel in ("player_form", "pitcher_form"):
        con.execute(f"CREATE TABLE feat.{rel} ({_COLS})")
    if player_rows:
        con.executemany("INSERT INTO feat.player_form VALUES (?,?,?,?,?,?,?,?,?)", player_rows)
    if pitcher_rows:
        con.executemany("INSERT INTO feat.pitcher_form VALUES (?,?,?,?,?,?,?,?,?)", pitcher_rows)
    con.close()
    return tmp_path / "mlb.duckdb"


def _row(pid, day, dh=0, *, pa=100, so=20):
    # available_ts = visible_ts = event_ts (the slice-1 model — the lag lives in
    # the window frame). created_ts is the build time: after the event.
    ev = datetime(2024, 6, day) + timedelta(hours=3 * dh)
    cr = datetime(2026, 1, 1)
    return (pid, ev, ev, cr, ev, "v1", so / pa, pa, so)


# --- clock consistency ---


def test_clock_check_passes_on_a_clean_build(tmp_path):
    db = _db(tmp_path, [_row(1, 1), _row(1, 8)])
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
        100,
        20,
    )
    db = _db(tmp_path, [backdated])
    r = check_clock_consistency(db)
    assert not r.ok
    assert len(r.evidence) == 1


def test_clock_check_fails_when_created_before_data_was_available(tmp_path):
    ev = datetime(2024, 6, 10)
    # created_ts predates available_ts: the row claims to have been built before
    # its own inputs existed.
    bad = (1, ev, ev, ev - timedelta(days=30), ev, "v1", 0.2, 100, 20)
    db = _db(tmp_path, [bad])
    assert not check_clock_consistency(db).ok


# --- doubleheader ordering: same-day rows must have identical windows ---


def test_doubleheader_check_passes_when_both_same_day_rows_share_history(tmp_path):
    # game 1 excluded from game 2's window -> identical numerators
    db = _db(tmp_path, [_row(1, 5, dh=1, pa=90, so=18), _row(1, 5, dh=2, pa=90, so=18)])
    r = check_doubleheader_ordering(db)
    assert r.ok, r.evidence.to_dict()


def test_doubleheader_check_fails_when_game1_enters_game2_window(tmp_path):
    # game 2's row has more PA -> game 1's line leaked in
    db = _db(tmp_path, [_row(1, 5, dh=1, pa=90, so=18), _row(1, 5, dh=2, pa=95, so=19)])
    r = check_doubleheader_ordering(db)
    assert not r.ok
    assert len(r.evidence) == 1


def test_doubleheader_check_ignores_games_on_different_days(tmp_path):
    db = _db(tmp_path, [_row(1, 5, pa=90, so=18), _row(1, 6, pa=95, so=19)])
    assert check_doubleheader_ordering(db).ok


# --- run_all / no sklearn ---


def test_run_all_returns_both_checks(tmp_path):
    db = _db(tmp_path, [_row(1, 1)])
    results = run_all(db)
    assert [r.name for r in results] == ["clock_consistency", "doubleheader_ordering"]
    assert all(results)


def test_module_imports_without_sklearn_or_xgboost():
    # Run in a clean interpreter: another test in this process may already have
    # imported sklearn/xgboost transitively (e.g. via the CLI), which says
    # nothing about what leakage_checks itself pulls in.
    code = (
        "import sys; import mlb_research.leakage_checks; "
        "assert 'sklearn' not in sys.modules, 'leakage_checks imported sklearn'; "
        "assert 'xgboost' not in sys.modules, 'leakage_checks imported xgboost'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_missing_build_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="mlb build"):
        check_clock_consistency(tmp_path / "nope.duckdb")
