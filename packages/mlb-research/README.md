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

## Data rights

The published dataset excludes `player_season` (Baseball-Reference) and
`team_season` (Lahman) on source-redistribution-rights grounds — see the
source repository's `openspec/changes/delivery-surface/rights-review.md`
and `docs/SOURCE_RIGHTS.md`.

## Source

[github.com/cbwinslow/mlb-baseball](https://github.com/cbwinslow/mlb-baseball)
— `packages/mlb-research/` in that repository.
