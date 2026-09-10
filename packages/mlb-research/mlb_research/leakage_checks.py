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
    # ATTACH under a fixed alias: opening the file as the default database makes
    # `feat.<table>` ambiguous when the file basename is also `feat`.
    con = duckdb.connect()
    con.execute(f"ATTACH '{str(path).replace(chr(39), chr(39) * 2)}' AS mlb_feat_db (READ_ONLY)")
    con.execute("USE mlb_feat_db")
    return con


def check_clock_consistency(
    db: str | os.PathLike[str] | None = None, *, feature_version: str = "v1"
) -> CheckResult:
    """Every feature row obeys ``event_ts <= available_ts <= visible_ts`` (the
    retrieval key ``visible_ts`` is never earlier than the data it summarises)
    and ``available_ts <= created_ts`` (the build ran after the inputs existed).
    A row that fails the first clause could be returned for a decision time
    before the baseball event was known — the exact leak ``visible_ts`` exists
    to prevent. In slice 1 (full rebuild) ``visible_ts = event_ts`` and
    ``created_ts`` is the build time; incremental builds will fold ``created_ts``
    into ``visible_ts`` and this check tightens with them.
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
                       AND available_ts <= created_ts)
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
        "all rows obey event_ts <= available_ts <= visible_ts and available_ts <= created_ts"
        if ok
        else f"{len(bad)} row(s) with an inconsistent clock",
        bad,
    )


def check_doubleheader_ordering(
    db: str | os.PathLike[str] | None = None, *, feature_version: str = "v1"
) -> CheckResult:
    """When an entity plays twice on the same calendar date (a doubleheader),
    game 1 must not enter game 2's rolling windows — the box score is not
    available in time. Both games' rows therefore see the *same* prior history,
    so every rolling numerator and exposure column must be **equal** across the
    two rows. A difference means game 1 leaked into game 2's window.

    This is checked on the output alone: `feat.*` does not carry per-game
    lines, but the window-frame lag guarantees the two same-day rows are
    computed over an identical input set.
    """
    con = _connect(db)
    try:
        parts = []
        for rel in _FORM_RELATIONS:
            num_cols = [
                r[0]
                for r in con.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='feat' AND table_name=? "
                    "AND (column_name LIKE '%_num_%' OR column_name LIKE 'pa\\_%' ESCAPE '\\' "
                    "OR column_name LIKE 'bf\\_%' ESCAPE '\\')",
                    [rel],
                ).fetchall()
            ]
            if not num_cols:
                continue
            diff = " OR ".join(f"a.{c} IS DISTINCT FROM b.{c}" for c in num_cols)
            parts.append(
                f"""
                SELECT '{rel}' AS relation, a.player_id AS entity_key,
                       a.event_ts AS game1_event_ts, b.event_ts AS game2_event_ts
                FROM feat.{rel} AS a
                JOIN feat.{rel} AS b
                  ON a.player_id = b.player_id
                 AND a.feature_version = b.feature_version
                 AND a.event_ts < b.event_ts
                 AND a.event_ts::DATE = b.event_ts::DATE
                WHERE a.feature_version = ? AND ({diff})
                """
            )
        if not parts:
            return CheckResult("doubleheader_ordering", True, "no form relations to check")
        bad = con.execute(" UNION ALL ".join(parts), [feature_version] * len(parts)).df()
    finally:
        con.close()
    ok = len(bad) == 0
    detail = (
        "same-day games see identical prior history — game 1 never enters game 2's window"
        if ok
        else f"{len(bad)} same-day pair(s) whose rolling windows differ (game 1 leaked forward)"
    )
    return CheckResult("doubleheader_ordering", ok, detail, bad)


def run_all(
    db: str | os.PathLike[str] | None = None, *, feature_version: str = "v1"
) -> list[CheckResult]:
    """Every store-level leakage check, in order. `mlb verify` calls this."""
    return [
        check_clock_consistency(db, feature_version=feature_version),
        check_doubleheader_ordering(db, feature_version=feature_version),
    ]
