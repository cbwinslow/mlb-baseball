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

Feature set is exactly gold.game_feature's currently-populated columns
(win%, run-diff, Pythagenpat, Elo) -- starter stats, rest days, prior-
season WAR, and weather are real, known-incomplete gaps (see ADR-032's
gold.game_feature column list), not built yet. Retraining against a
richer feature set later is expected, ordinary iteration, not something
this version is "half-finished" without -- gold.prediction.model_version
exists specifically so multiple model versions can coexist.

ADR-043: FEATURE_COLUMNS now also includes every feature built since
ADR-033 (starter quality, park factor, team wOBA/wRC+, prior-season
WAR/OAA/speed, bullpen quality/fatigue). Split into REQUIRED_COLUMNS
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
"""

from pathlib import Path

import numpy as np
import psycopg
import xgboost as xgb
from sklearn.metrics import brier_score_loss, log_loss

from mlb_baseball.health import Check
from mlb_baseball.model import elo, log5

MODEL_VERSION = "gbm-v1"
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / f"{MODEL_VERSION}.json"

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
# row, see this module's docstring (ADR-043) for why a strict non-null
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

FEATURE_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# ADR-032: train through 2023, validate 2024-2025, forward-test live
# against 2026 via the normal mlb predict path -- not a fourth split here.
TRAIN_SEASON_CUTOFF = 2023
VALIDATION_SEASONS = (2024, 2025)


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
    # crash or a dropped row -- see this module's docstring (ADR-043).
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
    X_train, y_train = _fetch_rows(conn, f"season <= {TRAIN_SEASON_CUTOFF}")
    X_val, y_val = _fetch_rows(
        conn, f"season IN ({', '.join(str(s) for s in VALIDATION_SEASONS)})"
    )

    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        eval_metric="logloss",
    )
    model.fit(X_train, y_train)

    gbm_probs = model.predict_proba(X_val)[:, 1]
    home_win_pct_idx = FEATURE_COLUMNS.index("home_win_pct")
    away_win_pct_idx = FEATURE_COLUMNS.index("away_win_pct")
    home_elo_idx = FEATURE_COLUMNS.index("home_elo")
    away_elo_idx = FEATURE_COLUMNS.index("away_elo")
    log5_probs = np.array(
        [
            float(log5.probability(row[home_win_pct_idx], row[away_win_pct_idx]))
            for row in X_val
        ]
    )
    elo_probs = np.array(
        [elo.expected_win_prob(row[home_elo_idx], row[away_elo_idx]) for row in X_val]
    )

    def _score(probs: np.ndarray) -> dict:
        return {"log_loss": log_loss(y_val, probs), "brier": brier_score_loss(y_val, probs)}

    metrics = {
        "train_rows": len(y_train),
        "validation_rows": len(y_val),
        "gbm": _score(gbm_probs),
        "log5": _score(log5_probs),
        "elo": _score(elo_probs),
    }

    beats_both = (
        metrics["gbm"]["log_loss"] < metrics["log5"]["log_loss"]
        and metrics["gbm"]["log_loss"] < metrics["elo"]["log_loss"]
    )
    metrics["saved"] = beats_both
    if beats_both:
        MODEL_DIR.mkdir(exist_ok=True)
        model.save_model(str(MODEL_PATH))

    return metrics


def predict(conn: psycopg.Connection) -> int:
    if not MODEL_PATH.exists():
        return 0

    model = xgb.XGBClassifier()
    model.load_model(str(MODEL_PATH))

    columns = ", ".join(FEATURE_COLUMNS)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT mlb_game_pk, {columns} FROM gold.game_feature "
            f"WHERE home_win IS NULL AND mlb_game_pk IS NOT NULL "
            f"AND {' AND '.join(c + ' IS NOT NULL' for c in REQUIRED_COLUMNS)}"
        )
        rows = cur.fetchall()
        if not rows:
            return 0

        game_pks = [row[0] for row in rows]
        X = np.array(
            [[np.nan if v is None else float(v) for v in row[1:]] for row in rows],
            dtype=np.float64,
        )
        probs = model.predict_proba(X)[:, 1]

        predictions = [
            (game_pk, MODEL_VERSION, float(prob))
            for game_pk, prob in zip(game_pks, probs, strict=True)
        ]
        cur.executemany(
            "INSERT INTO gold.prediction (mlb_game_pk, model_version, home_win_prob) "
            "VALUES (%s, %s, %s)",
            predictions,
        )
        return len(predictions)


def health_check() -> list[Check]:
    if not MODEL_PATH.exists():
        detail = f"not found at {MODEL_PATH} — run mlb train"
        return [Check(f"{MODEL_VERSION} model file", False, detail)]
    return [Check(f"{MODEL_VERSION} model file", True, str(MODEL_PATH))]
