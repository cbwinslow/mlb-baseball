# MLB Research

A free, commercially-usable ([AGPL-3.0](https://github.com/cbwinslow/mlb-baseball/blob/main/LICENSE)),
**honest** MLB research database: a clean grain ladder of standard and advanced
statistics, event-derived back to 1910, every formula cited to its source, every
accuracy and leakage limitation documented.

## Get the data

```bash
pip install mlb-research
```

```python
import mlb_research

batting = mlb_research.load("batting_season", season=2023)
```

The published tables are Parquet files on Hugging Face; the loader downloads and
caches them locally. No database, no cloned repository.

- **Dataset:** [huggingface.co/datasets/cbwinslow/mlb-research](https://huggingface.co/datasets/cbwinslow/mlb-research)
- **Run SQL in your browser:** [Run SQL](query/index.html) — DuckDB-WASM against
  the published Parquet, nothing server-side.
- **Source:** [github.com/cbwinslow/mlb-baseball](https://github.com/cbwinslow/mlb-baseball)

## What's documented here

| Page | What it covers |
| --- | --- |
| [Data dictionary](data-dictionary.md) | Every published table, its grain, its columns, its source, its null policy |
| [Grain ladder](grain-ladder.md) | How game, season, team, and career figures relate — and why rates are recomputed, never averaged |
| [Formulas & citations](formulas.md) | Every published metric with its formula and the source it is cited to |
| [Honest limitations](limitations.md) | Coverage boundaries, tie-out tolerances, regular-season-only scope, "missing is not zero" |

## What this is not

This site documents the **public research database**. Tuned prediction models,
novel metrics still in validation, and betting research are a separate internal
product and are not published here. See the project's
[phased ladder](https://github.com/cbwinslow/mlb-baseball/blob/main/openspec/project.md).
