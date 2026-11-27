"""Type contract (dlt-ingestion-layer D9): empty is NULL never zero, bad values are rejected
with a reason and kept as source text, nothing raises."""

import polars as pl

from mlb_baseball import market_store as ms
from mlb_baseball.ingest_layer.types import arrow_schema, cast

FRAME = pl.DataFrame(
    {
        "clob_token_id": ["a", "b", "", "c", "d"],
        "_market": ["1", "", "x", "2", "3"],
        "_event": ["1"] * 5,
        "ts": ["10", "11", "12", "99999999999999999999", "14"],
        "price": ["0.5", "", "0.1", "0.2", "nan"],
        "extra": ["x", "y", "z", "w", "v"],
    }
)


def test_empty_becomes_null_and_types_are_declared():
    good, _ = cast(FRAME, ms.POLYMARKET_PRICE)
    assert good.schema["ts"] == pl.Int64 and good.schema["price"] == pl.Float64
    assert good["price"].to_list() == [0.5, None]  # empty source value is NULL, not 0
    assert good["_market"].to_list() == [1, None]
    assert good.schema["extra"] == pl.String  # unknown source field stays text


def test_bad_values_are_rejected_with_reason_and_source_text():
    _, rejected = cast(FRAME, ms.POLYMARKET_PRICE)
    assert rejected["reason"].to_list() == [
        "clob_token_id is empty",
        "ts is not a valid bigint",
        "price is not a valid double precision",
    ]
    assert rejected["ts"].to_list()[1] == "99999999999999999999"  # kept as the source text
    assert rejected["price"].to_list()[2] == "nan"


def test_arrow_schema_matches_declared_columns():
    schema = arrow_schema(ms.POLYMARKET_PRICE)
    assert schema.names == ["clob_token_id", "_market", "_event", "ts", "price"]
    assert str(schema.field("ts").type) == "int64"
    assert not schema.field("ts").nullable


def test_already_typed_input_is_accepted():
    good, rejected = cast(
        pl.DataFrame({"clob_token_id": ["a"], "ts": [5], "price": [0.25]}), ms.POLYMARKET_PRICE
    )
    assert good.height == 1 and rejected.height == 0


def test_state_dir_follows_mlb_home_and_lists_leftover_runs(tmp_path, monkeypatch):
    from mlb_baseball.ingest_layer.state import leftover_runs, state_dir

    monkeypatch.setenv("MLB_HOME", str(tmp_path))
    assert state_dir() == tmp_path / "dlt" and leftover_runs() == []
    (tmp_path / "dlt" / "tmpabc").mkdir(parents=True)
    assert [p.name for p in leftover_runs()] == ["tmpabc"]


def test_doctor_line_for_dlt_state_never_fails(tmp_path, monkeypatch):
    from mlb_baseball import doctor

    monkeypatch.setenv("MLB_HOME", str(tmp_path))
    (tmp_path / "dlt" / "tmpabc").mkdir(parents=True)
    check = doctor._dlt_state_directory()
    assert check.ok and "1 leftover" in check.detail
