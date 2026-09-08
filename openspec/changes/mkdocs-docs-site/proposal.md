## Why

`openspec/project.md` lists a published **MkDocs Material docs site** (data
dictionary, grain-ladder diagram, formula citations, honest-limitations page) as
NOW item #5 and as one of the "v1 is done when" criteria. It is the last
unshipped piece of v1's researcher-facing surface: the Parquet export, Hugging
Face dataset, PyPI loader, and DuckDB-WASM query page all exist, but a first-time
visitor still has no single documented entry point that explains what the data
is, at what grain, computed how, and with what limitations.

## What Changes

- Add a MkDocs Material site whose **source** lives in a new `docs/site-src/`
  tree and whose **build output** goes to `docs/site/` (`mkdocs build`'s
  `site_dir`), so the existing `pages.yml` GitHub Pages workflow deploys it —
  no second workflow, matching the note already in `.github/workflows/pages.yml`.
- Move the existing hand-written DuckDB-WASM query page from `docs/site/query/`
  to `docs/site-src/query/` so `mkdocs build` carries it through verbatim as a
  static asset instead of `site_dir` cleaning wiping it. Its published URL
  (`/query/`) is unchanged.
- `docs/site/` becomes generated output and is git-ignored; `pages.yml` gains a
  build step (`uv sync` the docs group, `mkdocs build`) and its trigger paths
  move from `docs/site/**` to `docs/site-src/**` + `mkdocs.yml`.
- Site content (four required pages plus an index):
  - **Data dictionary** — the ten published backbone tables, their grains,
    columns, source, null policy. Single source of truth stays
    `docs/DATA_DICTIONARY.md`; the site page includes it via a snippet so the
    two never drift.
  - **Grain ladder** — a Mermaid diagram of game → season-stint →
    season-combined → team-season → career, with the "rates recomputed from
    numerators/denominators, never averaged" rule stated.
  - **Formula citations** — every published metric with its formula and the
    published source it is cited to (Tango/`The Book`, Retrosheet, FanGraphs,
    Baseball-Reference), sourced from `docs/THEORY_AND_METHODOLOGY.md`.
  - **Honest limitations** — coverage gaps, known tie-out tolerances,
    regular-season-only scope, "missing is not zero", no future-data guarantee
    only for the feature store (not yet shipped). Sourced from
    `docs/RESEARCH.md`'s honest-limitations content, which the HF dataset card
    already links to.
  - **Index** — what `mlb-research` is, install line, links to the HF dataset,
    the query page, and the repo.
- Add `mkdocs` + `mkdocs-material` to a new `docs` dependency group in
  `pyproject.toml` (MkDocs Material is already on the adopted-tools list in
  `openspec/project.md`).

Out of scope (separate follow-ups): the `understand-anything` knowledge graph
also named in NOW #5; the ≥4 remaining example notebooks (a distinct v1
criterion); any docs content for the feature store / baseline model (Phase A
v1.1, not yet built).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `delivery`: adds one requirement — the delivery surface includes a **published
  documentation site** that a visitor can read without cloning the repo,
  covering the data dictionary, the grain ladder, cited formulas, and honest
  limitations, deployed at $0 hosting cost through the same static Pages
  workflow as the query page.

## Impact

- **New:** `mkdocs.yml`, `docs/site-src/` (index + 4 pages + moved query page),
  `docs` dependency group in `pyproject.toml` (+ `uv.lock`).
- **Changed:** `.github/workflows/pages.yml` (build step + trigger paths),
  `.gitignore` (`/docs/site/`), `openspec/project.md` (NOW #5 / v1 criterion
  marked done), `docs/DATA_DICTIONARY.md` / `docs/THEORY_AND_METHODOLOGY.md` /
  `docs/RESEARCH.md` only if a snippet anchor comment must be added.
- **Moved:** `docs/site/query/{index.html,query.js}` →
  `docs/site-src/query/`. Published URL unchanged.
- **No** production code, database, connector, or model change. No new runtime
  dependency for the shipped package — the `docs` group is build-time only.
- **CI:** `pages.yml` only runs on push to `main`; a branch build is not
  triggered, so the deploy path is exercised only at merge.
