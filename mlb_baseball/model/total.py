"""Run-total (over/under) prediction (ADR-056) -- a genuinely different
target from log5.py/elo.py/gbm.py: expected *combined* runs scored, not
which team wins. Regression, not classification against a specific betting
line -- checked directly against production before deciding, not assumed
(see docs/RESEARCH.md): raw.polymarket_market has 12,766 'totals' rows with
a real `line` column (e.g. "Total: Over 8.5"), but conform.py's
_polymarket_market_rows only ever resolves an outcome whose text matches a
*team name* (the moneyline shape) -- a totals market's outcomes are
literally "Over"/"Under", so every one of those rows is silently dropped
before it ever reaches core.market. core.market has zero usable total-runs
market data today; wiring a second, genuinely different match/resolve path
(an Over/Under outcome resolves against a specific numeric line, not a team)
would be new, real scope, not a small extension -- out of bounds for this
change per CLAUDE.md's scope discipline. Regression against the honest,
directly-computable target (`core.game.home_score + core.game.away_score`)
is the safer, immediately-buildable v1; matching a specific external line is
real, separate follow-up work once core.market's own totals-matching exists.

Feature set is deliberately NOT gbm.py's FEATURE_COLUMNS -- built by
checking correlation against real total-runs data first, not copied from
the win/loss model (see docs/RESEARCH.md "Run totals" for the full
correlation table computed against all 216,729 real decided games). The
win/loss-oriented columns (win%, run-diff, Pythagenpat, Elo) all landed
within noise of zero correlation with total runs (|r| < 0.02) -- unsurprising,
since a team can be "strong" via either elite pitching (suppresses total
runs) or elite hitting (inflates it), so the SAME win/loss rating doesn't
carry a consistent sign for a run-total target. Prior-season OAA/speed/
framing/WAR did too (|r| < 0.011) and are additionally sparse (~5-11%
coverage) -- excluded rather than added as noise. Weather columns
(temp_f/wind_speed_mph/wind_dir/sky/precip) are a real, confirmed-directly
gap: 0 of 216,729+ gold.game_feature rows have any of them populated at
all (not built by anything in this codebase yet) -- excluded for having
literally zero signal to offer, not a design choice against them in
principle. What's left -- park factor, team wOBA/wRC+, starter/bullpen
FIP/K%/BB%/HR% -- all showed the expected-sign correlation (positive for
scoring-friendly signals, negative for pitcher-suppressing ones) and are
populated at the same real, meaningful scale (88-96% of decided games)
gbm.py's own OPTIONAL_COLUMNS already established as usable via XGBoost's
native missing-value handling -- same discipline reused here, not
reinvented.

REQUIRED_COLUMNS is just park_factor: the one signal common to ~96% of
decided games in both the train and validation splits, and the input the
naive baseline (below) itself depends on -- without it there's no baseline
to compare against for that row at all, so filtering it as REQUIRED (unlike
gbm.py's own 10-column REQUIRED set) isn't an arbitrary choice, it's what
the evaluation itself needs. Everything else is OPTIONAL (NaN-allowed),
exactly gbm.py's ADR-044 precedent.

Naive baseline -- "the park's trailing average total" (the task's own
framing, verified as sensible before building: real 2021-2025 league-wide
averages cluster tightly around 8.6-9.2 runs/game, while Coors Field's own
trailing average sits at 10.7-11.8, a real, meaningfully different number a
flat league-wide constant would miss). Built by reusing park_factor
(already trailing-window, no-leakage, verified in ADR-035) rather than
computing a second, parallel trailing-runs-by-venue query from scratch:
baseline_total = league_trailing_avg_total(season) * park_factor / 100,
where league_trailing_avg_total is the same TRAILING_SEASONS-year,
games-weighted, strictly-prior-seasons window park.py already uses for
park_factor itself -- consistent leakage discipline, not a second one
invented for this module. A season with no trailing league history at all
(the deep past, or a target season more than TRAILING_SEASONS after the
first tracked one but still short of real prior data) has no baseline and
is naturally excluded by the inner join, not defaulted to a guess -- same
"leave it out, don't guess" precedent as core.game.game_pk's own backfill.

train() only saves a new model if it beats this baseline on RMSE over the
validation split -- same "never silently overwrite a working model with a
worse one" discipline as gbm.py's own beats_both check, just against one
baseline instead of two (log5/Elo have no run-total analogue to compare
against).

predict() targets the same home_win IS NULL scope as log5/elo/gbm (still-
upcoming games) and gold.total_prediction is history-preserving with
generated_at in its own composite PK -- same precedent as gold.prediction
(migration 0014): re-running predict() for a game before it's decided adds
another row, tracking how the prediction moved as game day approaches,
rather than overwriting it in place.
"""

import numpy as np
import psycopg
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from mlb_baseball.db import fetch_one, get_connection
from mlb_baseball.health import Check, check_table_has_rows
from mlb_baseball.model import provenance

MODEL_VERSION = "total-v1"
MODEL_DIR = provenance.models_dir()
MODEL_PATH = MODEL_DIR / f"{MODEL_VERSION}.json"

# Same trailing window as park.py's own TRAILING_SEASONS -- see module
# docstring for why the baseline reuses park_factor's own leakage
# discipline rather than a second, parallel one.
TRAILING_SEASONS = 3

REQUIRED_COLUMNS = ["park_factor"]

# Populated at 88-96% of decided games (confirmed directly against
# production, see docs/RESEARCH.md) -- allowed to be NULL/NaN per row,
# same XGBoost-native-missing-value precedent as gbm.py's OPTIONAL_COLUMNS
# (ADR-044), not a blanket non-null filter that would gut the training set.
OPTIONAL_COLUMNS = [
    "home_woba",
    "away_woba",
    "home_wrc_plus",
    "away_wrc_plus",
    "home_starter_era",  # true FIP, see starter.py (ADR-034)
    "away_starter_era",
    "home_starter_k_pct",
    "away_starter_k_pct",
    "home_starter_bb_pct",
    "away_starter_bb_pct",
    "home_starter_hr_pct",
    "away_starter_hr_pct",
    "home_bullpen_fip",
    "away_bullpen_fip",
    "home_bullpen_k_pct",
    "away_bullpen_k_pct",
    "home_bullpen_bb_pct",
    "away_bullpen_bb_pct",
    "home_bullpen_fatigue",
    "away_bullpen_fatigue",
]

FEATURE_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# ADR-032's own split, reused for consistency: train through 2023, validate
# 2024-2025, forward-test live against 2026 via the normal mlb predict path.
TRAIN_SEASON_CUTOFF = 2023
VALIDATION_SEASONS = (2024, 2025)

# Shared by both _fetch_training_rows and _fetch_upcoming_rows -- the
# games-weighted (not a plain average-of-averages, since seasons have
# different game counts, e.g. 2020's shortened season) trailing league
# average total runs entering `target_season`, for whatever seasons the
# caller actually needs (`needed_seasons_sql`).
_LEAGUE_TRAILING_CTE = """
WITH season_totals AS (
    SELECT season, avg(home_score + away_score) AS avg_total, count(*) AS games
    FROM core.game
    WHERE game_type = 'regular' AND home_score IS NOT NULL AND away_score IS NOT NULL
    GROUP BY season
),
needed_seasons AS (
    {needed_seasons_sql}
),
league_trailing AS (
    SELECT n.season AS target_season,
        sum(st.avg_total * st.games) / NULLIF(sum(st.games), 0) AS league_avg_total
    FROM needed_seasons n
    JOIN season_totals st
        ON st.season BETWEEN n.season - %(trailing_seasons)s AND n.season - 1
    GROUP BY n.season
)
"""

_TRAIN_SQL_TEMPLATE = (
    _LEAGUE_TRAILING_CTE
    + """
SELECT {columns}, lt.league_avg_total * f.park_factor / 100.0 AS baseline_total,
    (g.home_score + g.away_score) AS total_runs
FROM gold.game_feature f
JOIN core.game g ON g.id = f.game_id
JOIN league_trailing lt ON lt.target_season = f.season
WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL
    AND {required_not_null}
    AND {season_filter}
"""
)

_PREDICT_SQL_TEMPLATE = (
    _LEAGUE_TRAILING_CTE
    + """
SELECT f.mlb_game_pk, {columns}, lt.league_avg_total * f.park_factor / 100.0 AS baseline_total
FROM gold.game_feature f
JOIN league_trailing lt ON lt.target_season = f.season
WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL
    AND {required_not_null}
"""
)


def _required_not_null_sql() -> str:
    return " AND ".join(f"f.{c} IS NOT NULL" for c in REQUIRED_COLUMNS)


def _feature_columns_sql() -> str:
    return ", ".join(f"f.{c}" for c in FEATURE_COLUMNS)


def _to_float_row(values: tuple) -> list[float]:
    # None (NULL for an OPTIONAL_COLUMNS feature) becomes NaN, not a crash
    # or a dropped row -- same precedent as gbm.py (ADR-044).
    return [np.nan if v is None else float(v) for v in values]


def _fetch_training_rows(
    conn: psycopg.Connection, season_filter: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    needed_seasons_sql = (
        "SELECT DISTINCT f.season FROM gold.game_feature f "
        "JOIN core.game g ON g.id = f.game_id "
        f"WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL AND {season_filter}"
    )
    sql = _TRAIN_SQL_TEMPLATE.format(
        needed_seasons_sql=needed_seasons_sql,
        columns=_feature_columns_sql(),
        required_not_null=_required_not_null_sql(),
        season_filter=season_filter,
    )
    with conn.cursor() as cur:
        cur.execute(sql, {"trailing_seasons": TRAILING_SEASONS})
        rows = cur.fetchall()
    n_features = len(FEATURE_COLUMNS)
    X = np.array([_to_float_row(row[:n_features]) for row in rows], dtype=np.float64)
    baseline = np.array([float(row[n_features]) for row in rows], dtype=np.float64)
    y = np.array([float(row[n_features + 1]) for row in rows], dtype=np.float64)
    return X, y, baseline


def train(conn: psycopg.Connection) -> dict:
    """Fits an XGBoost regressor on seasons through TRAIN_SEASON_CUTOFF,
    evaluates on VALIDATION_SEASONS against the park's own trailing-average
    total (see module docstring), and only saves the model to disk if it
    beats that baseline on RMSE. Never overwrites a working model with a
    worse one silently -- same discipline as gbm.py's train()."""
    X_train, y_train, _ = _fetch_training_rows(conn, f"f.season <= {TRAIN_SEASON_CUTOFF}")
    X_val, y_val, baseline_val = _fetch_training_rows(
        conn, f"f.season IN ({', '.join(str(s) for s in VALIDATION_SEASONS)})"
    )

    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        eval_metric="rmse",
    )
    model.fit(X_train, y_train)

    model_preds = model.predict(X_val)

    def _score(preds: np.ndarray) -> dict:
        return {
            "rmse": float(root_mean_squared_error(y_val, preds)),
            "mae": float(mean_absolute_error(y_val, preds)),
        }

    model_score = _score(model_preds)
    baseline_score = _score(baseline_val)
    metrics: dict = {
        "train_rows": len(y_train),
        "validation_rows": len(y_val),
        "model": model_score,
        "baseline": baseline_score,
    }

    beats_baseline = model_score["rmse"] < baseline_score["rmse"]
    metrics["saved"] = beats_baseline
    if beats_baseline:
        MODEL_DIR.mkdir(exist_ok=True)
        model.save_model(str(MODEL_PATH))

    return metrics


def predict(conn: psycopg.Connection) -> int:
    if not MODEL_PATH.exists():
        return 0

    model = xgb.XGBRegressor()
    model.load_model(str(MODEL_PATH))

    needed_seasons_sql = (
        "SELECT DISTINCT f.season FROM gold.game_feature f "
        f"WHERE f.home_win IS NULL AND f.mlb_game_pk IS NOT NULL AND {_required_not_null_sql()}"
    )
    sql = _PREDICT_SQL_TEMPLATE.format(
        needed_seasons_sql=needed_seasons_sql,
        columns=_feature_columns_sql(),
        required_not_null=_required_not_null_sql(),
    )
    with conn.cursor() as cur:
        cur.execute(sql, {"trailing_seasons": TRAILING_SEASONS})
        rows = cur.fetchall()
        if not rows:
            return 0

        n_features = len(FEATURE_COLUMNS)
        game_pks = [row[0] for row in rows]
        X = np.array([_to_float_row(row[1 : 1 + n_features]) for row in rows], dtype=np.float64)
        baseline = [float(row[1 + n_features]) for row in rows]
        preds = model.predict(X)

        predictions = [
            (game_pk, MODEL_VERSION, float(pred), base)
            for game_pk, pred, base in zip(game_pks, preds, baseline, strict=True)
        ]
        cur.executemany(
            "INSERT INTO gold.total_prediction "
            "(mlb_game_pk, model_version, predicted_total, baseline_total) "
            "VALUES (%s, %s, %s, %s)",
            predictions,
        )
        return len(predictions)


def backfill_outcomes(conn: psycopg.Connection) -> int:
    """Fills in actual_total for any gold.total_prediction row whose game is
    now final -- the total.py-specific sibling of mlb_baseball.model's own
    backfill_outcomes(), which only ever touches gold.prediction (a
    different table, different column shape) and so can't cover this one
    too. See this module's own docstring for why gold.total_prediction is a
    separate table rather than a reused gold.prediction shape."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE gold.total_prediction p "
            "SET actual_total = (g.home_score + g.away_score) "
            "FROM core.game g "
            "WHERE g.game_pk = p.mlb_game_pk AND p.actual_total IS NULL "
            "  AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL"
        )
        return cur.rowcount


def health_check() -> list[Check]:
    checks = [check_table_has_rows("gold.total_prediction")]
    if not MODEL_PATH.exists():
        detail = f"not found at {MODEL_PATH} — run mlb train"
        checks.append(Check(f"{MODEL_VERSION} model file", False, detail))
        return checks
    checks.append(Check(f"{MODEL_VERSION} model file", True, str(MODEL_PATH)))
    # Real total runs have never been observed outside roughly 0-49 across
    # all of MLB history (confirmed directly against production) -- a
    # predicted_total wildly outside that range (negative, or in the
    # hundreds) would mean a broken feature/scale bug, not a legitimately
    # extreme game. Generous upper bound (60) leaves real headroom above
    # the observed max for a genuine outlier prediction without masking an
    # actual bug the way a tight bound calibrated to the exact historical
    # max would risk on a slightly-more-extreme future game.
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM gold.total_prediction "
            "WHERE predicted_total < 0 OR predicted_total > 60"
        )
        (bad,) = fetch_one(cur)
    if bad:
        detail = f"{bad} rows outside 0-60"
        checks.append(Check("predicted_total plausible range", False, detail))
    else:
        detail = "all computed values within 0-60"
        checks.append(Check("predicted_total plausible range", True, detail))
    return checks
