"""Pure-logic tests for the FanGraphs connector — no network, no DB.

Covers the connector's own transforms: the fungo-call error boundary, the
projection change-detection hash, and the curated-split constant table.
"""

import fungo.fangraphs as fg
import pytest
from fungo.exceptions import FangraphsError, RequestError

from mlb_baseball.connectors import fangraphs


def test_fg_call_reraises_and_logs_fangraphs_error(capsys):
    def blocked():
        raise FangraphsError("HTTP 403 — Cloudflare exemption withdrawn")

    with pytest.raises(FangraphsError):
        fangraphs._fg_call(blocked)

    out = capsys.readouterr().out
    assert "fangraphs:" in out
    assert "FangraphsError" in out
    assert "403" in out


def test_fg_call_reraises_request_error(capsys):
    def exhausted():
        raise RequestError("Failed after 3 retries")

    with pytest.raises(RequestError):
        fangraphs._fg_call(exhausted)
    assert "RequestError" in capsys.readouterr().out


def test_fg_call_passes_through_success():
    assert fangraphs._fg_call(lambda a, b: a + b, 2, 3) == 5


def test_frame_renames_colliding_sign_variant_columns():
    # -WPA / +WPA both sanitize to _wpa; K-BB% / K/BB+ both to k_bb_.
    # _frame must split them before load_dataframe's collision check fires.
    rows = [{"WPA": 1.0, "-WPA": -2.0, "+WPA": 3.0, "K-BB%": 0.1, "K/BB+": 1.2, "HR": 30}]
    df = fangraphs._frame(rows)

    assert set(df.columns) == {"WPA", "WPA_neg", "WPA_pos", "K_minus_BB_pct", "K_per_BB_plus", "HR"}
    assert df["WPA_neg"].iloc[0] == -2.0
    assert df["WPA_pos"].iloc[0] == 3.0


def test_frame_is_a_noop_when_no_colliding_columns_present():
    rows = [{"playerName": "A", "HR": 5}]
    df = fangraphs._frame(rows)
    assert list(df.columns) == ["playerName", "HR"]


def test_projection_value_hash_ignores_bookkeeping_and_is_order_stable():
    row_a = {"HR": 30, "WAR": 4.1, "playerid": "1234"}
    row_b = {"WAR": 4.1, "HR": 30, "playerid": "1234"}
    assert fangraphs._projection_value_hash(row_a) == fangraphs._projection_value_hash(row_b)

    # bookkeeping columns (leading underscore) never affect the hash
    with_bookkeeping = {**row_a, "_projection_system": "steamer", "_captured_date": "2026-09-10"}
    assert fangraphs._projection_value_hash(with_bookkeeping) == fangraphs._projection_value_hash(
        row_a
    )


def test_projection_value_hash_changes_when_a_value_changes():
    base = {"HR": 30, "WAR": 4.1}
    moved = {"HR": 31, "WAR": 4.1}
    assert fangraphs._projection_value_hash(base) != fangraphs._projection_value_hash(moved)


def test_projection_rows_tags_horizon_and_skips_idless_rows(monkeypatch):
    payload = [
        {"playerid": "100", "HR": 20},
        {"playerid": None, "HR": 5},  # no id -> cannot track history -> dropped
        {"playerid": "", "HR": 6},  # blank id -> dropped
        {"playerid": "100", "HR": 99},  # dup id in one system -> first wins
    ]
    monkeypatch.setattr(fangraphs, "_fg_call", lambda fn, *a, **k: payload)

    rows = fangraphs._projection_rows("steamer", "bat", "preseason", "2026-09-10")

    assert len(rows) == 1
    (row,) = rows
    assert row["playerid"] == "100"
    assert row["HR"] == 20
    assert row["_projection_system"] == "steamer"
    assert row["_stat_group"] == "bat"
    assert row["_horizon"] == "preseason"
    assert row["_captured_date"] == "2026-09-10"
    assert row["_row_hash"] == fangraphs._projection_value_hash({"playerid": "100", "HR": 20})


def test_changed_projection_rows_keeps_only_new_or_moved():
    rows = [
        {
            "_projection_system": "steamer",
            "_stat_group": "bat",
            "playerid": "1",
            "_row_hash": "aaa",
        },
        {
            "_projection_system": "steamer",
            "_stat_group": "bat",
            "playerid": "2",
            "_row_hash": "bbb",
        },
        {
            "_projection_system": "steamer",
            "_stat_group": "bat",
            "playerid": "3",
            "_row_hash": "ccc",
        },
    ]
    known = {
        ("steamer", "bat", "1"): "aaa",  # unchanged -> dropped
        ("steamer", "bat", "2"): "OLD",  # moved -> kept
        # playerid 3 not seen before -> kept
    }

    changed = fangraphs._changed_projection_rows(rows, known)

    assert {r["playerid"] for r in changed} == {"2", "3"}


def test_curated_splits_all_resolve_in_fungo():
    for name in fangraphs.CURATED_SPLITS:
        assert name in fg.SPLIT_CODES, name


def test_curated_splits_cover_the_spec_minimum():
    required = {"vs_lhp", "vs_rhp", "home", "away"}
    assert required <= set(fangraphs.CURATED_SPLITS)
    months = {"march_april", "may", "june", "july", "august", "sept_oct"}
    assert months <= set(fangraphs.CURATED_SPLITS)


def test_projection_systems_split_into_preseason_and_ros():
    assert fangraphs.PRESEASON_SYSTEMS == list(fg.PROJECTION_SYSTEMS)
    assert fangraphs.ROS_SYSTEMS == list(fg.ROS_PROJECTION_SYSTEMS)
    assert set(fangraphs.PRESEASON_SYSTEMS).isdisjoint(fangraphs.ROS_SYSTEMS)
