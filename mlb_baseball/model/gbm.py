"""Gradient-boosted model -- the third and final piece of ADR-032's build
order, after the classical baselines (log5, Elo) proved out the pipeline
end to end. See ADR-033 for the framework/storage/evaluation decisions
this module implements, and docs/RESEARCH.md for why 55-58% accuracy is
the honest target, not a shortfall (70%+ on this kind of data is a
leakage red flag, not a win).

Deliberately separate from predict()'s daily cadence: training is a
distinct, occasional operation (mlb train), not something that reruns
every day the way log5/elo's stateless formulas do -- retraining daily
would be wasteful and could make predictions unstable day to day for no
benefit. predict() here just loads whatever model train() last saved.

Feature set grows as enrichment families get built and, separately,
proven to help -- gold.prediction.model_version exists specifically so
multiple model versions can coexist while that happens. Weather remains
a real, known-incomplete gap (schema-reserved since ADR-032, never
populated -- see docs/RESEARCH.md).

ADR-044: FEATURE_COLUMNS now also includes every feature built since
ADR-033 (starter quality, park factor, team wOBA/wRC+, prior-season
WAR/OAA/speed/framing, bullpen quality/fatigue). Split into REQUIRED_COLUMNS
(the original 10 -- win%/run-diff/Pythagenpat/Elo, populated for every
row) and the rest, which are allowed to be NULL/NaN per row rather than
filtered out with a blanket "every column must be non-null" -- that
blanket filter would otherwise gut the training set from 215K to under
19K rows (confirmed directly: home_oaa_prior/home_speed_prior only
cover 2016+, and requiring them non-null intersected against every
other new column leaves only ~9% of rows). More importantly, several
of these columns (starter quality, wOBA, wRC+, bullpen -- everything
sourced from raw.retrosheet_event, which stops at 2025) are *always*
NULL for the live 2026 season predict() actually serves -- a strict
non-null filter there wouldn't just shrink predict()'s row count, it
would zero it out entirely, breaking live predictions outright.

XGBoost handles this natively and correctly, not a workaround: its
split-finding algorithm learns a default branch direction for missing
values at each tree split (the sklearn wrapper's default `missing=nan`
already matches what _fetch_rows/predict() now pass through), so a row
missing some optional features still trains/predicts on whatever it
does have, instead of being dropped or needing manual imputation.

2026-08-20: tried adding team_prior_offense_defense_v1 and
starter_workload_v1 to OPTIONAL_COLUMNS -- both had been live in
gold.game_feature for weeks without ever being tried in this model. A
real retrain against production `mlb` beat both baselines on raw
log-loss but didn't clear the required 0.002 improvement margin over
elo; see the comment just above OPTIONAL_COLUMNS's closing bracket and
docs/DECISIONS.md for the full result.
"""

import uuid
from pathlib import Path

import numpy as np
import psycopg
import xgboost as xgb
from sklearn.metrics import brier_score_loss, log_loss

from mlb_baseball.health import Check
from mlb_baseball.model import elo, log5, provenance

MODEL_VERSION = "gbm-v1"
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / f"{MODEL_VERSION}.json"
ARTIFACTS_DIR = MODEL_DIR / "artifacts"

REQUIRED_COLUMNS = [
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
]

# Everything built since ADR-033 -- always allowed to be NULL/NaN per
# row, see this module's docstring (ADR-044) for why a strict non-null
# filter can't be used here.
OPTIONAL_COLUMNS = [
    "home_starter_era",  # true FIP, not ERA -- see starter.py (ADR-034)
    "away_starter_era",
    "home_starter_k_pct",
    "away_starter_k_pct",
    "home_starter_bb_pct",
    "away_starter_bb_pct",
    "home_starter_hr_pct",
    "away_starter_hr_pct",
    "park_factor",
    "home_woba",
    "away_woba",
    "home_wrc_plus",
    "away_wrc_plus",
    "home_war_prior",
    "away_war_prior",
    "home_bullpen_fip",
    "away_bullpen_fip",
    "home_bullpen_k_pct",
    "away_bullpen_k_pct",
    "home_bullpen_bb_pct",
    "away_bullpen_bb_pct",
    "home_bullpen_fatigue",
    "away_bullpen_fatigue",
    "home_oaa_prior",
    "away_oaa_prior",
    "home_speed_prior",
    "away_speed_prior",
]

# home_framing_prior/away_framing_prior (ADR-045), and -- as of 2026-08-20
# -- team_prior_offense_defense_v1's OBP/SLG/ISO/BB%/K%/BABIP/run-environment
# columns (ADR-061) plus starter_workload_v1's rest-days/7-day-outs columns
# (ADR-068/069) are deliberately NOT in OPTIONAL_COLUMNS: real retrains
# against production `mlb` that added them beat both baselines on raw
# log-loss but didn't clear the required 0.002 improvement margin over
# elo (team_rate + starter_workload together: gbm log_loss 0.6792 vs
# elo's 0.6801, only a 0.0009 improvement over elo -- well under the
# required 0.002 margin; the model beat log5's 0.9774 log-loss by a wide
# 0.2982 margin, well clear -- it was elo's tighter margin it missed;
# see docs/DECISIONS.md for the full result), so the saved model
# on disk still expects the 37-column shape above it -- adding columns
# here without a successful save broke predict() outright (ValueError:
# Feature shape mismatch, confirmed directly in production before this
# fix, the exact same failure mode framing's own attempt hit first).
# Re-add any of these once a future `mlb train` run that includes them
# actually beats both baselines and saves a new model with the wider
# shape.

FEATURE_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# ADR-032: train through 2023, validate 2024-2025, forward-test live
# against 2026 via the normal mlb predict path -- not a fourth split here.
TRAIN_SEASON_CUTOFF = 2023
VALIDATION_SEASONS = (2024, 2025)
# A challenger must clear this absolute held-out log-loss margin over *each*
# baseline before it can become champion.  It prevents a one-ten-thousandth
# point fluctuation from replacing a working model; it is a promotion policy,
# not evidence that the margin is statistically significant.
MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT = 0.002


def _fetch_rows(conn: psycopg.Connection, season_filter: str) -> tuple[np.ndarray, np.ndarray]:
    columns = ", ".join(FEATURE_COLUMNS)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {columns}, home_win FROM gold.game_feature "
            f"WHERE home_win IS NOT NULL "
            f"AND {' AND '.join(c + ' IS NOT NULL' for c in REQUIRED_COLUMNS)} "
            f"AND {season_filter}"
        )
        rows = cur.fetchall()
    # None (NULL for an OPTIONAL_COLUMNS feature) becomes NaN, not a
    # crash or a dropped row -- see this module's docstring (ADR-044).
    data = np.array(
        [[np.nan if v is None else float(v) for v in row[:-1]] for row in rows], dtype=np.float64
    )
    labels = np.array([1.0 if row[-1] else 0.0 for row in rows], dtype=np.float64)
    return data, labels


def train(conn: psycopg.Connection) -> dict:
    """Fits an XGBoost classifier on seasons through TRAIN_SEASON_CUTOFF,
    evaluates on VALIDATION_SEASONS against log5 and Elo computed on the
    exact same rows (not gold.prediction, which is only ever written for
    still-undecided games -- see log5.py/elo.py), and only saves the
    model to disk if it actually beats both. Never overwrites a working
    model with a worse one silently."""
    artifacts_dir = MODEL_DIR / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    X_train, y_train = _fetch_rows(conn, f"season <= {TRAIN_SEASON_CUTOFF}")
    X_val, y_val = _fetch_rows(conn, f"season IN ({', '.join(str(s) for s in VALIDATION_SEASONS)})")

    parameters = {
        "n_estimators": 200,
        "max_depth": 3,
        "learning_rate": 0.05,
        "eval_metric": "logloss",
    }
    model = xgb.XGBClassifier(**parameters)
    model.fit(X_train, y_train)

    gbm_probs = model.predict_proba(X_val)[:, 1]
    home_win_pct_idx = FEATURE_COLUMNS.index("home_win_pct")
    away_win_pct_idx = FEATURE_COLUMNS.index("away_win_pct")
    home_elo_idx = FEATURE_COLUMNS.index("home_elo")
    away_elo_idx = FEATURE_COLUMNS.index("away_elo")
    log5_probs = np.array(
        [float(log5.probability(row[home_win_pct_idx], row[away_win_pct_idx])) for row in X_val]
    )
    elo_probs = np.array(
        [elo.expected_win_prob(row[home_elo_idx], row[away_elo_idx]) for row in X_val]
    )

    def _score(probs: np.ndarray) -> dict:
        return {"log_loss": log_loss(y_val, probs), "brier": brier_score_loss(y_val, probs)}

    gbm_score = _score(gbm_probs)
    log5_score = _score(log5_probs)
    elo_score = _score(elo_probs)
    metrics: dict = {
        "train_rows": len(y_train),
        "validation_rows": len(y_val),
        "gbm": gbm_score,
        "log5": log5_score,
        "elo": elo_score,
    }

    improvements = {
        "vs_log5": log5_score["log_loss"] - gbm_score["log_loss"],
        "vs_elo": elo_score["log_loss"] - gbm_score["log_loss"],
    }
    beats_both = all(value >= MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT for value in improvements.values())
    metrics["promotion"] = {
        "min_log_loss_improvement": MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT,
        "actual_improvement": improvements,
        "eligible": beats_both,
    }
    metrics["saved"] = beats_both

    tmp_path = artifacts_dir / f"_tmp_{uuid.uuid4().hex}.json"
    model.save_model(str(tmp_path))
    sha256 = provenance.artifact_sha256(tmp_path)
    artifact_path = artifacts_dir / f"{sha256}.json"
    if not artifact_path.exists():
        tmp_path.rename(artifact_path)
    else:
        tmp_path.unlink()

    status = "champion" if beats_both else "candidate"
    model_id = provenance.register_model(
        conn,
        name="gbm",
        target="home_win",
        model_version=MODEL_VERSION,
        feature_set_version="game-feature-v1",
        status=status,
        artifact_path=artifact_path,
        parameters=parameters,
        metrics=metrics,
    )

    data_cutoff, feature_snapshot_id = provenance.feature_snapshot(
        conn, where=f"season <= {TRAIN_SEASON_CUTOFF}"
    )
    run_id = provenance.start_run(
        conn,
        run_type="train",
        model_id=model_id,
        data_cutoff=data_cutoff,
        source_snapshot=feature_snapshot_id,
        feature_snapshot_id=feature_snapshot_id,
    )
    try:
        provenance.finish_run(conn, run_id)
    except Exception as error:
        provenance.finish_run(conn, run_id, error=error)
        raise

    metrics["model_id"] = model_id
    return metrics


def _get_champion(conn: psycopg.Connection) -> tuple[str, Path] | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT model_id, artifact_uri "
            "FROM meta.model "
            "WHERE name = %s AND status = 'champion' "
            "ORDER BY created_at DESC LIMIT 1",
            ("gbm",),
        )
        row = cur.fetchone()
        if not row or not row[1]:
            return None
        model_id, artifact_uri = row
        artifact_path = Path(artifact_uri)
        if not artifact_path.exists():
            return None
        return model_id, artifact_path


def predict(conn: psycopg.Connection) -> int:
    champion = _get_champion(conn)
    if champion is None:
        return 0

    model_id, artifact_path = champion
    model = xgb.XGBClassifier()
    model.load_model(str(artifact_path))

    columns = ", ".join(FEATURE_COLUMNS)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT mlb_game_pk, game_instance_key, {columns} FROM gold.game_feature "
            f"WHERE home_win IS NULL AND mlb_game_pk IS NOT NULL "
            f"AND {' AND '.join(c + ' IS NOT NULL' for c in REQUIRED_COLUMNS)}"
        )
        rows = cur.fetchall()

    data_cutoff, feature_snapshot_id = provenance.feature_snapshot(
        conn, where="home_win IS NULL AND mlb_game_pk IS NOT NULL"
    )
    run_id = provenance.start_run(
        conn,
        run_type="predict",
        model_id=model_id,
        data_cutoff=data_cutoff,
        source_snapshot=feature_snapshot_id,
        feature_snapshot_id=feature_snapshot_id,
    )
    try:
        if not rows:
            provenance.finish_run(conn, run_id)
            return 0

        game_pks = [row[0] for row in rows]
        game_instance_keys = [row[1] for row in rows]
        X = np.array(
            [[np.nan if v is None else float(v) for v in row[2:]] for row in rows],
            dtype=np.float64,
        )
        probs = model.predict_proba(X)[:, 1]

        predictions = [
            (game_pk, game_instance_key, MODEL_VERSION, float(prob), model_id, run_id)
            for game_pk, game_instance_key, prob in zip(
                game_pks, game_instance_keys, probs, strict=True
            )
        ]
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO gold.prediction "
                "(mlb_game_pk, game_instance_key, model_version, home_win_prob, model_id, "
                "model_run_id, "
                "data_cutoff, feature_snapshot_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                [(*prediction, data_cutoff, feature_snapshot_id) for prediction in predictions],
            )
        provenance.finish_run(conn, run_id)
        return len(predictions)
    except Exception as error:
        provenance.finish_run(conn, run_id, error=error)
        raise


def health_check() -> list[Check]:
    artifacts_dir = MODEL_DIR / "artifacts"
    if (artifacts_dir.exists() and any(artifacts_dir.glob("*.json"))) or MODEL_PATH.exists():
        return [Check(f"{MODEL_VERSION} model file", True, str(MODEL_DIR))]
    detail = f"not found in {artifacts_dir} — run mlb train"
    return [Check(f"{MODEL_VERSION} model file", False, detail)]
