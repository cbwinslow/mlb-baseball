"""Declared column types for landed tables, and the cast that enforces them (D9).

One declaration per table (the existing ``market_store.MarketTable``): this module adds no
second registry. ``cast`` takes a frame of source values, turns empty strings into NULL
(never zero), casts to the declared types without raising, and splits the frame into rows
that pass and rows kept as source text with the reason they failed.
"""

import re

import polars as pl
import pyarrow as pa

from mlb_baseball.market_store import Column, MarketTable

REASON = "reason"
_NUMERIC = re.compile(r"^numeric\((\d+),\s*(\d+)\)$")
_FIXED = {
    "integer": (pl.Int32, pa.int32()),
    "bigint": (pl.Int64, pa.int64()),
    "double precision": (pl.Float64, pa.float64()),
    "text": (pl.String, pa.string()),
}


def _pl_type(column: Column) -> pl.DataType | type[pl.DataType]:
    if column.kind in _FIXED:
        return _FIXED[column.kind][0]
    match = _NUMERIC.match(column.kind)
    if match:
        return pl.Decimal(int(match.group(1)), int(match.group(2)))
    raise ValueError(f"column {column.name}: no Arrow type declared for {column.kind!r}")


def arrow_schema(table: MarketTable) -> pa.Schema:
    """The declared columns as a pyarrow schema (what a test compares with the database)."""
    fields = []
    for column in table.columns:
        if column.kind in _FIXED:
            arrow = _FIXED[column.kind][1]
        else:
            match = _NUMERIC.match(column.kind)
            if not match:
                raise ValueError(f"column {column.name}: no Arrow type for {column.kind!r}")
            arrow = pa.decimal128(int(match.group(1)), int(match.group(2)))
        fields.append(pa.field(column.name, arrow, nullable=column.nullable))
    return pa.schema(fields)


def cast(frame: pl.DataFrame, table: MarketTable) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return ``(good, rejected)``. ``good`` has the declared columns typed and every other
    column as text; ``rejected`` has every column as the source text plus ``reason``."""
    source = frame.select(pl.all().cast(pl.String))
    clean = source.select(
        pl.when(pl.col(c) == "").then(None).otherwise(pl.col(c)).alias(c) for c in source.columns
    )
    typed = table.typed()
    reasons: list[pl.Expr] = []
    casts: dict[str, pl.Expr] = {}
    for name in clean.columns:
        column = typed.get(name)
        if column is None:
            continue
        value = pl.col(name)
        if not column.nullable:
            reasons.append(pl.when(value.is_null()).then(pl.lit(f"{name} is empty")))
        if column.kind == "text":
            continue
        converted = value.cast(_pl_type(column), strict=False)
        casts[name] = converted
        failed = value.is_not_null() & converted.is_null()
        if column.kind == "double precision":
            failed = failed | converted.is_nan() | converted.is_infinite()
        reasons.append(pl.when(failed).then(pl.lit(f"{name} is not a valid {column.kind}")))
    flagged = clean.with_columns(
        pl.coalesce(reasons).alias(REASON) if reasons else pl.lit(None).alias(REASON)
    )
    ok = flagged[REASON].is_null()
    good = flagged.filter(ok).drop(REASON).with_columns(**{k: v for k, v in casts.items()})
    rejected = source.filter(~ok).with_columns(flagged.filter(~ok)[REASON])
    return good, rejected
