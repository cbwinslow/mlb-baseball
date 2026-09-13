## Context

See `proposal.md` — Why. Constraints that shape the approach:

- **$0 hosting.** `openspec/project.md` mandates no paid infrastructure. The
  existing `.github/workflows/pages.yml` deploys `docs/site/` to GitHub Pages as
  raw static files with **no build step**, and its header comment already says
  the MkDocs site "will land under the same `docs/site/` tree and deploy through
  this same workflow, not a second one."
- **One live asset already in `docs/site/`.** `docs/site/query/{index.html,query.js}`
  — the DuckDB-WASM query page from the delivery-surface change. It is
  hand-written, self-contained, and served at `/query/`. `mkdocs build` cleans
  its `site_dir` on every run, so a naive `site_dir: docs/site` would delete it.
- **`docs/` is mostly internal.** ~30 `docs/*.md` files are engineering docs, not
  public content. `docs/DATA_DICTIONARY.md` documents every layer
  (`raw`/`core`/`gold`/`meta`/`serve`); only its section 3 ("Grain-Complete
  Statistic Backbone") describes the ten published tables.
- MkDocs Material is already on the adopted-tools list in `openspec/project.md`.

## Goals / Non-Goals

**Goals:**

- A published docs site covering the four required pages, built with MkDocs
  Material, deployed by the existing Pages workflow.
- The query page keeps working at `/query/` with no URL change.
- The data-dictionary page has one source of truth in the repo.
- No change to any shipped runtime dependency; the docs toolchain is
  build-time only.

**Non-Goals:**

- Documenting the feature store or baseline model (Phase A v1.1, not built).
- The `understand-anything` knowledge graph (separate NOW #5 follow-up).
- The remaining example notebooks (separate v1 criterion).
- Custom theming, versioned docs (`mike`), or a search backend beyond
  Material's built-in client-side search.

## Decisions

### D1 — Source in `docs/site-src/`, build output to `docs/site/` (git-ignored)

`mkdocs.yml` at the repo root sets `docs_dir: docs/site-src` and
`site_dir: docs/site`. `docs/site/` becomes generated output and is added to
`.gitignore`; `pages.yml` runs `mkdocs build` and uploads `docs/site/`.

- **Alternative rejected — commit the built HTML.** MkDocs Material emits ~40
  files (search index, assets, per-page dirs); committing them makes every
  content edit a large, unreviewable diff and invites drift between source and
  output.
- **Alternative rejected — `docs_dir: docs/`.** Would publish every internal
  engineering doc. Curating an `exclude` list is fragile — a new internal doc
  leaks by default.
- **Alternative rejected — a second workflow that builds on a runner and
  deploys.** `pages.yml`'s comment explicitly rules this out; one workflow is
  simpler and there is only one Pages site.

### D2 — Move the query page into `docs/site-src/query/` as a static passthrough

`git mv docs/site/query docs/site-src/query`. MkDocs copies files it does not
recognise as pages (`.html`, `.js`) to `site_dir` verbatim, so
`docs/site-src/query/index.html` publishes at `/query/` unchanged. The page is
listed in the nav as a top-level entry pointing at `query/index.html`.

- **Alternative rejected — keep `query/` in `docs/site/` and merge after
  build.** Needs an extra copy step in CI and leaves a hand-maintained file in
  what is otherwise generated output.

### D3 — Data dictionary via a section snippet, not a copy or a full include

Add `<!-- --8<-- [start:backbone] -->` / `[end:backbone]` marker comments around
section 3 of `docs/DATA_DICTIONARY.md`. The site page is
`--8<-- "DATA_DICTIONARY.md:backbone"` via `pymdownx.snippets` with
`base_path: [docs]` and `check_paths: true` (a missing file or marker fails the
build). `docs/DATA_DICTIONARY.md` stays the single source; the public page tracks
its section 3 automatically.

- **Alternative rejected — include the whole file.** Publishes the internal
  `raw`/`core`/`meta`/`serve` schema.
- **Alternative rejected — generate the page from the Parquet manifest at build
  time.** Truer to the schema, but the manifest is produced by `mlb export`
  against a live DB — not available in the docs CI job. More moving parts than
  the requirement needs.
- **Alternative rejected — hand-write a second table.** Exactly the drift the
  spec forbids.

### D4 — Formulas and limitations pages: curated, citing the canonical docs

`docs/THEORY_AND_METHODOLOGY.md` (96 KB) and `docs/RESEARCH.md` (50 KB) are too
large and too internal to embed wholesale. Each site page is a curated summary —
the published metrics with formula + citation; the coverage/tolerance/scope
limitations — that ends with a link to the full canonical doc on GitHub. These
pages are content, reviewed like any doc; the drift risk is low because the
published-metric list and the honest-limitations list change rarely and are
already gated by `changes-review`.

- **Alternative rejected — section snippets like D3.** Neither source doc has a
  single contiguous "published metrics" or "limitations" section; carving one
  out is a larger edit to a heavily-cross-referenced file than writing the
  summary.

### D5 — `docs` extra in `pyproject.toml`, built with `uv`

Add `[project.optional-dependencies] docs = ["mkdocs>=1.6", "mkdocs-material>=9.5"]`.
`pages.yml` gains: checkout → `astral-sh/setup-uv` → `uv sync --extra docs` →
`uv run mkdocs build --strict` → upload `docs/site/`. `--strict` makes a broken
link or missing snippet fail CI.

- **Alternative rejected — PEP 735 `[dependency-groups]`.** The project uses
  `[project.optional-dependencies]` (`dev`, `export`); match it.
- **Alternative rejected — a standalone `pip install mkdocs-material` step.**
  `uv` + the lock file pins the toolchain; a bare `pip install` does not.

### D6 — `pages.yml` trigger paths

Change `paths` from `docs/site/**` to `docs/site-src/**`, `mkdocs.yml`, and
`pyproject.toml` / `uv.lock` (a toolchain bump must redeploy). Keep
`.github/workflows/pages.yml` in the list and `workflow_dispatch`.

### D7 — the grain-ladder diagram is a hand-authored inline SVG, not Mermaid

The proposal assumed Mermaid (via `pymdownx.superfences` + mkdocs-material's
native support). In practice that adds a runtime dependency — mkdocs-material
fetches `mermaid.min.js` from unpkg at page load and renders client-side — and
the `format: !!python/name:...` custom-fence tag also breaks the repo's plain
`check-yaml` pre-commit hook. The diagram is five boxes and four arrows; a
hand-authored inline `<svg>` using `currentColor` / `var(--md-default-fg-color)`
renders identically in light and dark, needs no JS and no network, has a real
`<title>`/`<desc>` for accessibility, and is asserted deterministically by the
docs test (SVG present with every grain label). This also lets `mkdocs.yml` use
plain `pymdownx.superfences` with no Python-tag YAML, so `check-yaml` needs no
exclusion.

- **Alternative rejected — keep Mermaid.** A CDN fetch and client-side render for
  a static five-node diagram, plus a pre-commit-hook carve-out, for no gain over
  40 lines of SVG.

## Risks / Trade-offs

- **`mkdocs build` in CI adds a failure mode to Pages deploys** → `--strict`
  locally in a task and in a pre-merge check; the build is pure static-site
  generation with a pinned toolchain, so it is deterministic. Rollback: revert
  the `pages.yml` change and the site falls back to raw static file upload.
- **`docs/site/` disappearing from git surprises anyone expecting it there** →
  the `.gitignore` entry has a comment; `proposal.md` and this file record the
  move; the `pages.yml` comment is updated.
- **The query page relies on MkDocs copying `.html` verbatim** → a
  `mkdocs build --strict` smoke check in tasks asserts
  `docs/site/query/index.html` and `query.js` exist byte-identical to the
  sources after a build.
- **Curated formulas/limitations pages can lag their canonical docs** (D4) →
  each page names its source doc and dates the summary; the lists it covers are
  slow-moving and `changes-review`-gated.
- **Snippet marker comments in `DATA_DICTIONARY.md`** are load-bearing for the
  build → `check_paths: true` + `--strict` turn a removed marker into a build
  failure, not a silent empty page.

## Migration Plan

1. Land the change on a branch; `pages.yml` does not run on branches, so the
   live site is untouched until merge.
2. On merge to `main`, `pages.yml` runs the new build-and-deploy path. The
   published site gains the docs pages; `/query/` resolves to the same content.
3. Rollback: revert the merge commit. `pages.yml` returns to raw upload of
   `docs/site/` — which means `docs/site/` must be restored; the revert does
   that because the `git mv` and `.gitignore` change are in the same commit
   range.
