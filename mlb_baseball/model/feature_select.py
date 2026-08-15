"""Feature selection stability reporting (filter + embedded stages).

Computes a per-fold, per-candidate-feature stability report (filter + embedded
stages only); does not select or promote features, does not change what any
model trains on, does not implement the stepwise wrapper.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
from sklearn.inspection import permutation_importance

from mlb_baseball.health import Check, check_table_exists
from mlb_baseball.model.experiment import (
    BASE_COLUMNS,
    DEFAULT_FOLD_YEARS,
    TARGET_REGISTRY,
    ExperimentError,
    _canonical_json,
    _common_rows,
    _labels,
    _make_estimator,
    _matrix,
    _sha256,
    _snapshot_metadata,
    _snapshot_rows,
    folds,
)


def _selection_id(
    snapshot_id: str,
    target: str,
    fold_plan: list[dict[str, Any]],
    n_repeats: int,
    seed: int,
) -> str:
    identity = {
        "snapshot_id": snapshot_id,
        "target": target,
        "fold_plan": fold_plan,
        "n_repeats": n_repeats,
        "seed": seed,
    }
    return f"fsel-{_sha256(_canonical_json(identity))[:24]}"


def _write_selection_artifact(
    artifact_dir: Path, selection_id: str, payload: dict[str, Any]
) -> tuple[str, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    content = _canonical_json(payload) + "\n"
    digest = _sha256(content)
    path = artifact_dir / f"{digest}.json"
    if not path.exists():
        path.write_text(content)
    return str(path), digest


def select_features(
    conn: psycopg.Connection,
    snapshot_id: str,
    *,
    n_repeats: int = 30,
    seed: int = 0,
    fold_years: tuple[int, ...] = DEFAULT_FOLD_YEARS,
    artifact_dir: Path = Path("artifacts/feature_selection"),
) -> dict[str, Any]:
    """Compute and persist a reproducible feature-selection stability report."""
    target, _feature_set_version, _source_profile = _snapshot_metadata(conn, snapshot_id)
    if target not in TARGET_REGISTRY:
        raise ExperimentError(f"unsupported target {target!r}")
    spec = TARGET_REGISTRY[target]

    all_rows = _snapshot_rows(conn, snapshot_id)
    eligible = _common_rows(all_rows, spec)

    fold_plan = [asdict(fold) for fold in folds(fold_years)]
    selection_id = _selection_id(snapshot_id, target, fold_plan, n_repeats, seed)

    method_config = {
        "n_repeats": n_repeats,
        "seed": seed,
        "noise_column": "__noise__",
        "stage1_estimator": "logistic" if spec.task_type == "classification" else "ridge",
        "stage2_estimator": (
            "xgboost" if spec.task_type == "classification" else "xgboost_regressor"
        ),
        "scoring": (
            "neg_log_loss" if spec.task_type == "classification" else "neg_mean_absolute_error"
        ),
    }

    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, result_json FROM meta.feature_selection WHERE selection_id = %s",
            (selection_id,),
        )
        existing = cur.fetchone()
        if existing is not None and existing[0] == "success":
            res = existing[1] if isinstance(existing[1], dict) else json.loads(existing[1])
            return res | {"reused": True}
        if existing is not None:
            cur.execute(
                "UPDATE meta.feature_selection SET status = 'running', error = NULL, "
                "finished_at = NULL WHERE selection_id = %s",
                (selection_id,),
            )
        else:
            cur.execute(
                """
                INSERT INTO meta.feature_selection (
                    selection_id, snapshot_id, target, fold_plan_json, method_config_json,
                    status
                ) VALUES (%s, %s, %s, %s, %s, 'running')
                """,
                (
                    selection_id,
                    snapshot_id,
                    target,
                    json.dumps(fold_plan),
                    json.dumps(method_config),
                ),
            )

    fold_results: dict[str, Any] = {}
    stage1_counts = {feature: 0 for feature in BASE_COLUMNS}
    stage2_counts = {feature: 0 for feature in BASE_COLUMNS}
    both_counts = {feature: 0 for feature in BASE_COLUMNS}
    stage1_by_fold: dict[str, dict[str, bool]] = {feature: {} for feature in BASE_COLUMNS}
    stage2_by_fold: dict[str, dict[str, bool]] = {feature: {} for feature in BASE_COLUMNS}
    both_by_fold: dict[str, dict[str, bool]] = {feature: {} for feature in BASE_COLUMNS}
    evaluated_folds_count = 0

    try:
        for fold in folds(fold_years):
            train_rows = [row for row in eligible if row.season <= fold.train_through_season]
            if not train_rows:
                fold_results[fold.name] = {
                    "train_rows": 0,
                    "skipped": True,
                    "reason": "no training rows",
                }
                continue

            evaluated_folds_count += 1
            base_matrix = _matrix(train_rows)
            rng = np.random.default_rng(seed + fold.test_season)
            noise = rng.standard_normal(len(train_rows))
            augmented = np.column_stack([base_matrix, noise])
            augmented_columns = list(BASE_COLUMNS) + ["__noise__"]
            labels = _labels(train_rows, spec)

            # Stage 1: filter (permutation importance on linear baseline)
            estimator1 = _make_estimator(str(method_config["stage1_estimator"]), {}, seed)
            estimator1.fit(augmented, labels)
            perm_result = permutation_importance(
                estimator1,
                augmented,
                labels,
                scoring=str(method_config["scoring"]),
                n_repeats=n_repeats,
                random_state=seed + fold.test_season,
            )
            importances1: dict[str, float] = dict(
                zip(
                    augmented_columns,
                    [float(v) for v in perm_result.importances_mean],
                    strict=True,
                )
            )
            noise_importance1 = importances1["__noise__"]

            # Stage 2: embedded (tree importance on XGBoost)
            estimator2 = _make_estimator(str(method_config["stage2_estimator"]), {}, seed)
            estimator2.fit(augmented, labels)
            raw_feat_imp = estimator2.feature_importances_
            importances2: dict[str, float] = dict(
                zip(
                    augmented_columns,
                    [float(v) for v in raw_feat_imp],
                    strict=True,
                )
            )
            noise_importance2 = importances2["__noise__"]

            stage1_survived = [col for col in BASE_COLUMNS if importances1[col] > noise_importance1]
            stage2_survived = [col for col in BASE_COLUMNS if importances2[col] > noise_importance2]
            both_survived = [
                col
                for col in BASE_COLUMNS
                if col in stage1_survived and col in stage2_survived
            ]

            for col in BASE_COLUMNS:
                s1 = col in stage1_survived
                s2 = col in stage2_survived
                b = s1 and s2
                if s1:
                    stage1_counts[col] += 1
                if s2:
                    stage2_counts[col] += 1
                if b:
                    both_counts[col] += 1
                stage1_by_fold[col][fold.name] = s1
                stage2_by_fold[col][fold.name] = s2
                both_by_fold[col][fold.name] = b

            fold_results[fold.name] = {
                "train_rows": len(train_rows),
                "skipped": False,
                "noise_importance_stage1": noise_importance1,
                "noise_importance_stage2": noise_importance2,
                "stage1_importances": importances1,
                "stage2_importances": importances2,
                "stage1_survived": stage1_survived,
                "stage2_survived": stage2_survived,
                "both_survived": both_survived,
            }

        features_summary = {
            col: {
                "stage1_survived_folds": stage1_counts[col],
                "stage2_survived_folds": stage2_counts[col],
                "both_stages_survived_folds": both_counts[col],
                "stage1_by_fold": stage1_by_fold[col],
                "stage2_by_fold": stage2_by_fold[col],
                "both_by_fold": both_by_fold[col],
            }
            for col in BASE_COLUMNS
        }

        result_payload: dict[str, Any] = {
            "selection_id": selection_id,
            "snapshot_id": snapshot_id,
            "target": target,
            "status": "success",
            "method_config": method_config,
            "total_folds_evaluated": evaluated_folds_count,
            "features": features_summary,
            "folds": fold_results,
        }

        artifact_uri, artifact_sha = _write_selection_artifact(
            artifact_dir,
            selection_id,
            result_payload,
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE meta.feature_selection
                SET status = 'success',
                    error = NULL,
                    result_json = %s,
                    artifact_uri = %s,
                    artifact_sha256 = %s,
                    finished_at = now()
                WHERE selection_id = %s
                """,
                (
                    json.dumps(result_payload),
                    artifact_uri,
                    artifact_sha,
                    selection_id,
                ),
            )

        return result_payload | {"reused": False}

    except Exception as error:
        conn.rollback()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO meta.feature_selection (
                    selection_id, snapshot_id, target, fold_plan_json, method_config_json,
                    status, error, finished_at
                ) VALUES (%s, %s, %s, %s, %s, 'failed', %s, now())
                ON CONFLICT (selection_id) DO UPDATE SET
                    status = 'failed', error = EXCLUDED.error, finished_at = EXCLUDED.finished_at
                """,
                (
                    selection_id,
                    snapshot_id,
                    target,
                    json.dumps(fold_plan),
                    json.dumps(method_config),
                    str(error),
                ),
            )
        raise


def health_check() -> list[Check]:
    return [
        check_table_exists("meta.feature_selection"),
    ]
