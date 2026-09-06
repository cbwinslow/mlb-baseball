## Context

See `proposal.md` — Why. Constraints that shape the approach:

- **An export layer already exists.** `mlb_baseball/export.py` (EXPORT-01,
  #123): validated relation allow-list, read-only repeatable-read
  server-side-cursor streaming, CSV/XLSX/Parquet via `pyarrow`,
  `--profile public_safe` rights filtering, a manifest, and `mlb doctor`
  health checks. The `mlb export` CLI subcommand is wired.
- **$0 hosting** is a hard rule (`openspec/project.md`). No project-operated
  query backend.
- **Source rights** are a correctness requirement, not a note
  (`mlb_baseball/source_profiles.py`, `docs/SOURCE_RIGHTS.md`). The backbone
  is Retrosheet-derived but the builders join conformed `core` dims — the
  per-table profile must be checked, not assumed.
- **Repo split is deferred** (`openspec/project.md`), so `mlb-research`
  lives in this repo for now, as its own publishable package.
- Owner has a Hugging Face account and an API key.

## Goals / Non-Goals

**Goals**
- One export command produces an HF-ready bundle of the ten backbone tables.
- A visitor can query the published data from a URL with nothing installed.
- `pip install mlb-research` → `mlb_research.load(...)` returns a DataFrame.
- Every piece reuses existing infrastructure where it exists.

**Non-Goals (design-level)**
- No new streaming/serialization engine — extend `export.py`.
- No `duckdb` dependency in the main `mlb_baseball` package.
- No automated tag→publish workflow in this change (manual/owner-run
  first; the workflow is a fast follow once the manual path is proven).
- No CDN self-hosting of DuckDB-WASM assets (load from a public CDN).
- `mlb-research` is not split to its own repo here.

## Decisions

### D1 — Export: a `backbone` preset on `mlb export`, not a new tool

`export.py` already has the allow-list, the rights gate, the streaming
transaction, and Parquet output. Add:
- a named preset `backbone` = the ten tables, so `mlb export --preset
  backbone --out <dir>` writes `<dir>/<table>.parquet` for each;
- a `dataset_card.md` writer alongside the existing manifest (source,
  coverage, licence, schema version, repo + honest-limitations links);
- a stable output layout: `<dir>/data/<table>.parquet`,
  `<dir>/manifest.json`, `<dir>/README.md` (the card) — this *is* the HF
  dataset repo layout.

*Alternative considered:* a DuckDB `ATTACH postgres` + `COPY TO parquet`
exporter. Rejected — it duplicates the rights gate and the allow-list that
`export.py` already enforces, and adds `duckdb` to the main package for no
gain over `pyarrow` at this data size (~low-millions of rows per table).

### D2 — Determinism scoped to content + manifest, not file bytes

Parquet container bytes are not stable across `pyarrow` versions
(compression, dictionary encoding, row-group boundaries). The export
guarantees:
- deterministic **row content and order** (`ORDER BY` the table's primary
  key in the export query);
- a deterministic **manifest** (sorted keys, row counts, column schema);
- a recorded `built_at` timestamp — the one intentionally non-deterministic
  field.

The spec's "byte-comparable Parquet content" is read as *decoded* content
(round-trip a Parquet file to a table and compare), not `md5(file)`. The
spec text is tightened to say "decoded content" during apply.

### D3 — Publish: `huggingface_hub.upload_folder`, token from env, manual first

A thin `publish.py` (or a `mlb export --publish hf` flag) calls
`HfApi().upload_folder(folder_path=<bundle dir>, repo_id="<owner>/mlb-research",
repo_type="dataset", revision=<tag>)` with `HF_TOKEN` read from the
environment. The bundle dir from D1 is already the correct repo shape.

First runs are owner-run locally (`HF_TOKEN=... mlb export --preset backbone
--publish hf --tag vX.Y.Z`). A `release`-triggered GitHub Actions job with
`HF_TOKEN` as a repo secret is a follow-up change once the manual path is
proven — keeps the blast radius small.

*Alternative considered:* the HF `datasets` library push. Rejected —
heavier dependency, opinionated dataset schema, and we want a plain file
upload, not a `datasets`-native format.

### D4 — Query page: DuckDB-WASM, Parquet over HTTP range from HF

A single static `docs/site/query/index.html` (+ a small JS file):
- loads `@duckdb/duckdb-wasm` from jsDelivr;
- registers each backbone table as a view over its HF Parquet URL
  (`https://huggingface.co/datasets/<owner>/mlb-research/resolve/<tag>/data/<table>.parquet`)
  — HF serves Parquet with HTTP range support, so DuckDB-WASM only fetches
  the row groups a query needs;
- a `<textarea>` + Run button + a results `<table>`; errors rendered inline.

Published via a `pages` GitHub Actions workflow (the same one that will
later publish the MkDocs Material docs site — step 5).

*Alternative considered:* sql.js / a hosted read-only Postgres. Rejected —
sql.js can't read Parquet; a hosted DB costs money and invites abuse
(`openspec/project.md` rejects it).

### D5 — `mlb-research` package: `uv` workspace member, resolves by HF tag

- Location: `packages/mlb-research/` with its own `pyproject.toml`; added
  as a `[tool.uv.workspace]` member so it develops in-tree but publishes
  independently to PyPI as `mlb-research` (import `mlb_research`).
- `load(table, *, season=None, version="latest")`:
  - resolves `version` → an HF revision (a tag, or the dataset's default
    branch for `"latest"`);
  - downloads `data/<table>.parquet` via `huggingface_hub.hf_hub_download`
    (which caches under `~/.cache/huggingface` by default);
  - reads it with `duckdb` (filter pushdown for `season`) → returns a
    `pandas.DataFrame`;
  - unknown table → `ValueError` naming the bad table + listing valid ones;
  - unreachable version → a clear error, not a stack trace from deep in
    `huggingface_hub`.
- Deps: `duckdb`, `huggingface_hub`, `pandas`. Deliberately *not*
  depending on `mlb_baseball`.

*Alternative considered:* bundle the Parquet into the wheel. Rejected —
the data is far bigger than a package should be, and it couples releases.

### D6 — Notebook: Marimo, `mlb_research` only

`notebooks/01-<question>.py` (Marimo, reactive, git-clean diffs). Answers
one real question (candidate: "which pitchers had the biggest platoon
split in 2023" or "team park-adjusted offense over a decade") using only
`mlb_research.load(...)`. Runs in CI-lite as `marimo export` to catch
breakage.

## Risks / Trade-offs

- **HF Parquet range-request support changes** → the query page slows to
  full-file fetches, still works. Mitigation: table Parquet files stay
  small (partition `*_game` by decade if any single file exceeds ~50 MB).
- **`pyarrow` vs `duckdb` schema drift** (export writes with pyarrow, the
  package + page read with duckdb) → column-type mismatch. Mitigation: a
  round-trip test in the export suite (write → read back with duckdb →
  assert schema matches the manifest).
- **A backbone table turns out `local_research`-only** → it can't ship.
  Mitigation: D1's rights gate excludes it with a logged reason; the
  milestone's coverage claim is adjusted, not faked. This is a real
  possibility for `player_season` (Baseball-Reference-sourced) and
  `team_season` (Lahman) — **must be checked first in apply, task 1.**
- **`HF_TOKEN` in a shell history / CI log** → credential leak. Mitigation:
  the spec forbids it appearing anywhere; the manual path documents
  `HF_TOKEN=... cmd` (not `export HF_TOKEN`); the eventual workflow uses a
  masked repo secret.
- **`mlb-research` name taken on PyPI** → pick a fallback at publish time.
  Low risk; `mlb-research` appears free.
- **Two Python packages in one repo** adds `uv` workspace complexity.
  Accepted — it's the standard pattern and repo-split is deferred anyway.

## Migration Plan

1. Confirm each backbone table's publish profile (apply task 1). If any is
   ineligible, record it and drop it from the preset — do not block.
2. Land the `backbone` preset + dataset card (no publish yet).
3. Land `mlb-research` skeleton with one table working end to end against a
   locally-produced bundle.
4. Land the DuckDB-WASM page + Pages workflow.
5. Owner runs the first real publish (`HF_TOKEN=... mlb export --preset
   backbone --publish hf --tag v0.1.0`).
6. Point the query page + package `"latest"` at the published dataset;
   land the notebook.

Rollback: each step is its own PR; the published HF dataset can be deleted
or a version yanked without touching the repo.

## Open Questions

- **HF dataset id** — `cbwinslow/mlb-research` vs an org account. Does not
  change the specs or tasks; fill in at apply task 2. (Owner to confirm the
  exact namespace.)
- **Query-page host path** — its own `gh-pages` vs a subpath of the (later)
  MkDocs site. Deferrable; the page is self-contained either way.
