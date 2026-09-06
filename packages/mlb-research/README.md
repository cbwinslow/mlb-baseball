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

## Data rights

The published dataset excludes `player_season` (Baseball-Reference) and
`team_season` (Lahman) on source-redistribution-rights grounds — see the
source repository's `openspec/changes/delivery-surface/rights-review.md`
and `docs/SOURCE_RIGHTS.md`.

## Source

[github.com/cbwinslow/mlb-baseball](https://github.com/cbwinslow/mlb-baseball)
— `packages/mlb-research/` in that repository.
