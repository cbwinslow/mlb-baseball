"""Immutable model registry and model-run bookkeeping."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

import psycopg

from mlb_baseball.db import fetch_one


def artifact_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_sha() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def feature_snapshot(
    conn: psycopg.Connection, *, where: str = "TRUE"
) -> tuple[datetime | None, str]:
    """Return the best available identity for the feature rows a run read.

    ``gold.game_feature`` is rebuilt in place and has no snapshot table yet.
    Until the planned immutable feature store exists, its row count, latest
    feature build timestamp, and latest game date are the honest, inspectable
    identity.  The timestamp is also the only defensible data-availability
    cutoff this table can currently provide.
    """
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*), max(_built_at), max(game_date) FROM gold.game_feature WHERE {where}"
        )
        row_count, built_at, latest_game_date = fetch_one(cur)
    identity = {
        "feature_set_version": "game-feature-v1",
        "row_count": row_count,
        "built_at": built_at.isoformat() if built_at else None,
        "latest_game_date": latest_game_date.isoformat() if latest_game_date else None,
        "selection": where,
    }
    snapshot_id = (
        "game-feature-v1:"
        f"rows={row_count}:built_at={built_at.isoformat() if built_at else 'none'}:"
        f"latest_game_date={latest_game_date.isoformat() if latest_game_date else 'none'}:"
        f"selection={hashlib.sha256(where.encode()).hexdigest()[:12]}"
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta.feature_snapshot (
                feature_snapshot_id, feature_set_version, data_cutoff, row_count,
                latest_game_date, built_at, identity_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (feature_snapshot_id) DO NOTHING
            """,
            (
                snapshot_id,
                "game-feature-v1",
                built_at,
                row_count,
                latest_game_date,
                built_at,
                json.dumps(identity),
            ),
        )
    return built_at, snapshot_id


def record_evaluation(
    conn: psycopg.Connection,
    *,
    run_id: int,
    model_versions: list[str],
    season: int,
    prediction_cutoff: str,
    common_games: int,
    coverage: Mapping,
    metrics: Mapping,
) -> int:
    """Persist one immutable result payload for an evaluation run."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta.model_evaluation (
                run_id, model_versions, season, prediction_cutoff, common_games,
                coverage_json, metrics_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING evaluation_id
            """,
            (
                run_id,
                json.dumps(model_versions),
                season,
                prediction_cutoff,
                common_games,
                json.dumps(dict(coverage)),
                json.dumps(dict(metrics)),
            ),
        )
        return int(fetch_one(cur)[0])


def register_model(
    conn: psycopg.Connection,
    *,
    name: str,
    target: str,
    model_version: str,
    feature_set_version: str,
    status: str,
    artifact_path: Path | None = None,
    parameters: Mapping | None = None,
    metrics: Mapping | None = None,
) -> str:
    """Register a content-addressed artifact or deterministic baseline."""
    sha256 = artifact_sha256(artifact_path) if artifact_path else None
    identity = (
        sha256
        or hashlib.sha256(f"{name}:{model_version}:{feature_set_version}".encode()).hexdigest()
    )
    model_id = f"{model_version}-{identity[:16]}"
    with conn.cursor() as cur:
        if status == "champion":
            cur.execute(
                "UPDATE meta.model SET status = 'retired' "
                "WHERE name = %s AND status = 'champion' AND model_id <> %s",
                (name, model_id),
            )
        cur.execute(
            """
            INSERT INTO meta.model (
                model_id, name, target, model_version, artifact_uri,
                artifact_sha256, git_sha, feature_set_version,
                parameters_json, metrics_json, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (model_id) DO UPDATE SET
                metrics_json = EXCLUDED.metrics_json,
                status = CASE
                    WHEN meta.model.status = 'champion' AND EXCLUDED.status = 'candidate'
                    THEN meta.model.status
                    ELSE EXCLUDED.status
                END
            """,
            (
                model_id,
                name,
                target,
                model_version,
                str(artifact_path) if artifact_path else None,
                sha256,
                git_sha(),
                feature_set_version,
                json.dumps(dict(parameters or {})),
                json.dumps(dict(metrics or {})),
                status,
            ),
        )
    return model_id


def start_run(
    conn: psycopg.Connection,
    *,
    run_type: str,
    model_id: str | None = None,
    data_cutoff=None,
    source_snapshot: str | None = None,
    prediction_cutoff: str | None = None,
    feature_snapshot_id: str | None = None,
) -> int:
    """Commits the new meta.model_run row immediately, independently of
    whatever transaction the caller's own real work (train/predict/
    evaluate) uses -- same reasoning as ingest.py's track_run (ADR-022).
    Every caller (elo.py, log5.py, gbm.py, evaluation.py) calls this, then
    does its real work, then calls finish_run() -- none of them commit in
    between. Without committing here, a later failure that aborts the
    transaction would roll this INSERT away along with the failed work,
    so finish_run()'s own rollback-then-UPDATE (see its docstring) would
    silently match zero rows: no failure ever gets recorded, the exact
    thing that fix exists to guarantee (PR review, CodeAnt)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta.model_run (
                model_id, run_type, data_cutoff, source_snapshot, prediction_cutoff,
                feature_snapshot_id, status
            ) VALUES (%s, %s, %s, %s, %s, %s, 'running')
            RETURNING run_id
            """,
            (
                model_id,
                run_type,
                data_cutoff,
                source_snapshot,
                prediction_cutoff,
                feature_snapshot_id,
            ),
        )
        run_id = int(fetch_one(cur)[0])
    conn.commit()
    return run_id


def finish_run(conn: psycopg.Connection, run_id: int, *, error: Exception | None = None) -> None:
    """Same rollback-before-logging-a-failure fix as ingest.py's track_run
    (see its own docstring/ADR-022 precedent): the caller's failed
    operation typically leaves `conn` in InFailedSqlTransaction state, and
    without rolling back first, this UPDATE itself would raise
    InFailedSqlTransaction instead of ever recording the real error --
    only on the failure path, never on success, where rolling back would
    discard the very work this call is meant to commit.

    Commits the UPDATE itself on both paths (PR review, Kilo -- a real,
    confirmed bug missed by this module's own tests but not by real
    usage): every real caller (log5.py/elo.py/gbm.py) re-raises after
    calling this on the failure path, and predict()/train() are always
    invoked from model/__init__.py's run(), inside track_run()'s own
    context manager (ingest.py). track_run's own except-block does a
    *second* conn.rollback() when that re-raised exception reaches it --
    which would silently wipe out this UPDATE if it were left
    uncommitted, discarding the very failure record this whole fix chain
    exists to guarantee."""
    if error:
        conn.rollback()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE meta.model_run
            SET status = %s, error = %s, finished_at = now()
            WHERE run_id = %s
            """,
            ("failed" if error else "success", str(error) if error else None, run_id),
        )
    conn.commit()
