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


def _row(pid, day, k, *, version="v1", created=None, avail_hours=6):
    ev = datetime(2024, 6, day, 0, 0)
    av = datetime(2024, 6, day, avail_hours, 0)
    cr = created or datetime(2024, 1, 1)
    vis = max(av, cr)
    return (pid, ev, av, cr, vis, version, 100, k, 0.08)


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


def test_row_created_after_the_decision_time_is_invisible(tmp_path):
    db = tmp_path / "mlb.duckdb"
    # same player, one snapshot, but it was written into the build on 6/15
    _build(db, [_row(1, 1, 0.20, created=datetime(2024, 6, 15))])
    early = pd.DataFrame({"player_id": [1], "event_timestamp": [datetime(2024, 6, 10)]})
    late = pd.DataFrame({"player_id": [1], "event_timestamp": [datetime(2024, 6, 20)]})
    assert pd.isna(
        get_historical_features(early, ["player_form:k_pct_30d"], db=db)["k_pct_30d"].iloc[0]
    )
    assert (
        get_historical_features(late, ["player_form:k_pct_30d"], db=db)["k_pct_30d"].iloc[0] == 0.20
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
