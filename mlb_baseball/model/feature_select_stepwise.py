"""Forward-stepwise feature selection with nested chronological validation.

Implements Stage 3 of feature selection: derives candidate features from
the Stage 1/2 stability report, runs forward-stepwise search with nested
chronological inner train/validate splits (train on seasons <= T-2, validate
on season T-1) inside each outer fold, using paired real-vs-shuffled
comparisons as the sole selection threshold.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
from sklearn.metrics import log_loss, mean_absolute_error

from mlb_baseball.health import Check, check_table_exists
from mlb_baseball.model.experiment import (
    BASE_COLUMNS,
    DEFAULT_FOLD_YEARS,
    TARGET_REGISTRY,
    ExperimentError,
    SnapshotRow,
    _canonical_json,
    _common_rows,
    _finalize_failed_run,
    _labels,
    _make_estimator,
    _sha256,
    _snapshot_metadata,
    _snapshot_rows,
    folds,
)
from mlb_baseball.model.feature_select import (
    _write_selection_artifact,
    select_features,
)


def _named_matrix(
    rows: Sequence[SnapshotRow], feature_names: Sequence[str]
) -> np.ndarray:
    """Build a 2D float matrix of named feature values for the given rows."""
    if not feature_names:
        return np.empty((len(rows), 0), dtype=np.float64)
    return np.array(
        [
            [np.nan if row.values.get(name) is None else row.values[name] for name in feature_names]
            for row in rows
        ],
        dtype=np.float64,
    )


def _selection_id(
    snapshot_id: str,
    target: str,
    fold_plan: list[dict[str, Any]],
    min_survival_fraction: float,
    seed: int,
) -> str:
    identity = {
        "snapshot_id": snapshot_id,
        "target": target,
        "fold_plan": fold_plan,
        "min_survival_fraction": min_survival_fraction,
        "seed": seed,
    }
    return f"fstep-{_sha256(_canonical_json(identity))[:24]}"


def select_features_stepwise(
    conn: psycopg.Connection,
    snapshot_id: str,
    *,
    seed: int = 0,
    fold_years: tuple[int, ...] = DEFAULT_FOLD_YEARS,
    min_survival_fraction: float = 0.70,
    artifact_dir: Path = Path("artifacts/feature_selection_stepwise"),
) -> dict[str, Any]:
    """Derive stage-1/2 candidates and run nested forward-stepwise selection."""
    target, _feature_set_version, _source_profile = _snapshot_metadata(conn, snapshot_id)
    if target not in TARGET_REGISTRY:
        raise ExperimentError(f"unsupported target {target!r}")
    spec = TARGET_REGISTRY[target]

    # 1. Obtain stage 1/2 stability report (idempotent call)
    stage12_report = select_features(
        conn,
        snapshot_id,
        seed=seed,
        fold_years=fold_years,
    )

    total_s12_evaluated = stage12_report["total_folds_evaluated"]
    if total_s12_evaluated == 0:
        threshold_pct = int(min_survival_fraction * 100)
        raise ExperimentError(
            f"no candidate features survived stage 1+2 at the {threshold_pct}th-percent "
            "threshold; nothing to search over (0 folds evaluated in stage 1/2)"
        )

    # 2. Derive candidate set (features surviving both stages >= min_survival_fraction)
    candidates = [
        col
        for col in BASE_COLUMNS
        if (
            stage12_report["features"][col]["both_stages_survived_folds"]
            / total_s12_evaluated
        )
        >= min_survival_fraction
    ]

    if not candidates:
        threshold_pct = int(min_survival_fraction * 100)
        raise ExperimentError(
            f"no candidate features survived stage 1+2 at the {threshold_pct}th-percent threshold; "
            "nothing to search over"
        )

    all_rows = _snapshot_rows(conn, snapshot_id)
    eligible = _common_rows(all_rows, spec)

    fold_plan = [asdict(fold) for fold in folds(fold_years)]
    selection_id = _selection_id(snapshot_id, target, fold_plan, min_survival_fraction, seed)

    probe_estimator_name = "logistic" if spec.task_type == "classification" else "ridge"
    scoring_metric = "log_loss" if spec.task_type == "classification" else "mae"

    method_config = {
        "seed": seed,
        "min_survival_fraction": min_survival_fraction,
        "stage1_2_selection_id": stage12_report["selection_id"],
        "candidate_features": candidates,
        "probe_estimator": probe_estimator_name,
        "scoring": scoring_metric,
    }

    # 3. Check for existing completed run
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, result_json FROM meta.feature_selection_stepwise "
            "WHERE selection_id = %s",
            (selection_id,),
        )
        existing = cur.fetchone()
        if existing is not None and existing[0] == "success":
            res = existing[1] if isinstance(existing[1], dict) else json.loads(existing[1])
            return res | {"reused": True}
        if existing is not None:
            cur.execute(
                "UPDATE meta.feature_selection_stepwise SET status = 'running', error = NULL, "
                "finished_at = NULL WHERE selection_id = %s",
                (selection_id,),
            )
        else:
            cur.execute(
                """
                INSERT INTO meta.feature_selection_stepwise (
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
    evaluated_folds_count = 0

    try:
        for fold in folds(fold_years):
            # Outer train rows: seasons <= fold.train_through_season (T - 1)
            outer_train_rows = [row for row in eligible if row.season <= fold.train_through_season]

            # Inner chronological split:
            # inner train: seasons <= fold.train_through_season - 1 (<= T - 2)
            # inner validate: season == fold.train_through_season (== T - 1)
            inner_train_rows = [
                row for row in outer_train_rows if row.season <= fold.train_through_season - 1
            ]
            inner_validate_rows = [
                row for row in outer_train_rows if row.season == fold.train_through_season
            ]

            if not inner_train_rows or not inner_validate_rows:
                fold_results[fold.name] = {
                    "train_rows": len(inner_train_rows),
                    "validate_rows": len(inner_validate_rows),
                    "skipped": True,
                    "reason": "insufficient inner-split data",
                    "selected": [],
                    "trace": [],
                }
                continue

            if (
                spec.task_type == "classification"
                and len(set(_labels(inner_train_rows, spec).tolist())) < 2
            ):
                fold_results[fold.name] = {
                    "train_rows": len(inner_train_rows),
                    "validate_rows": len(inner_validate_rows),
                    "skipped": True,
                    "reason": "single-class inner-training split",
                    "selected": [],
                    "trace": [],
                }
                continue

            evaluated_folds_count += 1
            y_inner_train = _labels(inner_train_rows, spec)
            y_inner_validate = _labels(inner_validate_rows, spec)

            selected: list[str] = []
            remaining = [col for col in BASE_COLUMNS if col in candidates]
            trace: list[dict[str, Any]] = []
            step_num = 1

            while remaining:
                step_candidates: list[dict[str, Any]] = []

                for candidate in remaining:
                    tested_features = selected + [candidate]
                    x_train_real = _named_matrix(inner_train_rows, tested_features)
                    x_val_real = _named_matrix(inner_validate_rows, tested_features)

                    # Real feature fit and evaluation
                    est_real = _make_estimator(probe_estimator_name, {}, seed)
                    est_real.fit(x_train_real, y_inner_train)

                    if spec.task_type == "classification":
                        probs_real = est_real.predict_proba(x_val_real)[:, 1]
                        real_score = float(log_loss(y_inner_validate, probs_real, labels=[0, 1]))
                    else:
                        preds_real = est_real.predict(x_val_real)
                        real_score = float(mean_absolute_error(y_inner_validate, preds_real))

                    # Shuffled variant: candidate column permuted in training matrix
                    seed_digest = _sha256(f"{seed}:{fold.test_season}:{len(selected)}:{candidate}")
                    step_seed = int(seed_digest[:15], 16)
                    rng = np.random.default_rng(step_seed)

                    x_train_shuffled = x_train_real.copy()
                    x_train_shuffled[:, -1] = rng.permutation(x_train_shuffled[:, -1])

                    est_shuffled = _make_estimator(probe_estimator_name, {}, seed)
                    est_shuffled.fit(x_train_shuffled, y_inner_train)

                    if spec.task_type == "classification":
                        probs_shuffled = est_shuffled.predict_proba(x_val_real)[:, 1]
                        shuffled_score = float(
                            log_loss(y_inner_validate, probs_shuffled, labels=[0, 1])
                        )
                    else:
                        preds_shuffled = est_shuffled.predict(x_val_real)
                        shuffled_score = float(
                            mean_absolute_error(y_inner_validate, preds_shuffled)
                        )

                    # Margin: positive indicates real score is lower (better) than shuffled
                    margin = shuffled_score - real_score
                    passed = real_score < shuffled_score

                    step_candidates.append(
                        {
                            "candidate": candidate,
                            "real_score": real_score,
                            "shuffled_score": shuffled_score,
                            "margin": margin,
                            "passed": passed,
                        }
                    )

                passing_candidates = [sc for sc in step_candidates if sc["passed"]]

                if not passing_candidates:
                    # No candidate passed the paired shuffled-control comparison; stop
                    for sc in step_candidates:
                        sc["added"] = False
                    trace.append(
                        {
                            "step": step_num,
                            "selected_before": list(selected),
                            "candidates": step_candidates,
                            "winner": None,
                        }
                    )
                    break

                # Pick passing candidate with largest margin (most improvement)
                winner_entry = max(passing_candidates, key=lambda sc: sc["margin"])
                winner = str(winner_entry["candidate"])

                for sc in step_candidates:
                    sc["added"] = sc["candidate"] == winner

                trace.append(
                    {
                        "step": step_num,
                        "selected_before": list(selected),
                        "candidates": step_candidates,
                        "winner": winner,
                    }
                )

                selected.append(winner)
                remaining.remove(winner)
                step_num += 1

            fold_results[fold.name] = {
                "train_rows": len(inner_train_rows),
                "validate_rows": len(inner_validate_rows),
                "skipped": False,
                "selected": selected,
                "trace": trace,
            }

        # Stability summary across evaluated folds
        selected_counts = {col: 0 for col in candidates}
        selected_by_fold: dict[str, dict[str, bool]] = {col: {} for col in candidates}

        for col in candidates:
            for fold_name, fold_data in fold_results.items():
                if fold_data.get("skipped"):
                    selected_by_fold[col][fold_name] = False
                else:
                    was_selected = col in fold_data.get("selected", [])
                    selected_by_fold[col][fold_name] = was_selected
                    if was_selected:
                        selected_counts[col] += 1

        features_summary = {
            col: {
                "selected_folds": selected_counts[col],
                "selected_by_fold": selected_by_fold[col],
                "selection_fraction": (
                    selected_counts[col] / evaluated_folds_count
                    if evaluated_folds_count > 0
                    else 0.0
                ),
            }
            for col in candidates
        }

        result_payload: dict[str, Any] = {
            "selection_id": selection_id,
            "snapshot_id": snapshot_id,
            "target": target,
            "status": "success",
            "method_config": method_config,
            "candidate_features": candidates,
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
                UPDATE meta.feature_selection_stepwise
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
        _finalize_failed_run(
            conn,
            """
            INSERT INTO meta.feature_selection_stepwise (
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
        check_table_exists("meta.feature_selection_stepwise"),
    ]
