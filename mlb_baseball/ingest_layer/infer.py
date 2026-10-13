"""Propose a PostgreSQL type for each column of an all-text frame (used to write the declared
schemas in ``schemas/``; the declaration, not this guess, is what ingest enforces).

Conservative on purpose: a column gets a narrower type only when EVERY non-empty value
fits it and nothing is lost on the round trip. Leading zeros, plus signs, mixed values and
empty columns stay ``text``.
"""

import polars as pl

_INT = r"^-?(0|[1-9][0-9]*)$"
_FLOAT = r"^-?(0|[1-9][0-9]*)\.[0-9]+$|^-?[0-9]+(\.[0-9]+)?[eE][-+]?[0-9]+$"
_NUMBER = _INT + "|" + _FLOAT
_DATE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
_TIMESTAMPTZ = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9:.]+(Z|[-+][0-9]{2}(:?[0-9]{2})?)$"
_INT32 = 2**31 - 1


def infer_column(values: pl.Series) -> str:
    """The narrowest kind that holds every non-empty value exactly."""
    present = values.filter(values.is_not_null() & (values != ""))
    if present.len() == 0:
        return "text"
    if present.str.contains(_INT).all():
        ints = present.cast(pl.Int64, strict=False)
        if ints.null_count() == 0:
            return "integer" if ints.abs().max() <= _INT32 else "bigint"  # type: ignore[operator]
        return "text"
    if present.str.contains(_NUMBER).all():
        return "double precision"  # decimals, or a mix of whole numbers and decimals
    if present.str.contains(_DATE).all():
        parsed = present.str.to_date("%Y-%m-%d", strict=False)
        return "date" if parsed.null_count() == 0 else "text"
    if present.str.contains(_TIMESTAMPTZ).all():
        return "timestamptz"
    return "text"


def infer_schema(frame: pl.DataFrame) -> dict[str, str]:
    return {name: infer_column(frame[name]) for name in frame.columns}


def propose(source: str, frames: dict[str, pl.DataFrame]) -> None:
    """Write ``schemas/<source>.json`` from real data (a starting point to review)."""
    from mlb_baseball.ingest_layer import schemas

    schemas.write(source, {t: {"columns": infer_schema(f)} for t, f in frames.items()})
