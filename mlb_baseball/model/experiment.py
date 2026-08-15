"""Reproducible, point-in-time machine-learning experiment lab.

Target-agnostic experiment harness supporting classification (home_win) and
regression (run_differential) across calendar folds. Provides transparent
baselines through full estimator families, immutable snapshots, and full
evidence-trail persistence. Anchors downstream feature-selection pipelines.
This is intentionally a focused lab, not a generic AutoML framework.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from random import Random
from typing import Any, Literal

import numpy as np
import psycopg
import xgboost as xgb
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    root_mean_squared_error,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_table_exists
from mlb_baseball.model import elo, log5, provenance
from mlb_baseball.sql import read_sql

FEATURE_SET_VERSION = "game_base_v1"
TARGET = "home_win"
SOURCE_PROFILE = "local_research"
BASE_COLUMNS = (
    "home_wins",
    "home_losses",
    "away_wins",
    "away_losses",
    "home_runs_for",
    "home_runs_allowed",
    "away_runs_for",
    "away_runs_allowed",
    "home_rest",
    "away_rest",
    "home_field",
)
LOG5_COLUMNS = ("home_win_pct", "away_win_pct")
ALL_COLUMNS = BASE_COLUMNS + LOG5_COLUMNS
DEFAULT_FOLD_YEARS = tuple(range(2016, 2025))
SUPPORTED_MODELS = (
    "home_rate",
    "log5",
    "elo",
    "logistic",
    "hist_gradient_boosting",
    "xgboost",
)
_SELECTION_SQL = read_sql("experiment_selection.sql")


class ExperimentError(ValueError):
    """A declared experiment cannot safely run."""


@dataclass(frozen=True)
class Fold:
    name: str
    train_through_season: int
    test_season: int


@dataclass(frozen=True)
class ExperimentConfig:
    snapshot_id: str
    model_family: str
    fold_years: tuple[int, ...] = DEFAULT_FOLD_YEARS
    parameters: dict[str, Any] | None = None
    seed: int = 0
    calibration: str = "none"
    source_profile: str = SOURCE_PROFILE
    artifact_dir: Path = Path("artifacts/experiments")
    target: str = TARGET
    feature_set_version: str = FEATURE_SET_VERSION


@dataclass(frozen=True)
class SnapshotRow:
    game_instance_key: str
    mlb_game_pk: str
    feature_cutoff_at: datetime
    season: int
    game_date: date
    game_number: int | None
    home_team_id: int
    away_team_id: int
    home_score: int
    away_score: int
    values: dict[str, float | None]
    home_win: bool


@dataclass(frozen=True)
class TargetSpec:
    name: str
    task_type: Literal["classification", "regression"]
    label: Callable[[SnapshotRow], float]
    required_columns: tuple[str, ...]
    valid_model_families: tuple[str, ...]


TARGET_REGISTRY: dict[str, TargetSpec] = {
    "home_win": TargetSpec(
        name="home_win",
        task_type="classification",
        label=lambda row: float(row.home_win),
        required_columns=("home_win_pct", "away_win_pct"),
        valid_model_families=(
            "home_rate",
            "log5",
            "elo",
            "logistic",
            "hist_gradient_boosting",
            "xgboost",
        ),
    ),
    "run_differential": TargetSpec(
        name="run_differential",
        task_type="regression",
        label=lambda row: float(row.home_score - row.away_score),
        required_columns=(
            "home_runs_for",
            "home_runs_allowed",
            "away_runs_for",
            "away_runs_allowed",
            "home_wins",
            "home_losses",
            "away_wins",
            "away_losses",
        ),
        valid_model_families=(
            "zero",
            "season_average",
            "ridge",
            "hist_gradient_boosting_regressor",
            "xgboost_regressor",
        ),
    ),
}

ALL_MODEL_FAMILIES: tuple[str, ...] = tuple(
    dict.fromkeys(
        model
        for spec in TARGET_REGISTRY.values()
        for model in spec.valid_model_families
    )
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: bytes | str) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def _lock_sha256() -> str | None:
    lock = Path("uv.lock")
    return _sha256(lock.read_bytes()) if lock.exists() else None


def _environment() -> dict[str, str | None]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "uv_lock_sha256": _lock_sha256(),
    }


def _feature_schema() -> dict[str, str]:
    return {column: "number_or_null" for column in ALL_COLUMNS}


def _source_rows(conn: psycopg.Connection) -> list[SnapshotRow]:
    with conn.cursor() as cur:
        cur.execute(_SELECTION_SQL)
        rows = cur.fetchall()
    result: list[SnapshotRow] = []
    seen_keys: set[str] = set()
    seen_game_pks: set[str] = set()
    for row in rows:
        (
            instance_key,
            game_pk,
            cutoff,
            season,
            game_date,
            game_number,
            home_team_id,
            away_team_id,
            home_win,
            home_score,
            away_score,
            *values,
        ) = row
        if instance_key in seen_keys:
            raise ExperimentError(f"duplicate game_instance_key in feature source: {instance_key}")
        seen_keys.add(str(instance_key))
        if game_pk in seen_game_pks:
            raise ExperimentError(f"duplicate mlb_game_pk in feature source: {game_pk}")
        seen_game_pks.add(str(game_pk))
        if (
            cutoff is None
            or game_pk is None
            or home_win is None
            or home_team_id is None
            or away_team_id is None
            or home_score is None
            or away_score is None
        ):
            raise ExperimentError(
                "experiment source contains a missing required point-in-time identity"
            )
        result.append(
            SnapshotRow(
                str(instance_key),
                str(game_pk),
                cutoff,
                int(season),
                game_date,
                int(game_number) if game_number is not None else None,
                int(home_team_id),
                int(away_team_id),
                int(home_score),
                int(away_score),
                {
                    column: float(value) if value is not None else None
                    for column, value in zip(ALL_COLUMNS, values, strict=True)
                },
                bool(home_win),
            )
        )
    if not result:
        raise ExperimentError("no resolved game-win rows available for an experiment snapshot")
    return result


def _row_identity(rows: Iterable[SnapshotRow]) -> str:
    payload = [
        {
            "game_instance_key": row.game_instance_key,
            "mlb_game_pk": row.mlb_game_pk,
            "feature_cutoff_at": row.feature_cutoff_at.isoformat(),
            "season": row.season,
            "game_date": row.game_date.isoformat(),
            "game_number": row.game_number,
            "home_team_id": row.home_team_id,
            "away_team_id": row.away_team_id,
            "home_score": row.home_score,
            "away_score": row.away_score,
            "values": row.values,
            "home_win": row.home_win,
        }
        for row in rows
    ]
    return _sha256(_canonical_json(payload))


def create_snapshot(
    conn: psycopg.Connection,
    *,
    target: str = TARGET,
    source_profile: str = SOURCE_PROFILE,
) -> str:
    """Copy the approved PIT rows into an immutable, content-addressed snapshot."""
    if target not in TARGET_REGISTRY:
        raise ExperimentError(f"unsupported target {target!r}")
    rows = _source_rows(conn)
    row_sha = _row_identity(rows)
    snapshot_id = f"{FEATURE_SET_VERSION}:{target}:{row_sha[:24]}"
    selection_sha = _sha256(_SELECTION_SQL)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT snapshot_id FROM meta.experiment_snapshot "
            "WHERE row_sha256 = %s AND target = %s",
            (row_sha, target),
        )
        existing = cur.fetchone()
        if existing is not None:
            return str(existing[0])
        cur.execute("SELECT max(_built_at) FROM gold.game_feature")
        (watermark,) = fetch_one(cur)
        cur.execute(
            """
            INSERT INTO meta.experiment_snapshot (
                snapshot_id, feature_set_version, target, source_profile, selection_sql,
                selection_sha256, row_sha256, source_watermark, row_count, feature_columns,
                schema_json, environment_json, git_sha
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot_id,
                FEATURE_SET_VERSION,
                target,
                source_profile,
                _SELECTION_SQL,
                selection_sha,
                row_sha,
                watermark,
                len(rows),
                json.dumps(list(ALL_COLUMNS)),
                json.dumps(_feature_schema()),
                json.dumps(_environment()),
                provenance.git_sha(),
            ),
        )
        cur.executemany(
            """
            INSERT INTO gold.game_feature_snapshot (
                snapshot_id, game_instance_key, mlb_game_pk, feature_cutoff_at,
                season, game_date, game_number, home_team_id, away_team_id,
                home_score, away_score, feature_json, home_win
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    snapshot_id,
                    row.game_instance_key,
                    row.mlb_game_pk,
                    row.feature_cutoff_at,
                    row.season,
                    row.game_date,
                    row.game_number,
                    row.home_team_id,
                    row.away_team_id,
                    row.home_score,
                    row.away_score,
                    json.dumps(row.values),
                    row.home_win,
                )
                for row in rows
            ],
        )
    return snapshot_id


def _snapshot_rows(conn: psycopg.Connection, snapshot_id: str) -> list[SnapshotRow]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT game_instance_key, mlb_game_pk, feature_cutoff_at, season, game_date,
                   game_number, home_team_id, away_team_id, home_score, away_score,
                   feature_json, home_win
            FROM gold.game_feature_snapshot
            WHERE snapshot_id = %s
            ORDER BY feature_cutoff_at, game_number NULLS LAST, mlb_game_pk, game_instance_key
            """,
            (snapshot_id,),
        )
        rows = cur.fetchall()
    if not rows:
        raise ExperimentError(f"snapshot {snapshot_id!r} does not exist or contains no rows")
    return [
        SnapshotRow(
            str(key),
            str(pk),
            cutoff,
            int(season),
            game_date,
            int(number) if number is not None else None,
            int(home_team),
            int(away_team),
            int(home_score),
            int(away_score),
            {name: float(value) if value is not None else None for name, value in values.items()},
            bool(outcome),
        )
        for (
            key,
            pk,
            cutoff,
            season,
            game_date,
            number,
            home_team,
            away_team,
            home_score,
            away_score,
            values,
            outcome,
        ) in rows
    ]


def folds(fold_years: Sequence[int]) -> tuple[Fold, ...]:
    years = tuple(fold_years)
    if not years or tuple(sorted(set(years))) != years:
        raise ExperimentError("fold years must be unique, sorted calendar years")
    return tuple(Fold(f"season-{year}", year - 1, year) for year in years)


def _common_rows(
    rows: Sequence[SnapshotRow], spec: TargetSpec = TARGET_REGISTRY["home_win"]
) -> list[SnapshotRow]:
    # Common-sample scoring requires the declared target's non-null inputs.
    # Opening games remain in the immutable snapshot but are reported as
    # excluded, not silently filled with a made-up rate or value.
    return [
        row
        for row in rows
        if all(row.values.get(column) is not None for column in spec.required_columns)
    ]


def _matrix(rows: Sequence[SnapshotRow]) -> np.ndarray:
    return np.array(
        [
            [np.nan if row.values[name] is None else row.values[name] for name in BASE_COLUMNS]
            for row in rows
        ],
        dtype=np.float64,
    )


def _labels(
    rows: Sequence[SnapshotRow], spec: TargetSpec = TARGET_REGISTRY["home_win"]
) -> np.ndarray:
    if spec.task_type == "classification":
        return np.array([int(spec.label(row)) for row in rows], dtype=np.int64)
    return np.array([float(spec.label(row)) for row in rows], dtype=np.float64)


def _make_estimator(model_family: str, parameters: dict[str, Any], seed: int):
    if model_family == "logistic":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(max_iter=1_000, random_state=seed, **parameters)),
            ]
        )
    if model_family == "hist_gradient_boosting":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", HistGradientBoostingClassifier(random_state=seed, **parameters)),
            ]
        )
    if model_family == "xgboost":
        return xgb.XGBClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.05,
            eval_metric="logloss",
            random_state=seed,
            n_jobs=1,
            **parameters,
        )
    if model_family == "ridge":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", Ridge(random_state=seed, **parameters)),
            ]
        )
    if model_family == "hist_gradient_boosting_regressor":
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", HistGradientBoostingRegressor(random_state=seed, **parameters)),
            ]
        )
    if model_family == "xgboost_regressor":
        return xgb.XGBRegressor(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.05,
            eval_metric="rmse",
            random_state=seed,
            n_jobs=1,
            **parameters,
        )
    raise ExperimentError(f"unsupported estimator {model_family!r}")


def _validate_parameters(model_family: str, parameters: dict[str, Any]) -> None:
    """Reject ignored or misspelled estimator choices before a run is recorded."""
    if model_family in {"home_rate", "log5", "elo", "zero", "season_average"}:
        if parameters:
            raise ExperimentError(f"{model_family} accepts no estimator parameters")
        return
    if model_family == "logistic":
        allowed = LogisticRegression().get_params(deep=False)
    elif model_family == "hist_gradient_boosting":
        allowed = HistGradientBoostingClassifier().get_params(deep=False)
    elif model_family == "xgboost":
        allowed = xgb.XGBClassifier().get_params(deep=False)
    elif model_family == "ridge":
        allowed = Ridge().get_params(deep=False)
    elif model_family == "hist_gradient_boosting_regressor":
        allowed = HistGradientBoostingRegressor().get_params(deep=False)
    elif model_family == "xgboost_regressor":
        allowed = xgb.XGBRegressor().get_params(deep=False)
    else:
        raise ExperimentError(f"unsupported estimator {model_family!r}")
    unknown = sorted(set(parameters) - set(allowed))
    if unknown:
        raise ExperimentError(
            f"{model_family} has unsupported parameter(s): {', '.join(unknown)}"
        )


def _snapshot_metadata(conn: psycopg.Connection, snapshot_id: str) -> tuple[str, str, str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT target, feature_set_version, source_profile "
            "FROM meta.experiment_snapshot WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise ExperimentError(f"snapshot {snapshot_id!r} does not exist")
    return str(row[0]), str(row[1]), str(row[2])


def snapshot_integrity(conn: psycopg.Connection) -> dict[str, int]:
    """Check stored snapshot evidence without consulting mutable feature rows."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT snapshot_id, row_sha256, selection_sql, selection_sha256, row_count "
            "FROM meta.experiment_snapshot ORDER BY snapshot_id"
        )
        snapshots = cur.fetchall()
    row_hash_mismatches = 0
    selection_hash_mismatches = 0
    row_count_mismatches = 0
    for snapshot_id, expected_rows, selection_sql, expected_selection, expected_count in snapshots:
        rows = _snapshot_rows(conn, str(snapshot_id))
        row_hash_mismatches += _row_identity(rows) != str(expected_rows)
        selection_hash_mismatches += _sha256(str(selection_sql)) != str(expected_selection)
        row_count_mismatches += len(rows) != int(expected_count)
    return {
        "snapshots": len(snapshots),
        "row_hash_mismatches": row_hash_mismatches,
        "selection_hash_mismatches": selection_hash_mismatches,
        "row_count_mismatches": row_count_mismatches,
    }


def _elo_probabilities(rows: Sequence[SnapshotRow], test_rows: Sequence[SnapshotRow]) -> np.ndarray:
    """Walk prior outcomes and test games in cutoff order without future leakage."""
    test_keys = {row.game_instance_key for row in test_rows}
    ratings: dict[int, float] = {}
    rating_season: dict[int, int] = {}
    values: dict[str, float] = {}
    for row in rows:
        home = row.home_team_id
        away = row.away_team_id
        for team in (home, away):
            if rating_season.get(team) not in (None, row.season):
                ratings[team] = (
                    ratings[team] * (1 - elo.REVERSION_WEIGHT)
                    + elo.STARTING_ELO * elo.REVERSION_WEIGHT
                )
            rating_season[team] = row.season
        home_elo = ratings.get(home, elo.STARTING_ELO)
        away_elo = ratings.get(away, elo.STARTING_ELO)
        probability = elo.expected_win_prob(home_elo, away_elo)
        if row.game_instance_key in test_keys:
            values[row.game_instance_key] = probability
        if row.home_win:
            score_diff = max(1, row.home_score - row.away_score)
            mult = elo._mov_multiplier(score_diff, home_elo + elo.HOME_ADVANTAGE, away_elo)
            ratings[home] = home_elo + elo.K_FACTOR * mult * (1 - probability)
            ratings[away] = away_elo + elo.K_FACTOR * mult * (probability - 1)
        else:
            score_diff = max(1, row.away_score - row.home_score)
            mult = elo._mov_multiplier(score_diff, away_elo, home_elo + elo.HOME_ADVANTAGE)
            ratings[home] = home_elo + elo.K_FACTOR * mult * (0 - probability)
            ratings[away] = away_elo + elo.K_FACTOR * mult * (probability - 0)
    return np.array([values[row.game_instance_key] for row in test_rows], dtype=np.float64)


def _probabilities(
    config: ExperimentConfig,
    all_rows: Sequence[SnapshotRow],
    train_rows: Sequence[SnapshotRow],
    test_rows: Sequence[SnapshotRow],
    spec: TargetSpec,
) -> np.ndarray:
    parameters = config.parameters or {}
    if config.model_family == "home_rate":
        return np.full(len(test_rows), _labels(train_rows, spec).mean(), dtype=np.float64)
    if config.model_family == "log5":
        return np.array(
            [
                float(
                    log5.probability(
                        Decimal(str(row.values["home_win_pct"])),
                        Decimal(str(row.values["away_win_pct"])),
                    )
                )
                for row in test_rows
            ],
            dtype=np.float64,
        )
    if config.model_family == "elo":
        return _elo_probabilities(all_rows, test_rows)
    estimator = _make_estimator(config.model_family, parameters, config.seed)
    estimator.fit(_matrix(train_rows), _labels(train_rows, spec))
    probabilities = estimator.predict_proba(_matrix(test_rows))[:, 1]
    return np.asarray(probabilities, dtype=np.float64)


def _predictions(
    config: ExperimentConfig,
    all_rows: Sequence[SnapshotRow],
    train_rows: Sequence[SnapshotRow],
    test_rows: Sequence[SnapshotRow],
    spec: TargetSpec,
) -> np.ndarray:
    parameters = config.parameters or {}
    if config.model_family == "zero":
        return np.zeros(len(test_rows), dtype=np.float64)
    if config.model_family == "season_average":
        preds: list[float] = []
        for row in test_rows:
            hw = row.values.get("home_wins") or 0.0
            hl = row.values.get("home_losses") or 0.0
            hrf = row.values.get("home_runs_for") or 0.0
            hra = row.values.get("home_runs_allowed") or 0.0
            hg = hw + hl
            h_diff = (hrf - hra) / hg if hg > 0 else 0.0

            aw = row.values.get("away_wins") or 0.0
            al = row.values.get("away_losses") or 0.0
            arf = row.values.get("away_runs_for") or 0.0
            ara = row.values.get("away_runs_allowed") or 0.0
            ag = aw + al
            a_diff = (arf - ara) / ag if ag > 0 else 0.0

            preds.append(h_diff - a_diff)
        return np.array(preds, dtype=np.float64)
    estimator = _make_estimator(config.model_family, parameters, config.seed)
    estimator.fit(_matrix(train_rows), _labels(train_rows, spec))
    predictions = estimator.predict(_matrix(test_rows))
    return np.asarray(predictions, dtype=np.float64)


def _calibration(y: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    bins = []
    for index in range(10):
        low, high = index / 10, (index + 1) / 10
        mask = (probabilities >= low) & (
            (probabilities < high) if index < 9 else (probabilities <= high)
        )
        if mask.any():
            bins.append(
                {
                    "low": low,
                    "high": high,
                    "count": int(mask.sum()),
                    "mean_probability": float(probabilities[mask].mean()),
                    "observed_rate": float(y[mask].mean()),
                }
            )
    if len(y) < 20 or len(np.unique(y)) < 2:
        return {"bins": bins, "intercept": None, "slope": None}
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    model = LogisticRegression(C=1_000_000, fit_intercept=True, max_iter=1_000).fit(
        np.log(clipped / (1 - clipped)).reshape(-1, 1), y
    )
    return {
        "bins": bins,
        "intercept": float(model.intercept_[0]),
        "slope": float(model.coef_[0][0]),
    }


def _residual_calibration(y: np.ndarray, predictions: np.ndarray) -> dict[str, Any]:
    """Residual calibration for regression: bin games by predicted-value deciles
    and report row count, mean prediction, and mean residual (actual - predicted).
    A well-calibrated model has near-zero mean residual in every bin, not just
    a low aggregate MAE."""
    if len(y) == 0:
        return {"bins": []}
    quantiles = np.quantile(predictions, np.linspace(0.0, 1.0, 11))
    bins = []
    for index in range(10):
        low, high = float(quantiles[index]), float(quantiles[index + 1])
        mask = (predictions >= low) & (
            (predictions < high) if index < 9 else (predictions <= high)
        )
        if mask.any():
            bins.append(
                {
                    "low": low,
                    "high": high,
                    "count": int(mask.sum()),
                    "mean_prediction": float(predictions[mask].mean()),
                    "mean_residual": float((y[mask] - predictions[mask]).mean()),
                }
            )
    return {"bins": bins}


def _metrics(y: np.ndarray, probabilities: np.ndarray, seed: int) -> dict[str, Any]:
    if (
        len(y) == 0
        or not np.isfinite(probabilities).all()
        or (probabilities < 0).any()
        or (probabilities > 1).any()
    ):
        raise ExperimentError("model did not produce finite probabilities in [0, 1]")
    scores = {
        "rows": int(len(y)),
        "log_loss": float(log_loss(y, probabilities, labels=[0, 1])),
        "brier": float(brier_score_loss(y, probabilities)),
        "accuracy": float(accuracy_score(y, probabilities >= 0.5)),
        "calibration": _calibration(y, probabilities),
    }
    rng = Random(seed)
    samples = []
    for _ in range(200):
        indexes = [rng.randrange(len(y)) for _ in range(len(y))]
        sample_y, sample_p = y[indexes], probabilities[indexes]
        samples.append(
            (
                float(log_loss(sample_y, sample_p, labels=[0, 1])),
                float(brier_score_loss(sample_y, sample_p)),
            )
        )
    samples.sort()
    scores["log_loss_95ci"] = [samples[int(0.025 * 199)][0], samples[int(0.975 * 199)][0]]
    briers = sorted(sample[1] for sample in samples)
    scores["brier_95ci"] = [briers[int(0.025 * 199)], briers[int(0.975 * 199)]]
    return scores


def _regression_metrics(y: np.ndarray, predictions: np.ndarray, seed: int) -> dict[str, Any]:
    if len(y) == 0 or not np.isfinite(predictions).all():
        raise ExperimentError("model did not produce finite predictions")
    mae = float(mean_absolute_error(y, predictions))
    rmse = float(root_mean_squared_error(y, predictions))
    scores: dict[str, Any] = {
        "rows": int(len(y)),
        "mae": mae,
        "rmse": rmse,
        "calibration": _residual_calibration(y, predictions),
    }
    rng = Random(seed)
    samples: list[tuple[float, float]] = []
    for _ in range(200):
        indexes = [rng.randrange(len(y)) for _ in range(len(y))]
        sample_y, sample_p = y[indexes], predictions[indexes]
        samples.append(
            (
                float(mean_absolute_error(sample_y, sample_p)),
                float(root_mean_squared_error(sample_y, sample_p)),
            )
        )
    samples.sort()
    scores["mae_95ci"] = [samples[int(0.025 * 199)][0], samples[int(0.975 * 199)][0]]
    rmses = sorted(sample[1] for sample in samples)
    scores["rmse_95ci"] = [rmses[int(0.025 * 199)], rmses[int(0.975 * 199)]]
    return scores


def _experiment_id(config: ExperimentConfig) -> str:
    identity = {
        "snapshot_id": config.snapshot_id,
        "target": config.target,
        "feature_set_version": config.feature_set_version,
        "source_profile": config.source_profile,
        "folds": [asdict(fold) for fold in folds(config.fold_years)],
        "model": config.model_family,
        "parameters": config.parameters or {},
        "seed": config.seed,
        "calibration": config.calibration,
    }
    return f"exp-{_sha256(_canonical_json(identity))[:24]}"


def _write_artifact(
    config: ExperimentConfig, experiment_id: str, fold: Fold, payload: dict[str, Any]
) -> tuple[str, str]:
    config.artifact_dir.mkdir(parents=True, exist_ok=True)
    content = _canonical_json(payload) + "\n"
    digest = _sha256(content)
    path = config.artifact_dir / f"{digest}.json"
    if not path.exists():
        path.write_text(content)
    return str(path), digest


def _aggregate_metrics(fold_results: dict[str, dict[str, Any]]) -> dict[str, float | int]:
    rows = sum(int(metrics["rows"]) for metrics in fold_results.values())
    if rows == 0:
        raise ExperimentError("cannot aggregate an experiment with no scored rows")
    return {
        "rows": rows,
        "log_loss": sum(
            float(metrics["log_loss"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
        "brier": sum(
            float(metrics["brier"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
        "accuracy": sum(
            float(metrics["accuracy"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
    }


def _aggregate_regression_metrics(
    fold_results: dict[str, dict[str, Any]]
) -> dict[str, float | int]:
    rows = sum(int(metrics["rows"]) for metrics in fold_results.values())
    if rows == 0:
        raise ExperimentError("cannot aggregate an experiment with no scored rows")
    return {
        "rows": rows,
        "mae": sum(
            float(metrics["mae"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
        "rmse": sum(
            float(metrics["rmse"]) * int(metrics["rows"]) for metrics in fold_results.values()
        )
        / rows,
    }


def _finalize_failed_run(
    conn: psycopg.Connection, sql: str, params: tuple[Any, ...]
) -> None:
    """Roll back aborted work, record the failed run status, and commit.

    The explicit commit ensures the failure record persists in Postgres even when
    the caller manages this connection with a context manager (e.g. `with conn:`)
    that would otherwise roll back the transaction when the exception propagates.
    """
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()


def run(conn: psycopg.Connection, config: ExperimentConfig) -> dict[str, Any]:
    """Run or return a deterministic experiment; never promotes a model."""
    if config.target not in TARGET_REGISTRY:
        raise ExperimentError(f"unsupported target {config.target!r}")
    spec = TARGET_REGISTRY[config.target]
    if config.model_family not in spec.valid_model_families:
        raise ExperimentError(
            f"model_family must be one of {', '.join(spec.valid_model_families)}"
        )
    if config.feature_set_version != FEATURE_SET_VERSION:
        raise ExperimentError(
            f"only feature set {FEATURE_SET_VERSION!r} is approved for this experiment lab"
        )
    if config.calibration != "none":
        raise ExperimentError("calibration is not yet implemented; declare 'none'")
    parameters = config.parameters or {}
    _validate_parameters(config.model_family, parameters)
    snapshot_target, snapshot_feature_set, snapshot_profile = _snapshot_metadata(
        conn, config.snapshot_id
    )
    if (snapshot_target, snapshot_feature_set, snapshot_profile) != (
        config.target,
        config.feature_set_version,
        config.source_profile,
    ):
        raise ExperimentError(
            "experiment configuration must match its snapshot target, feature-set version, "
            "and source profile"
        )
    all_rows = _snapshot_rows(conn, config.snapshot_id)
    eligible = _common_rows(all_rows, spec)
    experiment_id = _experiment_id(config)
    fold_plan = [asdict(fold) for fold in folds(config.fold_years)]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, metrics_json FROM meta.experiment WHERE experiment_id = %s",
            (experiment_id,),
        )
        existing = cur.fetchone()
        if existing is not None and existing[0] == "success":
            cur.execute(
                "SELECT fold_name, metrics_json FROM meta.experiment_fold "
                "WHERE experiment_id = %s ORDER BY fold_name",
                (experiment_id,),
            )
            return {
                "experiment_id": experiment_id,
                "status": "success",
                "folds": dict(cur.fetchall()),
                "aggregate": existing[1],
                "reused": True,
            }
        if existing is not None:
            cur.execute(
                "UPDATE meta.experiment SET status = 'running', error = NULL, finished_at = NULL "
                "WHERE experiment_id = %s",
                (experiment_id,),
            )
        if existing is None:
            cur.execute(
                """INSERT INTO meta.experiment (
                    experiment_id, snapshot_id, target, source_profile, fold_plan_json,
                    model_family, parameters_json, seed, calibration, code_sha, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'running')""",
                (
                    experiment_id,
                    config.snapshot_id,
                    config.target,
                    config.source_profile,
                    json.dumps(fold_plan),
                    config.model_family,
                    json.dumps(parameters),
                    config.seed,
                    config.calibration,
                    provenance.git_sha(),
                ),
            )
    results: dict[str, Any] = {}
    try:
        for fold in folds(config.fold_years):
            train_rows = [row for row in eligible if row.season <= fold.train_through_season]
            test_rows = [row for row in eligible if row.season == fold.test_season]
            if not train_rows or not test_rows:
                raise ExperimentError(f"{fold.name} needs non-empty train and common test rows")
            if max(row.feature_cutoff_at for row in train_rows) >= min(
                row.feature_cutoff_at for row in test_rows
            ):
                raise ExperimentError(f"{fold.name} violates chronological cutoff separation")
            if spec.task_type == "classification":
                probabilities = _probabilities(config, eligible, train_rows, test_rows, spec)
                metrics = _metrics(
                    _labels(test_rows, spec), probabilities, config.seed + fold.test_season
                )
                metrics["coverage"] = {
                    "snapshot_rows": len(all_rows),
                    "common_rows": len(eligible),
                    "excluded_opening_or_missing_rate_rows": len(all_rows) - len(eligible),
                }
                predictions = [
                    {
                        "game_instance_key": row.game_instance_key,
                        "probability": float(probability),
                        "actual_home_win": row.home_win,
                    }
                    for row, probability in zip(test_rows, probabilities, strict=True)
                ]
            else:
                raw_predictions = _predictions(config, eligible, train_rows, test_rows, spec)
                metrics = _regression_metrics(
                    _labels(test_rows, spec), raw_predictions, config.seed + fold.test_season
                )
                metrics["coverage"] = {
                    "snapshot_rows": len(all_rows),
                    "common_rows": len(eligible),
                    "excluded_opening_or_missing_rate_rows": len(all_rows) - len(eligible),
                }
                predictions = [
                    {
                        "game_instance_key": row.game_instance_key,
                        "prediction": float(prediction),
                        "actual_run_differential": float(row.home_score - row.away_score),
                    }
                    for row, prediction in zip(test_rows, raw_predictions, strict=True)
                ]
            prediction_sha = _sha256(_canonical_json(predictions))
            artifact_uri, artifact_sha = _write_artifact(
                config,
                experiment_id,
                fold,
                {
                    "experiment_id": experiment_id,
                    "snapshot_id": config.snapshot_id,
                    "fold": asdict(fold),
                    "config": asdict(config) | {"artifact_dir": str(config.artifact_dir)},
                    "metrics": metrics,
                    "predictions": predictions,
                },
            )
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO meta.experiment_fold (
                        experiment_id, fold_name, train_through_season, test_season, eligible_rows,
                        train_rows, test_rows, metrics_json, prediction_sha256, artifact_uri,
                        artifact_sha256, status
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'success')
                    ON CONFLICT (experiment_id, fold_name) DO NOTHING""",
                    (
                        experiment_id,
                        fold.name,
                        fold.train_through_season,
                        fold.test_season,
                        len(eligible),
                        len(train_rows),
                        len(test_rows),
                        json.dumps(metrics),
                        prediction_sha,
                        artifact_uri,
                        artifact_sha,
                    ),
                )
            results[fold.name] = metrics
        if spec.task_type == "classification":
            aggregate = _aggregate_metrics(results)
        else:
            aggregate = _aggregate_regression_metrics(results)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE meta.experiment SET status = 'success', finished_at = now(), "
                "error = NULL, metrics_json = %s WHERE experiment_id = %s",
                (json.dumps(aggregate), experiment_id),
            )
        return {
            "experiment_id": experiment_id,
            "status": "success",
            "folds": results,
            "aggregate": aggregate,
            "reused": False,
        }
    except Exception as error:
        # A database error can leave the caller's transaction aborted. Roll
        # back the incomplete fold writes, then preserve a small terminal run
        # record so a retry is visible and uses the same deterministic ID.
        _finalize_failed_run(
            conn,
            """
            INSERT INTO meta.experiment (
                experiment_id, snapshot_id, target, source_profile, fold_plan_json,
                model_family, parameters_json, seed, calibration, code_sha,
                status, error, finished_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'failed', %s, now())
            ON CONFLICT (experiment_id) DO UPDATE SET
                status = 'failed', error = EXCLUDED.error, finished_at = EXCLUDED.finished_at
            """,
            (
                experiment_id,
                config.snapshot_id,
                config.target,
                config.source_profile,
                json.dumps(fold_plan),
                config.model_family,
                json.dumps(parameters),
                config.seed,
                config.calibration,
                provenance.git_sha(),
                str(error),
            ),
        )
        raise


def compare(conn: psycopg.Connection, snapshot_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.model_family, e.experiment_id, f.fold_name, f.metrics_json
            FROM meta.experiment e JOIN meta.experiment_fold f USING (experiment_id)
            WHERE e.snapshot_id = %s AND e.status = 'success'
            ORDER BY e.model_family, f.fold_name
            """,
            (snapshot_id,),
        )
        return [
            {"model": model, "experiment_id": ident, "fold": fold, **metrics}
            for model, ident, fold, metrics in cur.fetchall()
        ]


def health_check() -> list[Check]:
    return [
        check_table_exists("meta.experiment_target"),
        check_table_exists("meta.experiment_snapshot"),
        check_table_exists("gold.game_feature_snapshot"),
        check_table_exists("meta.feature_selection"),
    ]
