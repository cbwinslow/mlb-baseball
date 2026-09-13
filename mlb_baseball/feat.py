"""The DuckDB feature build (feature-store-v1, slice 1).

`mlb build` calls :func:`build`. It reads the PostgreSQL ``gold`` / ``core``
layer (ATTACHed READ_ONLY) and writes three append-only relations into one
local DuckDB file under a ``feat`` schema:

* ``feat.player_form``  -- one row per ``(player_id, event_ts, feature_version)``
* ``feat.pitcher_form`` -- one row per ``(player_id, event_ts, feature_version)``
* ``feat.game``         -- one row per ``(game_pk, feature_version)``

The boundary is design decision D2: PostgreSQL stays authoritative for
``raw`` / ``core``; the feature and model layer is DuckDB-only. Nothing here
touches PostgreSQL ``gold.game_feature`` or writes to PostgreSQL at all.

Build-time parameters travel to the versioned ``.sql`` files as DuckDB session
variables (``feat_version``, ``feat_lag_hours``), not as psycopg placeholders
-- these files are DuckDB dialect and live in ``mlb_baseball/sql/duckdb/``.
``AVAILABLE_LAG_HOURS`` is the single source of truth for the box-score
availability lag; all three relations read it through ``feat_lag_hours``.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
from mlb_research.paths import resolve_db_path

from mlb_baseball import config
from mlb_baseball.health import Check
from mlb_baseball.sql import read_sql

# Hours from first pitch to when a game's box score is available. A documented
# assumption, not a measurement -- Retrosheet has no ingest timestamp (design
# D5, docs/FEATURE_STORE.md). It lives ONLY in the rolling-window frames (which
# prior games are eligible to contribute); a form row's own available_ts is its
# event_ts, because the row's value is entering form (prior games only) and is
# knowable at first pitch. 6h > the 3h doubleheader spacing, so a
# doubleheader's game 1 does not enter game 2's windows.
AVAILABLE_LAG_HOURS = 6

# EB shrink strength for the k%/bb% shrunk columns (design D4). Stored on
# every row as shrink_m; kept here so the value has one home.
SHRINK_M = 100

# relation name -> read_sql() resource, in build order (feat.game reads
# feat.pitcher_form, so the form relations must exist first).
_RELATION_SQL: tuple[tuple[str, str], ...] = (
    ("feat.player_form", "duckdb/feat_player_form.sql"),
    ("feat.pitcher_form", "duckdb/feat_pitcher_form.sql"),
    ("feat.game", "duckdb/feat_game.sql"),
)


def _quote(value: str) -> str:
    """Escape a value for a DuckDB single-quoted literal (ATTACH takes no
    parameter binding for its connection-string argument)."""
    return value.replace("'", "''")


def build(
    *,
    duckdb_path: str | os.PathLike[str] | None = None,
    pg_url: str | None = None,
    feature_version: str = "v1",
) -> dict[str, int]:
    """Build the three feature relations into the DuckDB file. Returns
    ``{relation: row_count}`` for the just-built ``feature_version``.

    ``duckdb_path`` resolves through :func:`mlb_research.paths.resolve_db_path`
    (explicit > ``$MLB_DUCKDB_PATH`` > ``~/.mlb/mlb.duckdb``); ``pg_url``
    defaults to :func:`mlb_baseball.config.database_url`.
    """
    db_path = resolve_db_path(duckdb_path)
    url = pg_url or config.database_url()

    # In-memory root connection; the feature file is ATTACHed under a fixed
    # alias so `feat.<relation>` always resolves to the schema, never to a
    # catalog that happens to share the file's basename.
    con = duckdb.connect()
    try:
        con.execute("INSTALL postgres")
        con.execute("LOAD postgres")
        con.execute("SET VARIABLE feat_version = ?", [feature_version])
        con.execute("SET VARIABLE feat_lag_hours = ?", [AVAILABLE_LAG_HOURS])
        con.execute(f"ATTACH '{_quote(str(db_path))}' AS mlbfeat")
        con.execute(f"ATTACH '{_quote(url)}' AS pg (TYPE postgres, READ_ONLY)")
        con.execute("USE mlbfeat")
        con.execute("CREATE SCHEMA IF NOT EXISTS feat")

        counts: dict[str, int] = {}
        for relation, resource in _RELATION_SQL:
            con.execute(read_sql(resource))
            row = con.execute(
                f"SELECT count(*) FROM {relation} "  # noqa: S608 -- relation is a module constant
                "WHERE feature_version = getvariable('feat_version')"
            ).fetchone()
            counts[relation] = int(row[0]) if row else 0
        return counts
    finally:
        con.close()


def verify(
    *,
    duckdb_path: str | os.PathLike[str] | None = None,
    feature_version: str = "v1",
    run_tie_out: bool = True,
) -> bool:
    """`mlb verify` -- audit a feature-store build the way an outside analyst
    would audit their own. Prints, returns True iff everything passed.

    1. The two store-level leakage checks (`mlb_research.leakage_checks`) --
       clock consistency and doubleheader ordering. No model, no labels.
    2. The build's `created_ts` range, so a stale file is visible.
    3. Optionally the Baseball-Reference tie-out on the PostgreSQL backbone
       (`scripts/verify_baseball_reference_tie_out.py`) -- slower, needs a
       fully-built `gold`; skip with `--skip-tie-out`.
    """
    from mlb_research import leakage_checks

    ok = True

    path = _resolved_path_no_create(duckdb_path)
    if not path.exists():
        print(f"[FAIL] feature build: none at {path} -- run `mlb build`")
        return False

    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{_quote(str(path))}' AS mlbfeat (READ_ONLY)")
        con.execute("USE mlbfeat")
        rng = con.execute(
            "SELECT min(created_ts), max(created_ts) FROM feat.player_form "
            "WHERE feature_version = ?",
            [feature_version],
        ).fetchone()
    finally:
        con.close()
    if rng and rng[0] is not None:
        print(f"[INFO] build created_ts: {rng[0]} .. {rng[1]}  (feature_version={feature_version})")

    for result in leakage_checks.run_all(path, feature_version=feature_version):
        status = "OK" if result.ok else "FAIL"
        print(f"[{status}] leakage/{result.name}: {result.detail}")
        if not result.ok:
            ok = False
            for _, row in result.evidence.head(5).iterrows():
                print(f"        {row.to_dict()}")

    if run_tie_out:
        import subprocess
        import sys

        script = (
            Path(__file__).resolve().parent.parent
            / "scripts"
            / "verify_baseball_reference_tie_out.py"
        )
        print("[..] Baseball-Reference tie-out (backbone) ...")
        proc = subprocess.run([sys.executable, str(script)], check=False)
        if proc.returncode == 0:
            print("[OK] Baseball-Reference tie-out")
        else:
            ok = False
            print(f"[FAIL] Baseball-Reference tie-out (exit {proc.returncode})")

    print(f"\n{'verify passed' if ok else 'verify FAILED'}")
    return ok


def _resolved_path_no_create(explicit: str | os.PathLike[str] | None) -> Path:
    """The path :func:`build` would use, without creating its parent dir --
    for health_check, which must not have side effects on a fresh machine."""
    if explicit is not None:
        return Path(explicit).expanduser()
    env = os.environ.get("MLB_DUCKDB_PATH")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".mlb" / "mlb.duckdb"


_RELATION_ENTITY_KEY: dict[str, str] = {
    "feat.player_form": "player_id",
    "feat.pitcher_form": "player_id",
    "feat.game": "game_pk",
}

# (rate column, denominator column) pairs whose "rate NULL iff denominator 0"
# invariant health_check asserts. Only the single-column-denominator rates --
# obp/slg/babip have composite denominators.
_RATE_DENOM_CHECKS: dict[str, tuple[tuple[str, str], ...]] = {
    "feat.player_form": (
        ("k_pct_7d", "pa_7d"),
        ("k_pct_30d", "pa_30d"),
        ("k_pct_std", "pa_std"),
        ("bb_pct_7d", "pa_7d"),
    ),
    "feat.pitcher_form": (
        ("k_pct_7d", "bf_7d"),
        ("k_pct_30d", "bf_30d"),
        ("k_pct_std", "bf_std"),
        ("bb_pct_30d", "bf_30d"),
    ),
}


def health_check(duckdb_path: str | os.PathLike[str] | None = None) -> list[Check]:
    """`mlb doctor` checks for the DuckDB feature store.

    When a build exists: every relation has rows, no duplicate
    ``(entity_id, event_ts, feature_version)``, ``event_ts <= available_ts <=
    visible_ts`` on every row, and each single-denominator rate is NULL
    exactly when its denominator is 0.
    """
    path = _resolved_path_no_create(duckdb_path)
    if not path.exists():
        return [Check("feat build", False, f"no DuckDB feature build at {path} -- run `mlb build`")]

    checks: list[Check] = []
    con = duckdb.connect()
    try:
        con.execute(f"ATTACH '{_quote(str(path))}' AS mlbfeat (READ_ONLY)")
        con.execute("USE mlbfeat")
    except (duckdb.Error, OSError) as exc:
        con.close()
        return [Check("feat build", False, f"cannot open {path}: {exc}")]

    def scalar(sql: str) -> int:
        row = con.execute(sql).fetchone()  # noqa: S608 -- all SQL built from module constants
        return int(row[0]) if row and row[0] is not None else 0

    try:
        created = con.execute(
            "SELECT min(created_ts), max(created_ts) FROM feat.player_form"
        ).fetchone()
        if created and created[0] is not None:
            checks.append(Check("feat build created_ts", True, f"{created[0]} .. {created[1]}"))

        for relation, key in _RELATION_ENTITY_KEY.items():
            n_rows = scalar(f"SELECT count(*) FROM {relation}")  # noqa: S608
            checks.append(
                Check(
                    f"{relation} rows",
                    n_rows > 0,
                    f"{n_rows} rows" if n_rows else "0 rows -- run `mlb build`",
                )
            )
            if not n_rows:
                continue

            dupes = scalar(  # noqa: S608 -- relation/key are module constants
                f"SELECT count(*) FROM (SELECT {key}, event_ts, feature_version "
                f"FROM {relation} GROUP BY 1, 2, 3 HAVING count(*) > 1)"
            )
            checks.append(
                Check(
                    f"{relation} grain",
                    dupes == 0,
                    "unique (entity, event_ts, feature_version)"
                    if dupes == 0
                    else f"{dupes} duplicated keys",
                )
            )

            bad_clock = scalar(  # noqa: S608
                f"SELECT count(*) FROM {relation} "
                "WHERE NOT (event_ts <= available_ts AND available_ts <= visible_ts)"
            )
            checks.append(
                Check(
                    f"{relation} clocks",
                    bad_clock == 0,
                    "event_ts <= available_ts <= visible_ts"
                    if bad_clock == 0
                    else f"{bad_clock} rows out of order",
                )
            )

        for relation, pairs in _RATE_DENOM_CHECKS.items():
            for rate_col, denom_col in pairs:
                mismatch = scalar(  # noqa: S608 -- columns are module constants
                    f"SELECT count(*) FROM {relation} "
                    f"WHERE ({denom_col} = 0) <> ({rate_col} IS NULL)"
                )
                checks.append(
                    Check(
                        f"{relation}.{rate_col} null-iff-empty",
                        mismatch == 0,
                        "NULL exactly when denominator 0"
                        if mismatch == 0
                        else f"{mismatch} rows violate it",
                    )
                )
    finally:
        con.close()
    return checks
