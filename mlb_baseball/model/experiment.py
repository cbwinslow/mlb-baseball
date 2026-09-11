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
from typing import Any, Literal

import numpy as np
import pandas as pd
import psycopg
import xgboost as xgb
from mlb_research import backtest as _backtest
from sklearn.ensemble import (
    ExtraTreesClassifier,
    ExtraTreesRegressor,
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import BayesianRidge, LogisticRegression, Ridge
from sklearn.naive_bayes import GaussianNB
from sklearn.neural_network import MLPClassifier, MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from sklearn.svm import SVC, SVR

from mlb_baseball.db import fetch_one
from mlb_baseball.health import Check, check_table_exists
from mlb_baseball.model import elo, log5, provenance
from mlb_baseball.sql import read_sql

FEATURE_SET_VERSION = "game_full_v2"
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
ALL_COLUMNS: tuple[str, ...] = (
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
    "home_win_pct",
    "away_win_pct",
    "home_win_pct_10",
    "away_win_pct_10",
    "home_run_diff",
    "away_run_diff",
    "home_pyth_wpct",
    "away_pyth_wpct",
    "home_elo",
    "away_elo",
    "home_obp",
    "away_obp",
    "home_slg",
    "away_slg",
    "home_iso",
    "away_iso",
    "home_bb_pct",
    "away_bb_pct",
    "home_k_pct",
    "away_k_pct",
    "home_babip",
    "away_babip",
    "home_runs_for_avg",
    "away_runs_for_avg",
    "home_runs_allowed_avg",
    "away_runs_allowed_avg",
    "home_pa",
    "away_pa",
    "home_woba",
    "away_woba",
    "home_wrc_plus",
    "away_wrc_plus",
    "home_sb",
    "away_sb",
    "home_cs",
    "away_cs",
    "home_wsb",
    "away_wsb",
    "home_xbt_pct",
    "away_xbt_pct",
    "home_ubr_runs",
    "away_ubr_runs",
    "home_wgdp_runs",
    "away_wgdp_runs",
    "home_bsr_total",
    "away_bsr_total",
    "home_starter_era",
    "away_starter_era",
    "home_starter_k_pct",
    "away_starter_k_pct",
    "home_starter_bb_pct",
    "away_starter_bb_pct",
    "home_starter_hr_pct",
    "away_starter_hr_pct",
    "home_starter_rest_days",
    "away_starter_rest_days",
    "home_starter_outs_7d",
    "away_starter_outs_7d",
    "home_starter_career_bf",
    "away_starter_career_bf",
    "home_starter_career_ip",
    "away_starter_career_ip",
    "home_starter_age",
    "away_starter_age",
    "home_starter_csw_pct",
    "away_starter_csw_pct",
    "home_starter_whiff_pct",
    "away_starter_whiff_pct",
    "home_starter_fstrike_pct",
    "away_starter_fstrike_pct",
    "home_starter_gb_pct",
    "away_starter_gb_pct",
    "home_starter_fb_pct",
    "away_starter_fb_pct",
    "home_starter_ld_pct",
    "away_starter_ld_pct",
    "home_starter_hr_per_fb",
    "away_starter_hr_per_fb",
    "home_starter_avg_li",
    "away_starter_avg_li",
    "home_starter_xfip",
    "away_starter_xfip",
    "home_starter_siera",
    "away_starter_siera",
    "home_starter_vs_lhb_woba",
    "away_starter_vs_lhb_woba",
    "home_starter_vs_rhb_woba",
    "away_starter_vs_rhb_woba",
    "home_starter_vs_lhb_k_pct",
    "away_starter_vs_lhb_k_pct",
    "home_starter_vs_rhb_k_pct",
    "away_starter_vs_rhb_k_pct",
    "home_starter_woba_vs_lhb",
    "away_starter_woba_vs_lhb",
    "home_starter_woba_vs_rhb",
    "away_starter_woba_vs_rhb",
    "home_starter_k_pct_vs_lhb",
    "away_starter_k_pct_vs_lhb",
    "home_starter_k_pct_vs_rhb",
    "away_starter_k_pct_vs_rhb",
    "home_starter_hard_hit_pct",
    "away_starter_hard_hit_pct",
    "home_starter_barrel_pct",
    "away_starter_barrel_pct",
    "home_starter_xwoba",
    "away_starter_xwoba",
    "home_starter_xba",
    "away_starter_xba",
    "home_starter_xslg",
    "away_starter_xslg",
    "home_starter_heart_pct",
    "away_starter_heart_pct",
    "home_starter_shadow_pct",
    "away_starter_shadow_pct",
    "home_starter_chase_pct",
    "away_starter_chase_pct",
    "home_starter_fastball_velo",
    "away_starter_fastball_velo",
    "home_starter_velo_delta",
    "away_starter_velo_delta",
    "home_starter_fastball_ivb_in",
    "away_starter_fastball_ivb_in",
    "home_starter_curve_drop_in",
    "away_starter_curve_drop_in",
    "home_starter_vert_separation_in",
    "away_starter_vert_separation_in",
    "home_starter_spin_rate_rpm",
    "away_starter_spin_rate_rpm",
    "home_bullpen_fip",
    "away_bullpen_fip",
    "home_bullpen_k_pct",
    "away_bullpen_k_pct",
    "home_bullpen_bb_pct",
    "away_bullpen_bb_pct",
    "home_bullpen_fatigue",
    "away_bullpen_fatigue",
    "home_bullpen_csw_pct",
    "away_bullpen_csw_pct",
    "home_bullpen_whiff_pct",
    "away_bullpen_whiff_pct",
    "home_bullpen_gb_pct",
    "away_bullpen_gb_pct",
    "home_bullpen_fb_pct",
    "away_bullpen_fb_pct",
    "home_bullpen_hr_per_fb",
    "away_bullpen_hr_per_fb",
    "home_bullpen_avg_li",
    "away_bullpen_avg_li",
    "home_bullpen_re24",
    "away_bullpen_re24",
    "home_bullpen_xfip",
    "away_bullpen_xfip",
    "home_bullpen_siera",
    "away_bullpen_siera",
    "home_bullpen_hard_hit_pct",
    "away_bullpen_hard_hit_pct",
    "home_bullpen_barrel_pct",
    "away_bullpen_barrel_pct",
    "home_bullpen_xwoba",
    "away_bullpen_xwoba",
    "home_bullpen_xba",
    "away_bullpen_xba",
    "home_bullpen_xslg",
    "away_bullpen_xslg",
    "home_bullpen_heart_pct",
    "away_bullpen_heart_pct",
    "home_bullpen_shadow_pct",
    "away_bullpen_shadow_pct",
    "home_bullpen_chase_pct",
    "away_bullpen_chase_pct",
    "home_bullpen_vert_separation_in",
    "away_bullpen_vert_separation_in",
    "home_batting_gb_pct",
    "away_batting_gb_pct",
    "home_batting_fb_pct",
    "away_batting_fb_pct",
    "home_batting_ld_pct",
    "away_batting_ld_pct",
    "home_batting_hr_per_fb",
    "away_batting_hr_per_fb",
    "home_batting_re24",
    "away_batting_re24",
    "home_batting_chase_pct",
    "away_batting_chase_pct",
    "home_batting_heart_swing_pct",
    "away_batting_heart_swing_pct",
    "home_offense_hard_hit_pct",
    "away_offense_hard_hit_pct",
    "home_offense_barrel_pct",
    "away_offense_barrel_pct",
    "home_offense_xwoba",
    "away_offense_xwoba",
    "home_offense_xba",
    "away_offense_xba",
    "home_offense_xslg",
    "away_offense_xslg",
    "home_war_prior",
    "away_war_prior",
    "home_oaa_prior",
    "away_oaa_prior",
    "home_speed_prior",
    "away_speed_prior",
    "home_framing_prior",
    "away_framing_prior",
    "home_catcher_csae_pct",
    "away_catcher_csae_pct",
    "home_catcher_framing_runs",
    "away_catcher_framing_runs",
    "park_factor",
    "park_factor_1yr",
    "park_factor_3yr",
    "park_factor_5yr",
    "park_hr_factor_3yr",
    "park_2b_factor_3yr",
    "park_3b_factor_3yr",
    "park_lhb_hr_factor_3yr",
    "park_rhb_hr_factor_3yr",
    "air_density_index",
    "effective_wind_speed",
    "home_offense_woba_vs_lhp",
    "away_offense_woba_vs_lhp",
    "home_offense_woba_vs_rhp",
    "away_offense_woba_vs_rhp",
    "home_platoon_matchup_woba_diff",
    "away_platoon_matchup_woba_diff",
    "win_pct_diff",
    "win_pct_10_diff",
    "pyth_wpct_diff",
    "elo_diff",
    "woba_diff",
    "wrc_plus_diff",
    "home_win_pct_trend",
    "away_win_pct_trend",
    "starter_siera_diff",
    "starter_xfip_diff",
    "starter_csw_diff",
    "starter_whiff_diff",
    "starter_xwoba_diff",
    "starter_fastball_velo_diff",
    "starter_vert_sep_diff",
    "bullpen_siera_diff",
    "bullpen_xfip_diff",
    "bullpen_csw_diff",
    "bullpen_whiff_diff",
    "bullpen_xwoba_diff",
    "offense_hard_hit_diff",
    "offense_barrel_diff",
    "offense_xwoba_diff",
    "bsr_total_diff",
    "catcher_framing_diff",
)
DEFAULT_FOLD_YEARS = tuple(range(2016, 2025))
SUPPORTED_MODELS = (
    "home_rate",
    "log5",
    "elo",
    "logistic",
    "hist_gradient_boosting",
    "xgboost",
    "random_forest",
    "extra_trees",
    "gam",
    "svm",
    "bayesian",
    "neural",
)
_SELECTION_SQL = read_sql("experiment_selection.sql")
_SNAPSHOT_INSERT_SQL = read_sql("experiment_snapshot_insert.sql")


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
            "random_forest",
            "extra_trees",
            "gam",
            "svm",
            "bayesian",
            "neural",
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
            "random_forest_regressor",
            "extra_trees_regressor",
            "gam_regressor",
            "svm_regressor",
            "bayesian_regressor",
            "neural_regressor",
        ),
    ),
}

ALL_MODEL_FAMILIES: tuple[str, ...] = tuple(
    dict.fromkeys(model for spec in TARGET_REGISTRY.values() for model in spec.valid_model_families)
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
            _SNAPSHOT_INSERT_SQL,
            [
                {
                    "snapshot_id": snapshot_id,
                    "game_instance_key": row.game_instance_key,
                    "mlb_game_pk": row.mlb_game_pk,
                    "feature_cutoff_at": row.feature_cutoff_at,
                    "season": row.season,
                    "game_date": row.game_date,
                    "game_number": row.game_number,
                    "home_team_id": row.home_team_id,
                    "away_team_id": row.away_team_id,
                    "home_score": row.home_score,
                    "away_score": row.away_score,
                    "feature_json": json.dumps(row.values),
                    "home_win": row.home_win,
                }
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


def _evaluation_frame(rows: Sequence[SnapshotRow], spec: TargetSpec) -> pd.DataFrame:
    """The tidy, one-row-per-game frame `mlb_research.backtest.run_backtest`
    evaluates: identity/period/cutoff/outcome columns, the `BASE_COLUMNS` +
    `LOG5_COLUMNS` features every model family in `run()`'s zoo can need
    (the sklearn/xgboost families read `BASE_COLUMNS` via `feature_cols`;
    `log5` reads `LOG5_COLUMNS` directly; `elo` needs the team ids and
    scores to replay its rating walk), and the declared target's label.
    """
    feature_columns = tuple(dict.fromkeys((*BASE_COLUMNS, *LOG5_COLUMNS)))
    return pd.DataFrame(
        {
            "game_instance_key": [row.game_instance_key for row in rows],
            "season": [row.season for row in rows],
            "feature_cutoff_at": [row.feature_cutoff_at for row in rows],
            "home_team_id": [row.home_team_id for row in rows],
            "away_team_id": [row.away_team_id for row in rows],
            "home_score": [row.home_score for row in rows],
            "away_score": [row.away_score for row in rows],
            "home_win": [row.home_win for row in rows],
            **{column: [row.values.get(column) for row in rows] for column in feature_columns},
            "label": [spec.label(row) for row in rows],
        }
    )


def folds(fold_years: Sequence[int]) -> tuple[Fold, ...]:
    """`Fold` boundary math has one implementation, `mlb_research.backtest
    .time_ordered_folds`; this adapts its result back to `experiment.Fold`
    (`train_through_season` / `test_season`, not `train_through` / `test`)
    because that exact shape is a stored contract -- `meta.experiment
    .fold_plan_json` and `meta.experiment_fold`'s columns are keyed on it."""
    try:
        generic_folds = _backtest.time_ordered_folds(fold_years)
    except ValueError as exc:
        raise ExperimentError("fold years must be unique, sorted calendar years") from exc
    return tuple(Fold(fold.name, fold.train_through, fold.test) for fold in generic_folds)


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


def _merged_kwargs(defaults: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    """Merge this family's fixed defaults with the caller's overrides, caller
    wins. Every one of this function's callers previously passed its
    defaults as explicit keyword arguments *and* expanded `parameters`
    alongside them (`Estimator(random_state=seed, **parameters)`) -- a real
    bug found via PR review: `_validate_parameters` legitimately allows a
    caller to override `random_state`/`n_estimators`/`n_jobs` (scikit-learn
    exposes all three as real constructor params), but overriding any of
    them raised "got multiple values for keyword argument" instead of
    applying the override, for every model family in this file, not just
    the ones added alongside this fix. Merging first and expanding once
    lets an explicit override actually take effect."""
    return {**defaults, **parameters}


def _make_estimator(model_family: str, parameters: dict[str, Any], seed: int):
    if model_family == "logistic":
        kwargs = _merged_kwargs({"max_iter": 1_000, "random_state": seed}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(**kwargs)),
            ]
        )
    if model_family == "hist_gradient_boosting":
        kwargs = _merged_kwargs({"random_state": seed}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", HistGradientBoostingClassifier(**kwargs)),
            ]
        )
    if model_family == "xgboost":
        kwargs = _merged_kwargs(
            {
                "n_estimators": 100,
                "max_depth": 3,
                "learning_rate": 0.05,
                "eval_metric": "logloss",
                "random_state": seed,
                "n_jobs": 1,
            },
            parameters,
        )
        return xgb.XGBClassifier(**kwargs)
    if model_family == "random_forest":
        kwargs = _merged_kwargs(
            {"n_estimators": 200, "random_state": seed, "n_jobs": 1}, parameters
        )
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", RandomForestClassifier(**kwargs)),
            ]
        )
    if model_family == "extra_trees":
        kwargs = _merged_kwargs(
            {"n_estimators": 200, "random_state": seed, "n_jobs": 1}, parameters
        )
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", ExtraTreesClassifier(**kwargs)),
            ]
        )
    if model_family == "gam":
        kwargs = _merged_kwargs({"max_iter": 1_000, "random_state": seed}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("spline", SplineTransformer(degree=3, n_knots=5)),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(**kwargs)),
            ]
        )
    if model_family == "svm":
        # probability=True is required for predict_proba (_probabilities()
        # calls it unconditionally for every family past the three
        # hardcoded baselines) -- scikit-learn 1.9 deprecated this in favor
        # of CalibratedClassifierCV(SVC(), ensemble=False), removal
        # targeted for 1.11. Not switched to that wrapper yet: nesting SVC
        # inside CalibratedClassifierCV would push kernel/C/etc. behind an
        # `estimator__` prefix in get_params(deep=False), breaking this
        # file's established flat-pipeline _validate_parameters pattern
        # (every sibling family here validates its own directly-tunable
        # params, not a meta-estimator's). Revisit before the 1.11 upgrade.
        kwargs = _merged_kwargs(
            {"kernel": "rbf", "probability": True, "random_state": seed}, parameters
        )
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", SVC(**kwargs)),
            ]
        )
    if model_family == "bayesian":
        # GaussianNB is scikit-learn's Bayesian classifier: it applies
        # Bayes' theorem directly (conditional independence per feature,
        # hence "naive") rather than approximating it, and exposes
        # predict_proba natively -- no probability=True-style opt-in and no
        # deprecation risk like svm's. No random_state: GaussianNB fits a
        # closed-form per-class Gaussian with no internal randomness to
        # seed (unlike the tree/boosting/SVM families above, which all
        # require random_state for their stochastic components).
        kwargs = _merged_kwargs({}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", GaussianNB(**kwargs)),
            ]
        )
    if model_family == "neural":
        # MLPClassifier: a genuine feedforward neural network (one hidden
        # layer of 100 units by default -- sklearn's own default, not
        # tuned here). max_iter raised from sklearn's default 200 to 1_000
        # for the same reason logistic/gam raise it: this pipeline's
        # scaled, imputed input can need more optimizer iterations to
        # converge than the raw default allows, and a spurious
        # ConvergenceWarning is not the failure mode this file wants to
        # surface. random_state seeds MLPClassifier's weight
        # initialization and its solver's own internal stochasticity
        # (default solver="adam", a mini-batch stochastic method).
        kwargs = _merged_kwargs({"max_iter": 1_000, "random_state": seed}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", MLPClassifier(**kwargs)),
            ]
        )
    if model_family == "ridge":
        kwargs = _merged_kwargs({"random_state": seed}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", Ridge(**kwargs)),
            ]
        )
    if model_family == "hist_gradient_boosting_regressor":
        kwargs = _merged_kwargs({"random_state": seed}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", HistGradientBoostingRegressor(**kwargs)),
            ]
        )
    if model_family == "xgboost_regressor":
        kwargs = _merged_kwargs(
            {
                "n_estimators": 100,
                "max_depth": 3,
                "learning_rate": 0.05,
                "eval_metric": "rmse",
                "random_state": seed,
                "n_jobs": 1,
            },
            parameters,
        )
        return xgb.XGBRegressor(**kwargs)
    if model_family == "random_forest_regressor":
        kwargs = _merged_kwargs(
            {"n_estimators": 200, "random_state": seed, "n_jobs": 1}, parameters
        )
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", RandomForestRegressor(**kwargs)),
            ]
        )
    if model_family == "extra_trees_regressor":
        kwargs = _merged_kwargs(
            {"n_estimators": 200, "random_state": seed, "n_jobs": 1}, parameters
        )
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("model", ExtraTreesRegressor(**kwargs)),
            ]
        )
    if model_family == "gam_regressor":
        kwargs = _merged_kwargs({"random_state": seed}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("spline", SplineTransformer(degree=3, n_knots=5)),
                ("scale", StandardScaler()),
                ("model", Ridge(**kwargs)),
            ]
        )
    if model_family == "svm_regressor":
        kwargs = _merged_kwargs({"kernel": "rbf"}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", SVR(**kwargs)),
            ]
        )
    if model_family == "bayesian_regressor":
        # BayesianRidge: genuine Bayesian linear regression -- places priors
        # on the weights and noise precision and fits them by iterative
        # evidence maximization (analytic conditional-posterior updates each
        # round, repeated until `tol` convergence or `max_iter`), matching
        # ridge's impute -> scale -> model shape. No random_state: the
        # iteration is deterministic given the data -- no internal
        # randomness to seed, unlike every tree/boosting/SVM family above
        # (GaussianNB likewise has no randomness to seed, via its own
        # single-pass closed-form per-class fit).
        kwargs = _merged_kwargs({}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", BayesianRidge(**kwargs)),
            ]
        )
    if model_family == "neural_regressor":
        # MLPRegressor: same shape and reasoning as neural above.
        kwargs = _merged_kwargs({"max_iter": 1_000, "random_state": seed}, parameters)
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                ("scale", StandardScaler()),
                ("model", MLPRegressor(**kwargs)),
            ]
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
    elif model_family == "random_forest":
        allowed = RandomForestClassifier().get_params(deep=False)
    elif model_family == "extra_trees":
        allowed = ExtraTreesClassifier().get_params(deep=False)
    elif model_family == "gam":
        allowed = LogisticRegression().get_params(deep=False)
    elif model_family == "svm":
        allowed = SVC().get_params(deep=False)
    elif model_family == "bayesian":
        allowed = GaussianNB().get_params(deep=False)
    elif model_family == "neural":
        allowed = MLPClassifier().get_params(deep=False)
    elif model_family == "ridge":
        allowed = Ridge().get_params(deep=False)
    elif model_family == "hist_gradient_boosting_regressor":
        allowed = HistGradientBoostingRegressor().get_params(deep=False)
    elif model_family == "xgboost_regressor":
        allowed = xgb.XGBRegressor().get_params(deep=False)
    elif model_family == "random_forest_regressor":
        allowed = RandomForestRegressor().get_params(deep=False)
    elif model_family == "extra_trees_regressor":
        allowed = ExtraTreesRegressor().get_params(deep=False)
    elif model_family == "gam_regressor":
        allowed = Ridge().get_params(deep=False)
    elif model_family == "svm_regressor":
        allowed = SVR().get_params(deep=False)
    elif model_family == "bayesian_regressor":
        allowed = BayesianRidge().get_params(deep=False)
    elif model_family == "neural_regressor":
        allowed = MLPRegressor().get_params(deep=False)
    else:
        raise ExperimentError(f"unsupported estimator {model_family!r}")
    unknown = sorted(set(parameters) - set(allowed))
    if unknown:
        raise ExperimentError(f"{model_family} has unsupported parameter(s): {', '.join(unknown)}")
    # svm's probability=True default isn't just a preference -- _probabilities()
    # unconditionally calls predict_proba() for every family past the three
    # hardcoded baselines, which SVC only exposes when probability=True.
    # `unknown` alone wouldn't catch an override to False: "probability" is a
    # real SVC constructor parameter, so it passes the generic allowed-set
    # check above -- confirmed directly: SVC(probability=False).predict_proba
    # raises AttributeError. Reject the override explicitly instead of
    # letting a caller-configured, individually "valid" SVC construct a
    # model that fails later, mid-run, during scoring.
    if model_family == "svm" and parameters.get("probability") is False:
        raise ExperimentError("svm requires probability=True (predict_proba is required)")


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


def _elo_step(ratings: dict[int, float], rating_season: dict[int, int], row: Any) -> float:
    """One Elo prediction-then-update step: predict from the current
    ratings, then fold `row`'s own outcome in. Shared by `_elo_fit`
    (replaying history to build state) and `_elo_predict` (walking test
    rows) so both do the exact same math as the original
    `_elo_probabilities` walk, just split at the fold boundary. Mutates
    `ratings`/`rating_season` in place; returns the predicted home-win
    probability, computed before this row's own update."""
    home, away = row.home_team_id, row.away_team_id
    for team in (home, away):
        if rating_season.get(team) not in (None, row.season):
            ratings[team] = (
                ratings[team] * (1 - elo.REVERSION_WEIGHT) + elo.STARTING_ELO * elo.REVERSION_WEIGHT
            )
        rating_season[team] = row.season
    home_elo = ratings.get(home, elo.STARTING_ELO)
    away_elo = ratings.get(away, elo.STARTING_ELO)
    probability = elo.expected_win_prob(home_elo, away_elo)
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
    return probability


def _elo_fit(train: pd.DataFrame) -> tuple[dict[int, float], dict[int, int]]:
    """`fit_fn` for `elo`: replay every train row (already time-ordered by
    `run_backtest`) to build the ratings state as of the fold boundary."""
    ratings: dict[int, float] = {}
    rating_season: dict[int, int] = {}
    for row in train.itertuples():
        _elo_step(ratings, rating_season, row)
    return ratings, rating_season


def _elo_predict(state: tuple[dict[int, float], dict[int, int]], test: pd.DataFrame) -> np.ndarray:
    """`predict_fn` for `elo`: continue the walk over test rows (also
    time-ordered), copying the fitted state so repeated calls never mutate
    it. Leak-free because `run_backtest` guarantees time_col order and this
    predicts before each row's own update."""
    ratings, rating_season = dict(state[0]), dict(state[1])
    return np.array(
        [_elo_step(ratings, rating_season, row) for row in test.itertuples()], dtype=np.float64
    )


def _season_average_predictions(test: pd.DataFrame) -> np.ndarray:
    """`predict_fn` for `season_average`: a stateless per-row formula, so
    there is no `fit_fn` state to build."""

    def to_float(value: Any) -> float:
        # A missing BASE_COLUMNS value is NaN in the DataFrame (not None as
        # in SnapshotRow.values), and `NaN or 0.0` is NaN (NaN is truthy) --
        # so this needs pd.notna(), not the original SnapshotRow code's
        # `value or 0.0` idiom, to treat missing the same way: 0.0.
        return float(value) if pd.notna(value) else 0.0

    predictions = []
    for row in test.itertuples():
        hw, hl = to_float(row.home_wins), to_float(row.home_losses)
        hrf, hra = to_float(row.home_runs_for), to_float(row.home_runs_allowed)
        hg = hw + hl
        h_diff = (hrf - hra) / hg if hg > 0 else 0.0

        aw, al = to_float(row.away_wins), to_float(row.away_losses)
        arf, ara = to_float(row.away_runs_for), to_float(row.away_runs_allowed)
        ag = aw + al
        a_diff = (arf - ara) / ag if ag > 0 else 0.0

        predictions.append(h_diff - a_diff)
    return np.array(predictions, dtype=np.float64)


def _estimator_factory(
    config: ExperimentConfig, spec: TargetSpec
) -> tuple[Callable[[pd.DataFrame], Any], Callable[[Any, pd.DataFrame], np.ndarray]]:
    """One `(fit_fn, predict_fn)` pair per model family, closing over
    `config`/`spec`, for `mlb_research.backtest.run_backtest`. Reproduces
    `_probabilities`/`_predictions`/`_elo_probabilities`'s exact math on the
    DataFrame seam the harness owns."""
    parameters = config.parameters or {}
    family = config.model_family

    if family == "home_rate":

        def home_rate_fit(train: pd.DataFrame) -> float:
            return float(train["label"].to_numpy(dtype=np.float64).mean())

        def home_rate_predict(mean: float, test: pd.DataFrame) -> np.ndarray:
            return np.full(len(test), mean, dtype=np.float64)

        return home_rate_fit, home_rate_predict

    if family == "log5":

        def log5_fit(_train: pd.DataFrame) -> None:
            return None

        def log5_predict(_model: None, test: pd.DataFrame) -> np.ndarray:
            return np.array(
                [
                    float(log5.probability(Decimal(str(home)), Decimal(str(away))))
                    for home, away in zip(test["home_win_pct"], test["away_win_pct"], strict=True)
                ],
                dtype=np.float64,
            )

        return log5_fit, log5_predict

    if family == "elo":
        return _elo_fit, _elo_predict

    if family == "zero":

        def zero_fit(_train: pd.DataFrame) -> None:
            return None

        def zero_predict(_model: None, test: pd.DataFrame) -> np.ndarray:
            return np.zeros(len(test), dtype=np.float64)

        return zero_fit, zero_predict

    if family == "season_average":

        def season_average_fit(_train: pd.DataFrame) -> None:
            return None

        def season_average_predict(_model: None, test: pd.DataFrame) -> np.ndarray:
            return _season_average_predictions(test)

        return season_average_fit, season_average_predict

    def estimator_fit(train: pd.DataFrame) -> Any:
        estimator = _make_estimator(family, parameters, config.seed)
        labels = train["label"].to_numpy()
        if spec.task_type == "classification":
            labels = labels.astype(np.int64)
        estimator.fit(train[list(BASE_COLUMNS)].to_numpy(dtype=np.float64), labels)
        return estimator

    def estimator_predict(estimator: Any, test: pd.DataFrame) -> np.ndarray:
        matrix = test[list(BASE_COLUMNS)].to_numpy(dtype=np.float64)
        if spec.task_type == "classification":
            return np.asarray(estimator.predict_proba(matrix)[:, 1], dtype=np.float64)
        return np.asarray(estimator.predict(matrix), dtype=np.float64)

    return estimator_fit, estimator_predict


# The pure evaluation math (metrics, calibration, aggregation) has one
# implementation, `mlb_research.backtest` -- these names are direct
# re-exports so `experiment.py` keeps its existing call sites and
# `tests/unit/test_experiment_metrics.py`'s imports resolve unchanged. Their
# signatures and returned dict shapes are identical to the functions they
# replace (only `calibration`'s intercept/slope now come from a numpy IRLS
# fit instead of `sklearn.LogisticRegression`, within tie-out tolerance).
_calibration = _backtest.calibration
_residual_calibration = _backtest.residual_calibration
_metrics = _backtest.classification_metrics
_regression_metrics = _backtest.regression_metrics


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


_aggregate_metrics = _backtest.aggregate_metrics
_aggregate_regression_metrics = _backtest.aggregate_regression_metrics


def _finalize_failed_run(conn: psycopg.Connection, sql: str, params: tuple[Any, ...]) -> None:
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
        raise ExperimentError(f"model_family must be one of {', '.join(spec.valid_model_families)}")
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
    frame = _evaluation_frame(all_rows, spec)
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
        generic_folds = tuple(
            _backtest.Fold(fold.name, fold.train_through_season, fold.test_season)
            for fold in folds(config.fold_years)
        )
        fit_fn, predict_fn = _estimator_factory(config, spec)
        try:
            backtest_result = _backtest.run_backtest(
                frame,
                generic_folds,
                fit_fn,
                predict_fn,
                task=spec.task_type,
                time_col="feature_cutoff_at",
                period_col="season",
                label_col="label",
                feature_cols=BASE_COLUMNS,
                required_cols=spec.required_columns,
                seed=config.seed,
            )
        except ValueError as exc:
            raise ExperimentError(str(exc)) from exc
        coverage = {
            "snapshot_rows": backtest_result.coverage["snapshot_rows"],
            "common_rows": backtest_result.coverage["common_rows"],
            "excluded_opening_or_missing_rate_rows": backtest_result.coverage["excluded_rows"],
        }
        complete_frame = _backtest.drop_incomplete(frame, spec.required_columns)
        for fold in folds(config.fold_years):
            fold_result = backtest_result.folds[fold.name]
            metrics = dict(fold_result.metrics)
            metrics["coverage"] = coverage
            # Re-derive this fold's test rows the same deterministic way
            # run_backtest split them internally (season, then a stable sort
            # by feature_cutoff_at) so fold_result.predictions -- returned in
            # that same order -- lines up with the right game identity/
            # outcome for the stored artifact.
            test_frame = complete_frame[complete_frame["season"] == fold.test_season].sort_values(
                "feature_cutoff_at", kind="stable"
            )
            if spec.task_type == "classification":
                predictions = [
                    {
                        "game_instance_key": key,
                        "probability": float(probability),
                        "actual_home_win": bool(home_win),
                    }
                    for key, probability, home_win in zip(
                        test_frame["game_instance_key"],
                        fold_result.predictions,
                        test_frame["home_win"],
                        strict=True,
                    )
                ]
            else:
                predictions = [
                    {
                        "game_instance_key": key,
                        "prediction": float(prediction),
                        "actual_run_differential": float(home_score - away_score),
                    }
                    for key, prediction, home_score, away_score in zip(
                        test_frame["game_instance_key"],
                        fold_result.predictions,
                        test_frame["home_score"],
                        test_frame["away_score"],
                        strict=True,
                    )
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
                        coverage["common_rows"],
                        fold_result.train_rows,
                        fold_result.test_rows,
                        json.dumps(metrics),
                        prediction_sha,
                        artifact_uri,
                        artifact_sha,
                    ),
                )
            results[fold.name] = metrics
        aggregate = backtest_result.aggregate
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
