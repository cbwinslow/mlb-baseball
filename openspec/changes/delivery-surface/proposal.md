## Why

The research database has a grain-complete `gold` stat backbone but no way
for anyone outside this repo to use it. Step 6 of the restructure
(`docs/superpowers/specs/2026-09-02-project-restructure-design.md` §4.4)
is the first cut of the delivery surface: get the data out, at $0 hosting,
in the form the target analyst expects.

This is the piece that turns "a Postgres database on one machine" into "a
dataset a Retrosheet/FanGraphs/academic researcher can actually pull".

## What Changes

- **Extend, not rebuild:** the existing `mlb export` bundle path
  (`mlb_baseball/export.py`, EXPORT-01 / #123) already does rights-gated,
  manifested, multi-format (incl. Parquet) relation export with a
  `--profile` allow-list. This change adds a **`backbone` preset** (the ten
  tables below), confirms their profile eligibility, and makes the bundle
  output HF-publishable (dataset card, versioned layout). No parallel
  exporter.
- **New:** publish path to **Hugging Face Datasets** (`cbwinslow/mlb-research`
  or similar) — the canonical home for the released Parquet, versioned by
  release tag. GitHub Releases is a mirror. The HF write token is supplied
  at run time via `HF_TOKEN`; it is never committed.
- **New:** a **DuckDB-WASM static query page** (`docs/site/query/` or a
  standalone `query.html`) — loads the published Parquet and runs SQL
  entirely in the visitor's browser, no server. Published via GitHub Pages.
- **New:** **`mlb-research`** — a pybaseball-style Python package
  (`import mlb_research`) that resolves the released Parquet by version,
  caches locally, and exposes `load("<table>", season=...)` returning a
  DataFrame. Skeleton + one working table in this change.
- **New:** one **Marimo notebook recipe** answering a real analyst question
  against the released data, as the on-ramp example.
- **Docs:** a delivery section in `openspec/project.md` / the eventual docs
  site pointing at all four.

Not in this change: the MkDocs Material docs site (step 5), the remaining ≥4
notebook recipes, the r/Sabermetrics announcement, `public_safe`-keyed
variants. Those are the rest of the milestone (`openspec/project.md`
NOW → milestone).

### Data scope (first drop)

`gold.batting_game`, `gold.pitching_game`, `gold.batting_season`,
`gold.pitching_season`, `gold.batting_team`, `gold.pitching_team`,
`gold.batting_career`, `gold.pitching_career`, `gold.player_season`,
`gold.team_season`. **Excluded:** `gold.game_feature` (pregame feature
vectors, not a stat line), `gold.prediction` / model tables (frozen), and
anything `local_research`-only under `source_profiles` that can't be
published (checked at export time — a table that fails the profile gate is
skipped with a logged reason, not silently dropped).

## Capabilities

### New Capabilities
- `delivery`: how the research `gold` data is exported to Parquet,
  published to Hugging Face, queried in-browser via DuckDB-WASM, and loaded
  from the `mlb-research` Python package. Covers determinism/idempotency of
  the export, the schema manifest / dataset card, versioning by release
  tag, the source-rights gate at export time, and the package's
  version-resolution + caching contract.

### Modified Capabilities
- (none — no existing spec)

## Impact

- **Changed code:** `mlb_baseball/export.py` gains a `backbone` preset + a
  dataset-card writer; a new HF publish step (`huggingface_hub`). New:
  the `mlb-research` package (new top-level package or `packages/` dir), a
  static `query.html` (DuckDB-WASM), one `.py` Marimo notebook.
- **New dependencies:** `huggingface_hub`, `marimo` (dev/export extras);
  `duckdb` only in the `mlb-research` package + the notebook, not the main
  package. No paid service.
- **New GitHub Actions:** a Pages deploy for the query page (and later the
  docs site). A release workflow that runs the export + HF publish on a
  tag — or that stays manual/owner-run first.
- **Secrets:** `HF_TOKEN` as a repo secret (owner adds) for the automated
  publish path; the local path reads it from the environment.
- **Source rights:** the export gate must honor `mlb_baseball/source_profiles.py`
  — the backbone is Retrosheet-derived but joins conformed `core` dims;
  confirm each table's publish eligibility, don't assume.
- **Docs:** `openspec/project.md` delivery/tooling sections; `docs/PUBLIC_API.md`
  (the `mlb-research` API); `docs/SOURCE_RIGHTS.md` if the publish gate
  surfaces anything.
