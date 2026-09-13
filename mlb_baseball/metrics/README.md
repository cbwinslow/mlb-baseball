# Metric catalog entries

One YAML file per metric (`<name>.yaml`), schema-validated by
`mlb_baseball/catalog.py`'s `MetricEntry` model and loaded into the
PostgreSQL `meta.metric` table by `mlb catalog build`. See
`openspec/changes/metric-catalog/` for the full proposal/design/spec this
directory implements, and `docs/DECISIONS.md` ADR-291.

This file documents the schema **field-for-field** so it cannot drift from
`catalog.py`'s `MetricEntry` — if you change one, change the other in the
same commit.

## Fields

- `name` (required, string) — a stable, unique identifier for the metric.
  Matches the YAML filename (`<name>.yaml`) and becomes `meta.metric`'s
  primary key.
- `definition` (required, string) — plain-English, 1-3 sentences, no
  unexplained jargon. This is what a public docs-page reader sees.
- `formula` (required, string) — a pointer to the `.sql`/`.py` file that
  computes the metric, e.g. `mlb_baseball/model/framing.py::compute` (a
  `::function_name` suffix is optional and stripped when generating the
  reproducibility link below). Not the formula itself — the *code*.
- `citation` (required, string) — the formula's published source and year
  (e.g. `"FanGraphs, Guts! constants (https://www.fangraphs.com/guts.aspx)"`),
  or `"project-derived"` if there is genuinely no external citation. This
  names whose *idea* the formula is — kept separate from `data_source`,
  which names where the *numbers* come from.
- `data_source` (required, string) — the ingested `raw`/`core` table(s) the
  computed numbers are actually read from (e.g. `raw.fangraphs_guts`).
- `grain` (required, string) — the entry's unit of analysis, e.g. `season`,
  `game`, `player-season`, `career`, `team-season`.
- `layer` (required, enum: `gold` | `feat` | `model`) — which layer
  materializes this metric today.
- `complexity` (required, enum: `arithmetic` | `complex`) — `arithmetic` if
  the formula is a deterministic aggregation over already-normalized data a
  researcher could recompute by hand; `complex` if it needs an iterative
  fit, simulation, or another stochastic method.
- `implementation` (required, enum: `sql` | `sqlmesh` | `python`) — what
  actually computes the metric today. Any entry with
  `complexity: arithmetic` and `implementation: python` is a
  should-migrate-to-SQL candidate, queryable directly from `meta.metric`
  (spec: "The catalog makes SQL/Python misplacement visible, not
  re-argued") — this is a derived query, not an additional field.
- `status` (required, enum) —
  - `published`: a cited formula, correctly implemented, not yet
    independently tie-out tested against a second source.
  - `validated`: has a passing automated test that reproduces an
    independent published value within a documented tolerance. Requires
    `test_ref`.
  - `implemented-untested`: runs, produces output, no independent check
    exists.
  - `negative-result`: implemented and evaluated; did not outperform a
    documented baseline; kept for the record rather than deleted.
  - `archived`: superseded or removed.
- `visibility` (required, enum: `public` | `internal`) — `public` if the
  formula is drawn from published, citable literature, regardless of which
  directory currently implements it; `internal` only for tuned
  parameters/weights not themselves published, blended/ensembled outputs,
  ranked feature-selection results, market-disagreement research, or
  non-baseline backtest results.
- `test_ref` (optional, string; **required when `status: validated`**) — the
  specific automated test that reproduces the independent published value,
  e.g. `tests/integration/test_model_framing.py::test_...`.
- `notes` (optional, string) — known limitations, open questions, or why
  `status`/`visibility` is what it is.

## Generated, not hand-written

`source_permalink` is **not** a YAML field. `mlb catalog build`
(`catalog.py::load()`) generates it for every entry from `formula`'s file
path plus the git commit the build ran against, producing a version-pinned
GitHub blob URL — never a link to a moving branch. It is stored only on the
loaded `meta.metric` row.

## Example

```yaml
name: fangraphs_guts
definition: >
  FanGraphs' "Guts!" per-season linear-weight constants used to compute
  wOBA and FIP correctly for a given season's actual run environment,
  rather than a single fixed weight set applied to every year.
formula: mlb_baseball/sql/gold_fangraphs_guts.sql
citation: "FanGraphs, Guts! constants (https://www.fangraphs.com/guts.aspx)"
data_source: raw.fangraphs_guts
grain: season
layer: gold
complexity: arithmetic
implementation: sql
status: published
visibility: public
notes: >
  Verbatim numeric conform of FanGraphs' own published constants -- no
  re-derivation. Not yet independently tie-out tested against a second
  source, hence "published" rather than "validated" (ADR-290).
```

See `fangraphs_guts.yaml` in this directory for the real, complete entry.
