"""Two leakage checks that test the *store*, not a model
(feature-store-v1, design D5/D7).

Neither needs a model, a label, or sklearn. They run against a local DuckDB
build and return a :class:`CheckResult` with the offending rows attached, so an
analyst can audit their own build (`mlb verify` runs both).

The two model-diagnostic checks from earlier drafts — shuffle the labels, inject
the outcome as a feature — are not here: they need a fitted model and prove
nothing about the store. They live in a notebook recipe (slice 3).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

from mlb_research.paths import resolve_db_path

_FORM_RELATIONS = ("player_form", "pitcher_form")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    evidence: pd.DataFrame = field(default_factory=pd.DataFrame)

    def __bool__(self) -> bool:
        return self.ok


def _connect(db: str | os.PathLike[str] | None) -> duckdb.DuckDBPyConnection:
    path = resolve_db_path(db)
    if not Path(path).exists():
        raise FileNotFoundError(f"no feature database at {path} — run `mlb build` first.")
    return duckdb.connect(str(path), read_only=True)


def check_clock_consistency(
    db: str | os.PathLike[str] | None = None, *, feature_version: str = "v1"
) -> CheckResult:
    """Every feature row obeys ``event_ts <= available_ts <= visible_ts`` and
    ``created_ts <= visible_ts``. A row that fails this could be returned for a
    decision time before the baseball event was known or before the build wrote
    it — the exact leak ``visible_ts`` exists to prevent.
    """
    con = _connect(db)
    try:
        parts = [
            f"""
            SELECT '{rel}' AS relation, entity_key, event_ts, available_ts,
                   created_ts, visible_ts
            FROM (
                SELECT player_id AS entity_key, event_ts, available_ts,
                       created_ts, visible_ts
                FROM feat.{rel} WHERE feature_version = ?
            )
            WHERE NOT (event_ts <= available_ts
                       AND available_ts <= visible_ts
                       AND created_ts <= visible_ts)
            """
            for rel in _FORM_RELATIONS
        ]
        bad = con.execute(" UNION ALL ".join(parts), [feature_version] * len(parts)).df()
    finally:
        con.close()
    ok = len(bad) == 0
    return CheckResult(
        "clock_consistency",
        ok,
        "all rows obey event_ts <= available_ts <= visible_ts, created_ts <= visible_ts"
        if ok
        else f"{len(bad)} row(s) with an inconsistent clock",
        bad,
    )


def check_doubleheader_ordering(
    db: str | os.PathLike[str] | None = None, *, feature_version: str = "v1"
) -> CheckResult:
    """For two games of the same entity less than a day apart (a doubleheader),
    the earlier game's box score must not be visible when the later game's
    features are assembled — its ``available_ts`` must land at or after the later
    game's ``event_ts``. A violation means game 2 could see game 1.
    """
    con = _connect(db)
    try:
        parts = [
            f"""
            SELECT '{rel}' AS relation, a.player_id AS entity_key,
                   a.event_ts AS earlier_event_ts, a.available_ts AS earlier_available_ts,
                   b.event_ts AS later_event_ts
            FROM feat.{rel} AS a
            JOIN feat.{rel} AS b
              ON a.player_id = b.player_id
             AND a.feature_version = b.feature_version
             AND a.event_ts < b.event_ts
             AND b.event_ts - a.event_ts < INTERVAL 1 DAY
            WHERE a.feature_version = ?
              AND a.available_ts < b.event_ts
            """
            for rel in _FORM_RELATIONS
        ]
        bad = con.execute(" UNION ALL ".join(parts), [feature_version] * len(parts)).df()
    finally:
        con.close()
    ok = len(bad) == 0
    return CheckResult(
        "doubleheader_ordering",
        ok,
        "same-day games are ordered so an earlier game is never visible to a later one"
        if ok
        else f"{len(bad)} same-day pair(s) where the earlier game leaks into the later",
        bad,
    )


def run_all(
    db: str | os.PathLike[str] | None = None, *, feature_version: str = "v1"
) -> list[CheckResult]:
    """Every store-level leakage check, in order. `mlb verify` calls this."""
    return [
        check_clock_consistency(db, feature_version=feature_version),
        check_doubleheader_ordering(db, feature_version=feature_version),
    ]
