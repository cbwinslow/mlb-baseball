"""Point-in-time feature retrieval — Feast's shape, one DuckDB ASOF JOIN inside.

``get_historical_features`` takes an entity dataframe (entity ids + a decision
timestamp) and a list of ``"view:feature"`` refs, and returns one row per input
row with each feature as it stood *before* that row's decision time. A feature
with no qualifying value is returned missing — never forward-filled, never
defaulted.

This is Feast's `get_historical_features` signature and vocabulary without the
Feast dependency (see ``openspec/changes/feature-store-v1/`` — no Feast, with a
recorded adoption trigger). The point-in-time correctness lives in the DuckDB
`ASOF LEFT JOIN` on ``decision_time >= visible_ts`` plus the entity-key equality;
``visible_ts`` is ``GREATEST(available_ts, created_ts)`` so a row is invisible
both before the baseball event was known and before the build wrote it.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd

from mlb_research.paths import resolve_db_path

# view name -> (entity-key column — the same name in entity_df and the feat
# table, e.g. `player_id` — and the DuckDB table)
_VIEWS: dict[str, tuple[str, str]] = {
    "player_form": ("player_id", "feat.player_form"),
    "pitcher_form": ("player_id", "feat.pitcher_form"),
    "game": ("game_pk", "feat.game"),
}

_RESERVED = {"event_ts", "available_ts", "created_ts", "visible_ts", "feature_version"}


def _parse_refs(features: Sequence[str]) -> dict[str, list[str]]:
    by_view: dict[str, list[str]] = {}
    for ref in features:
        if ":" not in ref:
            raise ValueError(
                f"feature ref {ref!r} is not '<view>:<feature>'. "
                f"Known views: {', '.join(sorted(_VIEWS))}."
            )
        view, col = ref.split(":", 1)
        if view not in _VIEWS:
            raise ValueError(
                f"unknown feature view {view!r} in {ref!r}. "
                f"Known views: {', '.join(sorted(_VIEWS))}."
            )
        by_view.setdefault(view, []).append(col)
    return by_view


def _validate_columns(con: duckdb.DuckDBPyConnection, view: str, cols: list[str]) -> None:
    _, table = _VIEWS[view]
    present = {
        r[0]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'feat' AND table_name = ?",
            [table.split(".", 1)[1]],
        ).fetchall()
    }
    if not present:
        raise ValueError(
            f"feature view {view!r} ({table}) is not in this build — run `mlb build` first."
        )
    missing = [c for c in cols if c not in present]
    if missing:
        usable = sorted(present - _RESERVED)
        raise ValueError(
            f"feature view {view!r} has no column(s) {missing}. Available: {', '.join(usable)}."
        )


def get_historical_features(
    entity_df: pd.DataFrame,
    features: Sequence[str],
    *,
    timestamp_col: str = "event_timestamp",
    feature_version: str = "v1",
    db: str | os.PathLike[str] | None = None,
) -> pd.DataFrame:
    """Return ``entity_df`` with each requested feature joined point-in-time.

    ``entity_df`` must carry ``timestamp_col`` (the decision time) and, for every
    view referenced, that view's entity-key column (``player_id`` for
    ``player_form`` / ``pitcher_form``, ``game_pk`` for ``game``). One output row
    per input row, in input order. A feature with no value at or before the
    decision time is missing.

    Raises ``ValueError`` for a malformed ref, an unknown view, an unknown
    feature column, a missing entity-key column, or a view absent from the build.
    """
    if timestamp_col not in entity_df.columns:
        raise ValueError(f"entity_df has no timestamp column {timestamp_col!r}")

    by_view = _parse_refs(features)
    db_path = resolve_db_path(db)
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"no feature database at {db_path} — run `mlb build` (or pass db=...)."
        )

    work = entity_df.reset_index(drop=True).copy()
    work["__row__"] = range(len(work))

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for view, cols in by_view.items():
            entity_key, table = _VIEWS[view]
            if entity_key not in work.columns:
                raise ValueError(
                    f"feature view {view!r} needs an {entity_key!r} column in entity_df"
                )
            _validate_columns(con, view, cols)

            con.register("entity_df", work)
            select_feats = ", ".join(f'f."{c}" AS "{view}__{c}"' for c in cols)
            rows = con.execute(
                f"""
                SELECT e.*, {select_feats}
                FROM entity_df AS e
                ASOF LEFT JOIN {table} AS f
                  ON e."{entity_key}" = f."{entity_key}"
                 AND f.feature_version = ?
                 AND e."{timestamp_col}" >= f.visible_ts
                ORDER BY e.__row__
                """,
                [feature_version],
            ).df()
            con.unregister("entity_df")
            rename = {
                f"{view}__{c}": (c if c not in work.columns else f"{view}__{c}") for c in cols
            }
            rows = rows.rename(columns=rename)
            work = rows
    finally:
        con.close()

    return work.drop(columns="__row__").reset_index(drop=True)
