"""Stacking meta-learner over log5-v1/elo-v1/gbm-v1's own predictions (and,
optionally, polymarket-v1/kalshi-v1's) -- the "(b) formal meta-learner" half
of docs/RESEARCH.md's "Model stacking / ensembling" section, now actually
built. Not a new base signal: this module never touches gold.game_feature
directly, only gold.prediction's own already-generated probabilities --
"how much should we trust each model's opinion, given how the others voted
on the same game."

Meta-learner choice: logistic regression, not XGBoost -- a deliberate
departure from gbm.py's own precedent, decided only after checking real
production numbers, not assumed going in. Verified directly against
production (2026-08-04): only 47 real decided games currently have a latest
prediction from all three of log5-v1/elo-v1/gbm-v1 (see
_fetch_training_rows) -- far short of the "hundreds" this module was
originally scoped assuming, because gbm-v1 has only ever been predicting
for a recent, narrow window of games so far (173 distinct games total,
ever). At n=47 (~37 train / ~10 held-out after the chronological split
below), a boosted-tree meta-learner stacking only 3-7 already-strong input
features has more than enough capacity to memorize the training split
outright -- exactly the overfitting risk docs/RESEARCH.md's own stacking
section names as the reason "a simple logistic regression ... is the
classic, defensible choice." An L2-regularized logistic regression over a
handful of bounded [0, 1] inputs has orders of magnitude less capacity to
overfit than even a shallow XGBoost model at this sample size, and each of
its inputs is already an independently strong, well-calibrated probability
estimate -- exactly the regime linear stacking was designed for (a
"level-1" combiner over strong "level-0" models, not a model that needs to
learn feature interactions from scratch).

Optional-column handling deliberately does NOT reuse gbm.py's
XGBoost-native-missing-value pattern -- sklearn's LogisticRegression
(unlike XGBoost) has no native NaN split-direction handling to reuse, that
machinery is XGBoost-specific. Instead, each optional model's probability
gets the standard missing-data treatment for a linear model: impute a
neutral 0.5 ("no information") placeholder plus a paired binary presence
indicator (see _optional_feature) -- an established technique, not an ad
hoc workaround. This serves the same goal gbm.py's own pattern serves: a
row missing polymarket-v1/kalshi-v1 (currently the large majority --
market coverage is a recent ~21-game window, ADR-052/053) still trains/
predicts on whatever it has, and the model can learn to discount the
placeholder via the indicator when the data isn't real.

Live-serving asymmetry, worth flagging explicitly: market.py's own
docstring establishes that polymarket-v1/kalshi-v1 predictions are
retrospective-only -- core.market.game_id only ever resolves for an
already-decided game. That means predict()'s own targeted games (still
undecided, gold.game_feature.home_win IS NULL) can never have a
polymarket-v1/kalshi-v1 row in gold.prediction *by construction* -- the
market inputs are only ever non-missing in train()'s training set
(evaluating already-decided games), never in predict()'s live-serving
path, today. Not a bug to route around: the model is trained with the
missing case fully represented (imputed 0.5 + indicator 0), so predict()
always lands on that well-defined branch. The market signal gaining
influence "with no special-casing needed" describes the future state
where a live market-matching extension (market.py's own documented
"Revisit if") starts landing pre-game rows -- not something already true
today.

Held-out evaluation is chronological (train on the earliest ~80% of
decided games by game_date, evaluate on the most recent ~20%), not a
random split -- matches this project's own walk-forward validation
discipline (docs/RESEARCH.md "Leakage / validation discipline") and
ADR-032/033's train/validation season split, at whatever timescale this
dataset actually has (days, not seasons, given how little history exists
yet). train() only overwrites the saved model if it beats every one of
log5-v1/elo-v1/gbm-v1 individually on held-out log-loss -- gbm.py's own
"never blindly overwrite a working model" precedent, extended to a
three-way comparison.

"Predict once per game," not once per stale row: gold.prediction is
history-preserving by design (migration 0013) -- a model still targeting
an upcoming game can accumulate several rows for the same (game,
model_version) as days pass, all sharing the same eventual outcome once
backfilled. Both _fetch_training_rows and _fetch_predict_rows dedupe via
`DISTINCT ON (mlb_game_pk, model_version) ... ORDER BY generated_at DESC`
before joining -- confirmed directly against production this matters:
log5-v1/elo-v1/gbm-v1 have 12,748/13,885/2,163 raw gold.prediction rows
but only 689/793/173 distinct games between them, an ~14x average
duplication factor from re-prediction while games stayed upcoming. Feeding
the raw (undeduped) table into a join would silently multiply-count
several stale, superseded probabilities per game as if they were
independent training examples.
"""

import json
import math
from decimal import Decimal
from pathlib import Path

import numpy as np
import psycopg
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss

from mlb_baseball.health import Check

MODEL_VERSION = "stack-v1"
MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "models"
MODEL_PATH = MODEL_DIR / f"{MODEL_VERSION}.json"

BASE_MODELS = ("log5-v1", "elo-v1", "gbm-v1")
MARKET_MODELS = ("polymarket-v1", "kalshi-v1")
ALL_MODELS = BASE_MODELS + MARKET_MODELS

# feature_row()'s own fixed output order -- train() and predict() both go
# through feature_row(), so this list and the coefficients saved to
# MODEL_PATH can never silently drift out of sync with each other.
FEATURE_NAMES = [
    "log5",
    "elo",
    "gbm",
    "polymarket",
    "polymarket_present",
    "kalshi",
    "kalshi_present",
]

# Chronological, not random -- see module docstring. 0.8 is an ordinary,
# unremarkable train/test split ratio, not tuned against this dataset.
TRAIN_FRACTION = 0.8

_MODEL_PARAMS = {
    "log5": BASE_MODELS[0],
    "elo": BASE_MODELS[1],
    "gbm": BASE_MODELS[2],
    "polymarket": MARKET_MODELS[0],
    "kalshi": MARKET_MODELS[1],
}

# Shared by both queries below: the latest (by generated_at) gold.prediction
# row per (game, model_version), restricted to the 5 model_versions this
# module cares about -- see module docstring's "predict once per game" note.
_LATEST_CTE = """
    latest AS (
        SELECT DISTINCT ON (mlb_game_pk, model_version)
            mlb_game_pk, model_version, home_win_prob, actual_home_win
        FROM gold.prediction
        WHERE model_version = ANY(%(models)s)
        ORDER BY mlb_game_pk, model_version, generated_at DESC
    )
"""

# Training set: every decided game (actual_home_win resolved) where all
# three of log5-v1/elo-v1/gbm-v1 have a latest prediction -- polymarket-v1/
# kalshi-v1 joined in as optional (LEFT JOIN, NULL when absent, the normal
# case -- see module docstring). Ordered by game_date for the chronological
# split in train(). core.game is an inner join, not a risk of dropping real
# rows: actual_home_win only resolves via backfill_outcomes()'s own join
# through core.game, so a row with actual_home_win IS NOT NULL always has
# a matching core.game row by construction.
_TRAINING_ROWS_SQL = f"""
    WITH {_LATEST_CTE}
    SELECT g.game_date, l1.actual_home_win,
           l1.home_win_prob, l2.home_win_prob, l3.home_win_prob,
           p.home_win_prob, k.home_win_prob
    FROM latest l1
    JOIN latest l2 ON l2.mlb_game_pk = l1.mlb_game_pk AND l2.model_version = %(elo)s
    JOIN latest l3 ON l3.mlb_game_pk = l1.mlb_game_pk AND l3.model_version = %(gbm)s
    LEFT JOIN latest p ON p.mlb_game_pk = l1.mlb_game_pk AND p.model_version = %(polymarket)s
    LEFT JOIN latest k ON k.mlb_game_pk = l1.mlb_game_pk AND k.model_version = %(kalshi)s
    JOIN core.game g ON g.game_pk = l1.mlb_game_pk
    WHERE l1.model_version = %(log5)s AND l1.actual_home_win IS NOT NULL
    ORDER BY g.game_date, l1.mlb_game_pk
"""

# Live-serving set: every still-undecided game (same home_win IS NULL scope
# log5.predict()/elo.predict()/gbm.predict() already use) where all three
# base models have a latest prediction. Market columns will be NULL here in
# practice every time -- see module docstring's "live-serving asymmetry."
_PREDICT_ROWS_SQL = f"""
    WITH candidates AS (
        SELECT mlb_game_pk, game_instance_key FROM gold.game_feature
        WHERE home_win IS NULL AND mlb_game_pk IS NOT NULL
    ),
    {_LATEST_CTE}
    SELECT c.mlb_game_pk, c.game_instance_key, l1.home_win_prob, l2.home_win_prob,
           l3.home_win_prob, p.home_win_prob, k.home_win_prob
    FROM candidates c
    JOIN latest l1 ON l1.mlb_game_pk = c.mlb_game_pk AND l1.model_version = %(log5)s
    JOIN latest l2 ON l2.mlb_game_pk = c.mlb_game_pk AND l2.model_version = %(elo)s
    JOIN latest l3 ON l3.mlb_game_pk = c.mlb_game_pk AND l3.model_version = %(gbm)s
    LEFT JOIN latest p ON p.mlb_game_pk = c.mlb_game_pk AND p.model_version = %(polymarket)s
    LEFT JOIN latest k ON k.mlb_game_pk = c.mlb_game_pk AND k.model_version = %(kalshi)s
"""


def _optional_feature(prob: Decimal | float | None) -> tuple[float, float]:
    """Missing-value treatment for a linear meta-learner (contrast gbm.py's
    XGBoost-native handling -- see module docstring): a neutral 0.5
    ("no information") placeholder plus a paired binary presence indicator,
    so logistic regression can learn to discount the placeholder when the
    indicator says it isn't real data."""
    if prob is None:
        return 0.5, 0.0
    return float(prob), 1.0


def feature_row(
    log5_prob: Decimal | float,
    elo_prob: Decimal | float,
    gbm_prob: Decimal | float,
    polymarket_prob: Decimal | float | None,
    kalshi_prob: Decimal | float | None,
) -> list[float]:
    """The one place feature order/shape is decided -- train() and
    predict() both go through this, matching FEATURE_NAMES exactly, so
    they can never silently drift out of sync (the bug class gbm.py's own
    FEATURE_COLUMNS/OPTIONAL_COLUMNS split guards against)."""
    poly_val, poly_present = _optional_feature(polymarket_prob)
    kalshi_val, kalshi_present = _optional_feature(kalshi_prob)
    return [
        float(log5_prob),
        float(elo_prob),
        float(gbm_prob),
        poly_val,
        poly_present,
        kalshi_val,
        kalshi_present,
    ]


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _fetch_training_rows(conn: psycopg.Connection) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(_TRAINING_ROWS_SQL, {"models": list(ALL_MODELS), **_MODEL_PARAMS})
        return cur.fetchall()


def _fetch_predict_rows(conn: psycopg.Connection) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(_PREDICT_ROWS_SQL, {"models": list(ALL_MODELS), **_MODEL_PARAMS})
        return cur.fetchall()


def train(conn: psycopg.Connection) -> dict:
    """Fits a logistic regression on the earliest TRAIN_FRACTION of real
    decided games (by game_date), evaluates on the most recent held-out
    slice against log5-v1/elo-v1/gbm-v1's own probabilities for the exact
    same games, and only saves the model if it beats all three on held-out
    log-loss. Never overwrites a working model with a worse one silently
    -- same contract as gbm.train()."""
    rows = _fetch_training_rows(conn)
    if len(rows) < 4:
        raise ValueError(
            f"only {len(rows)} decided games have a prediction from all of "
            f"{BASE_MODELS} -- too few to train/evaluate a held-out split"
        )

    split_idx = int(len(rows) * TRAIN_FRACTION)
    split_idx = max(1, min(split_idx, len(rows) - 1))  # keep both sides non-empty
    train_rows, test_rows = rows[:split_idx], rows[split_idx:]

    def _xy(rows: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
        X = [
            feature_row(log5, elo, gbm, poly, kalshi) for _, _, log5, elo, gbm, poly, kalshi in rows
        ]
        y = [1.0 if actual else 0.0 for _, actual, *_ in rows]
        return np.array(X, dtype=np.float64), np.array(y, dtype=np.float64)

    X_train, y_train = _xy(train_rows)
    X_test, y_test = _xy(test_rows)

    model = LogisticRegression()
    model.fit(X_train, y_train)

    stack_probs = model.predict_proba(X_test)[:, 1]
    log5_probs = np.array([float(r[2]) for r in test_rows])
    elo_probs = np.array([float(r[3]) for r in test_rows])
    gbm_probs = np.array([float(r[4]) for r in test_rows])

    def _score(probs: np.ndarray) -> dict:
        # labels=[0.0, 1.0] pinned explicitly: at this sample size a
        # chronological held-out slice could plausibly land on a single
        # class by chance, which log_loss otherwise rejects outright.
        return {
            "log_loss": log_loss(y_test, probs, labels=[0.0, 1.0]),
            "brier": brier_score_loss(y_test, probs),
        }

    stack_score = _score(stack_probs)
    log5_score = _score(log5_probs)
    elo_score = _score(elo_probs)
    gbm_score = _score(gbm_probs)

    metrics: dict = {
        "train_rows": len(train_rows),
        "test_rows": len(test_rows),
        "stack": stack_score,
        "log5": log5_score,
        "elo": elo_score,
        "gbm": gbm_score,
    }

    beats_all = (
        stack_score["log_loss"] < log5_score["log_loss"]
        and stack_score["log_loss"] < elo_score["log_loss"]
        and stack_score["log_loss"] < gbm_score["log_loss"]
    )
    metrics["saved"] = beats_all
    if beats_all:
        MODEL_DIR.mkdir(exist_ok=True)
        MODEL_PATH.write_text(
            json.dumps(
                {
                    "features": FEATURE_NAMES,
                    "coef": model.coef_[0].tolist(),
                    "intercept": float(model.intercept_[0]),
                }
            )
        )

    return metrics


def predict(conn: psycopg.Connection) -> int:
    if not MODEL_PATH.exists():
        return 0

    saved = json.loads(MODEL_PATH.read_text())
    coef: list[float] = saved["coef"]
    intercept: float = saved["intercept"]

    rows = _fetch_predict_rows(conn)
    if not rows:
        return 0

    predictions = []
    for game_pk, game_instance_key, log5_prob, elo_prob, gbm_prob, poly_prob, kalshi_prob in rows:
        features = feature_row(log5_prob, elo_prob, gbm_prob, poly_prob, kalshi_prob)
        z = sum(c * f for c, f in zip(coef, features, strict=True)) + intercept
        predictions.append((game_pk, game_instance_key, MODEL_VERSION, _sigmoid(z)))

    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO gold.prediction "
            "(mlb_game_pk, game_instance_key, model_version, home_win_prob) "
            "VALUES (%s, %s, %s, %s)",
            predictions,
        )
    return len(predictions)


def health_check() -> list[Check]:
    if not MODEL_PATH.exists():
        detail = f"not found at {MODEL_PATH} — run mlb train"
        return [Check(f"{MODEL_VERSION} model file", False, detail)]
    return [Check(f"{MODEL_VERSION} model file", True, str(MODEL_PATH))]
