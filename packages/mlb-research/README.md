# mlb-research

A pybaseball-style Python loader for the [MLB Research Statistic
Backbone](https://huggingface.co/datasets/cbwinslow/mlb-research) dataset —
grain-complete batting and pitching box-score, season, team-season, and
career statistics, computed from Retrosheet play-by-play data (1910+) and
published as versioned Parquet on Hugging Face.

## Install

```bash
pip install mlb-research
```

## Usage

```python
import mlb_research

df = mlb_research.load("batting_season", season=2023)
print(df.head())
```

`load(table, *, season=None, version="latest", repo_id="cbwinslow/mlb-research")`:

- `table` — one of `mlb_research.BACKBONE_TABLES` (`batting_game`,
  `pitching_game`, `batting_season`, `pitching_season`, `batting_team`,
  `pitching_team`, `batting_career`, `pitching_career`). Raises `ValueError`
  naming the bad table and listing valid ones for anything else.
- `season` — optional row filter, pushed down via DuckDB.
- `version` — a released tag (e.g. `"v0.1.0"`), or `"latest"` (default) for
  the dataset's current revision. An unreachable version raises a
  `RuntimeError` wrapping the underlying cause.
- Downloaded Parquet is cached (both in-process and on disk via
  `huggingface_hub`) — a repeat `load()` of the same table+version does no
  network I/O.

This package is deliberately standalone: it does not depend on the
`mlb-baseball` ingestion pipeline or a database connection of any kind.

## Point-in-time features

`get_historical_features(entity_df, features, *, timestamp_col="event_timestamp", feature_version="v1", db=None)`
assembles leakage-free training rows from a DuckDB feature store (built by
`mlb build` — default `~/.mlb/mlb.duckdb`, override with `db=` or
`$MLB_DUCKDB_PATH`):

```python
import mlb_research as mr

entities = [
    {"player_id": 592450, "event_timestamp": "2023-06-01T18:00:00"},
    {"player_id": 605141, "event_timestamp": "2023-06-01T18:00:00"},
]
X = mr.get_historical_features(
    entities,
    ["player_form:obp_30d", "player_form:k_pct_shrunk_30d"],
)
```

- `features` — `"view:feature"` strings. Views: `player_form`, `pitcher_form`
  (keyed by `player_id`), `game` (keyed by `game_pk`). An unknown view or
  feature raises `ValueError` listing what is available.
- `entity_df` — a `DataFrame` or list of dicts carrying `timestamp_col` plus
  the entity-key column each requested view needs.
- Returns one row per input row, in input order. Each value is
  `ASOF`-joined on `decision_time >= visible_ts`; no qualifying row → the
  feature is missing (never forward-filled, never zero). No database server
  is involved — the DuckDB file is read directly.

Copies [Feast](https://docs.feast.dev/)'s call shape and vocabulary, not its
framework. See `docs/FEATURE_STORE.md` in the source repo for the full
contract, the four clocks, and the `mlb verify` leakage checks.

## Backtesting

`mlb_research.backtest` is a model-agnostic walk-forward evaluation harness:
numpy + pandas only, no `sklearn`/`xgboost` import, no database connection.
Model fitting is a caller-supplied `fit_fn` / `predict_fn` pair, so any
library — or a hand-written estimator — becomes the *caller's* dependency,
never this package's.

```python
time_ordered_folds(test_periods, *, key="season") -> tuple[Fold, ...]

run_backtest(
    frame: pd.DataFrame,             # one row per evaluation unit
    folds: Sequence[Fold],           # from time_ordered_folds(...)
    fit_fn: Callable[[pd.DataFrame], Model],
    predict_fn: Callable[[Model, pd.DataFrame], np.ndarray],
    *,
    task: Literal["classification", "regression"],
    time_col: str,                   # the cutoff timestamp column
    label_col: str,
    feature_cols: Sequence[str],
    period_col: str | None = None,   # defaults to time_col
    required_cols: Sequence[str] = (),
    seed: int = 0,
) -> BacktestResult

paired_comparison(pred_a, pred_b, y, keys_a, keys_b) -> dict[str, Any]
```

**The `fit_fn` / `predict_fn` contract:** each fold's `train`/`test` frames
are strictly time-ordered slices of `frame` (train is everything at or
before the fold's cutoff; test is the next period) — a random split is not
expressible. Both callbacks receive `pandas.DataFrame`s, not numpy matrices,
so a caller keying on a row's identity, or a sequential model that needs to
walk `test` in `time_col` order (predicting from its state *before* folding
each row's own outcome in — the shape Elo-style ratings need), has what it
needs. A plain `sklearn` caller does `df[feature_cols].to_numpy()` in its own
two-line callback. `run_backtest` scores every fold with numpy log loss /
Brier / accuracy / calibration (classification) or MAE / RMSE / residual
calibration (regression), plus bootstrap 95% CIs — probability quality, not
accuracy alone.

**A plain sklearn callback:**

```python
import numpy as np
import pandas as pd
from mlb_research import backtest
from sklearn.linear_model import LogisticRegression

# One row per game; `season` is the period column, `event_ts` the cutoff.
frame = pd.DataFrame(...)  # season, event_ts, feature_a, feature_b, home_win


def fit_fn(train: pd.DataFrame) -> LogisticRegression:
    model = LogisticRegression()
    model.fit(train[["feature_a", "feature_b"]].to_numpy(), train["home_win"].to_numpy())
    return model


def predict_fn(model: LogisticRegression, test: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(test[["feature_a", "feature_b"]].to_numpy())[:, 1]


folds = backtest.time_ordered_folds((2016, 2017))
result = backtest.run_backtest(
    frame, folds, fit_fn, predict_fn,
    task="classification", time_col="event_ts", period_col="season",
    label_col="home_win", feature_cols=("feature_a", "feature_b"),
)
print(result.aggregate)  # {"rows": ..., "log_loss": ..., "brier": ..., "accuracy": ...}
```

**A no-sklearn, stateful callback** (the shape a sequential model like Elo
needs — this package never imports `sklearn`; only the caller's own code
does, and here it doesn't need to at all):

```python
import numpy as np
import pandas as pd
from mlb_research import backtest

frame = pd.DataFrame(...)  # season, event_ts, home_team, away_team, home_win


def elo_fit(train: pd.DataFrame) -> dict[int, float]:
    ratings: dict[int, float] = {}
    for row in train.itertuples():
        ratings.setdefault(row.home_team, 1500.0)
        ratings.setdefault(row.away_team, 1500.0)
        expected = 1.0 / (1.0 + 10 ** ((ratings[row.away_team] - ratings[row.home_team]) / 400))
        delta = 20 * (row.home_win - expected)
        ratings[row.home_team] += delta
        ratings[row.away_team] -= delta
    return ratings


def elo_predict(state: dict[int, float], test: pd.DataFrame) -> np.ndarray:
    ratings = dict(state)  # never mutate the fitted state
    predictions = []
    for row in test.itertuples():  # run_backtest guarantees time_col order
        ratings.setdefault(row.home_team, 1500.0)
        ratings.setdefault(row.away_team, 1500.0)
        expected = 1.0 / (1.0 + 10 ** ((ratings[row.away_team] - ratings[row.home_team]) / 400))
        predictions.append(expected)  # predict *before* this row's own update
        delta = 20 * (row.home_win - expected)
        ratings[row.home_team] += delta
        ratings[row.away_team] -= delta
    return np.array(predictions, dtype=np.float64)


folds = backtest.time_ordered_folds((2016, 2017))
result = backtest.run_backtest(
    frame, folds, elo_fit, elo_predict,
    task="classification", time_col="event_ts", period_col="season",
    label_col="home_win", feature_cols=(),
)
print(result.aggregate)
```

## Data rights

The published dataset excludes `player_season` (Baseball-Reference) and
`team_season` (Lahman) on source-redistribution-rights grounds — see the
source repository's `openspec/changes/delivery-surface/rights-review.md`
and `docs/SOURCE_RIGHTS.md`.

## Source

[github.com/cbwinslow/mlb-baseball](https://github.com/cbwinslow/mlb-baseball)
— `packages/mlb-research/` in that repository.
