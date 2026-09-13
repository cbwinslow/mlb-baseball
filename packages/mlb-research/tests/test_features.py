"""get_historical_features — point-in-time retrieval contract
(feature-store-v1, task 5.1). Standalone: no mlb_baseball, no PostgreSQL.
A tiny feat.player_form is hand-built with duckdb.
"""

from datetime import datetime

import duckdb
import pandas as pd
import pytest
from mlb_research.features import get_historical_features


def _build(path, rows):
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA IF NOT EXISTS feat")
    con.execute(
        """
        CREATE TABLE feat.player_form (
            player_id BIGINT, event_ts TIMESTAMP, available_ts TIMESTAMP,
            created_ts TIMESTAMP, visible_ts TIMESTAMP, feature_version TEXT,
            pa_30d INTEGER, k_pct_30d DOUBLE, bb_pct_30d DOUBLE
        )
        """
    )
    con.executemany(
        "INSERT INTO feat.player_form VALUES (?,?,?,?,?,?,?,?,?)",
        rows,
    )
    con.close()


def _row(pid, day, k, *, version="v1"):
    # slice-1 clock model: a form row's value is entering form, so
    # available_ts == visible_ts == event_ts. created_ts is audit metadata
    # (uniform across a full rebuild); it does not gate retrieval.
    ev = datetime(2024, 6, day, 0, 0)
    return (pid, ev, ev, datetime(2024, 1, 1), ev, version, 100, k, 0.08)


def test_returns_the_latest_snapshot_before_the_decision_time(tmp_path):
    db = tmp_path / "mlb.duckdb"
    _build(db, [_row(1, 1, 0.20), _row(1, 10, 0.25), _row(1, 20, 0.30)])
    entity = pd.DataFrame(
        {"player_id": [1, 1], "event_timestamp": [datetime(2024, 6, 12), datetime(2024, 6, 5)]}
    )
    out = get_historical_features(entity, ["player_form:k_pct_30d"], db=db)
    assert list(out["k_pct_30d"]) == [0.25, 0.20]  # the 6/10 snapshot, then the 6/1 snapshot


def test_missing_before_first_snapshot_is_null_never_forward_filled(tmp_path):
    db = tmp_path / "mlb.duckdb"
    _build(db, [_row(1, 10, 0.25)])
    entity = pd.DataFrame({"player_id": [1], "event_timestamp": [datetime(2024, 6, 1)]})
    out = get_historical_features(entity, ["player_form:k_pct_30d"], db=db)
    assert pd.isna(out["k_pct_30d"].iloc[0])


def test_one_output_row_per_input_row_in_input_order(tmp_path):
    db = tmp_path / "mlb.duckdb"
    _build(db, [_row(1, 1, 0.20), _row(2, 1, 0.15)])
    entity = pd.DataFrame(
        {
            "player_id": [2, 1, 2],
            "event_timestamp": [datetime(2024, 6, 5)] * 3,
            "tag": ["a", "b", "c"],
        }
    )
    out = get_historical_features(entity, ["player_form:k_pct_30d"], db=db)
    assert list(out["tag"]) == ["a", "b", "c"]
    assert list(out["k_pct_30d"]) == [0.15, 0.20, 0.15]


def test_retrieval_asof_key_is_visible_ts(tmp_path):
    # The ASOF join is on visible_ts, not event_ts or available_ts directly.
    # In slice 1 those are equal on a real build; here they are set apart so a
    # regression that joins on the wrong column is caught.
    db = tmp_path / "mlb.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA feat")
    con.execute(
        "CREATE TABLE feat.player_form (player_id BIGINT, event_ts TIMESTAMP, "
        "available_ts TIMESTAMP, created_ts TIMESTAMP, visible_ts TIMESTAMP, "
        "feature_version TEXT, k_pct_30d DOUBLE)"
    )
    # event_ts 6/1, but visible_ts pushed to 6/20 (as an incremental build's
    # created_ts would do)
    con.execute(
        "INSERT INTO feat.player_form VALUES "
        "(1, '2024-06-01', '2024-06-01', '2024-06-20', '2024-06-20', 'v1', 0.20)"
    )
    con.close()
    before = pd.DataFrame({"player_id": [1], "event_timestamp": [datetime(2024, 6, 10)]})
    after = pd.DataFrame({"player_id": [1], "event_timestamp": [datetime(2024, 6, 25)]})
    assert pd.isna(
        get_historical_features(before, ["player_form:k_pct_30d"], db=db)["k_pct_30d"].iloc[0]
    )
    assert (
        get_historical_features(after, ["player_form:k_pct_30d"], db=db)["k_pct_30d"].iloc[0]
        == 0.20
    )


def test_unknown_feature_ref_raises_before_any_query(tmp_path):
    db = tmp_path / "mlb.duckdb"
    _build(db, [_row(1, 1, 0.20)])
    entity = pd.DataFrame({"player_id": [1], "event_timestamp": [datetime(2024, 6, 5)]})
    with pytest.raises(ValueError, match="no column"):
        get_historical_features(entity, ["player_form:not_a_feature"], db=db)
    with pytest.raises(ValueError, match="unknown feature view"):
        get_historical_features(entity, ["nope:x"], db=db)
    with pytest.raises(ValueError, match="not '<view>:<feature>'"):
        get_historical_features(entity, ["no_colon"], db=db)


def test_feature_version_is_respected(tmp_path):
    db = tmp_path / "mlb.duckdb"
    _build(db, [_row(1, 1, 0.20, version="v1"), _row(1, 1, 0.99, version="v2")])
    entity = pd.DataFrame({"player_id": [1], "event_timestamp": [datetime(2024, 6, 5)]})
    assert (
        get_historical_features(entity, ["player_form:k_pct_30d"], db=db)["k_pct_30d"].iloc[0]
        == 0.20
    )
    v2 = get_historical_features(entity, ["player_form:k_pct_30d"], db=db, feature_version="v2")
    assert v2["k_pct_30d"].iloc[0] == 0.99


def test_no_build_raises_clearly(tmp_path):
    entity = pd.DataFrame({"player_id": [1], "event_timestamp": [datetime(2024, 6, 5)]})
    with pytest.raises(FileNotFoundError, match="mlb build"):
        get_historical_features(entity, ["player_form:k_pct_30d"], db=tmp_path / "absent.duckdb")
