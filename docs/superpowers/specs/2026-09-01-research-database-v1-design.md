# Research Database v1 — design

**Date:** 2026-09-01
**Status:** proposed — owner reviewing
**Owner conversation:** split-the-project discussion, 2026-09-01

## Why

The repo carries three efforts at once — a data/research database, a prediction
model ladder, and an (unbuilt) website. Day-to-day this is hard to work in:
every change touches shared code and requires reading a large doc corpus, and
the actual deliverables keep not arriving. The owner's call: **finish one thing
first — the research database — and freeze the other two until it ships.**

This is not a rewrite. The ingestion pipeline works. What is missing is the
layer that makes the database *useful to an outside researcher*: getting data
out into the tools they actually use, operable housekeeping, and honest docs.

## Scope — what "v1 done" means

### In scope

**A. Export & interop layer**

- Rework `mlb export` so it takes a relation (a `raw`/`core`/`gold` table or
  view), an optional season/date filter, and writes one of: `.csv`, `.xlsx`,
  `.parquet`. No arbitrary-SQL input in v1 — a fixed allow-list of relations.
- Parquet + CSV are the whole interop story. DuckDB, SQLite, pandas, R, and
  ClickHouse all read Parquet/CSV natively — no bespoke per-database connector
  is built.
- `mlb export --profile public_safe` writes a bundle (a directory, optionally
  zipped) containing only rights-cleared relations, so a researcher can
  redistribute it. Rights come from a relation→profile map derived from
  `source_profiles.py` and `docs/SOURCE_RIGHTS.md`; anything sourced even
  partly from Statcast / MLB API / market data is excluded from the
  `public_safe` bundle.
- The current `mlb export` behaviour (rendering the daily betting briefing)
  moves to a clearly betting-named command or is frozen with the rest of the
  modeling surface — it is not the research export.
- The hardcoded `mlb dump` demo (prints a fixed Shohei Ohtani record) is
  deleted. Entity-scoped export (one player / team / game) is a filter on
  `mlb export`, not a separate command.

**B. Export views**

- Confirm analysis-ready wide views exist for the grains a researcher expects:
  game (`gold.game_export` ✓), player-season (`gold.player_season` ✓),
  team-season (`gold.team_season` ✓), division standings
  (`gold.division_standing` ✓).
- Add a player-game wide view only if it is a small lift over existing `core`
  tables; otherwise record it as fast-follow.
- Each export view gets column-level documentation with a link to its formula
  in `THEORY_AND_METHODOLOGY.md` / the named `.sql` resource.
- No new tied-out metric families in v1 (owner decision 2026-09-01). RE24 /
  wSB / FIP / wOBA at more grains and dynamic trailing windows are fast-follow.

**C. Housekeeping & operability**

- Fix issue #76 — stale serving-view migrations block a fresh database from
  initializing. An outsider cannot bootstrap until this is fixed. This is a
  bug fix, not a new command.
- No new one-off CLI commands. `mlb conform`, `mlb report`, `mlb doctor`,
  `mlb metrics`, `mlb backup` already exist and cover rebuild / health /
  operational reporting. Postgres autovacuum covers vacuum. If a genuine gap
  in an *existing* command surfaces while doing A/B/D, fix it in place; do not
  add wrappers.
- `mlb export` (the one genuinely new command) exposes `health_check()` and is
  wired into `mlb doctor`.
- Issue #74 (analytics extensions `pg_trgm` / `btree_gist` / `tablefunc`):
  deferred out of v1 unless the export work turns out to need one.

**D. Docs for a stranger**

- Rewrite `docs/USER_MANUAL.md` into an accurate "stand up and use this
  database" guide — every command shown must match the real parser.
- Reframe `README.md`: this repo is a research database; the model ladder and
  the website are separate, currently-frozen efforts.
- Extend `docs/RESEARCH_QUERY_RUNBOOK.md` with the new `mlb export` commands.

**E. Clear the board**

- Land or close the four open non-dependabot PRs (#116–#119).
- Triage every open issue: label `research-db` / `modeling` / `website`.
  Close or defer (with a comment) everything not `research-db`.

### Frozen — not deleted, not touched until v1 ships

- The `model/` prediction layer: `elo`, `gbm`, `markov`, `simulate`, `stack`,
  `neural`, `total`, `props`, `parlay`, `backtest`, `drift`, `calibrate`.
- `serve/`, `serve-api`, any Astro/website work.
- The ~150 unwired "analytics demo" CLI commands and their `model/*.py`
  modules. Wiring them to real data is real per-module validation work
  (`PACKAGE_VALIDATION_STATUS.md` found 16 real formula bugs in one review
  pass); it stays parked as its own project (Plan 06) and is resumed after
  v1, starting from the existing classification, in small reviewed batches —
  never one bulk delegation.

### Explicitly deferred

- Physical repo split. v1 is finished as a clean unit *in place*; the database
  is lifted into its own repo only after v1 is green, so the extraction cost
  is paid once against finished code.
- New tied-out metric families (see B).
- Bespoke connectors to other database engines (Parquet/CSV cover it).

## The interface question

A split forces a decision about the boundary between "the database" and "the
math." For v1 the boundary is: **the modeling layer is a consumer of `gold`,
not part of the database.** Concretely —

- The database owns `raw`, `core`, `gold` (including `gold.game_feature` and
  the point-in-time enrichment families), and every builder that writes them:
  `conform`, `report`, the enrichment `.sql` resources, and the `model/*.py`
  modules that are pure SQL-driven stat computation feeding `gold`.
- The modeling project owns the *prediction* code that reads `gold` and writes
  `gold.prediction` / `gold.total_prediction`.
- The website owns `serve.*` and the Astro app.

This line is recorded now so the eventual repo split is a move, not a redesign.

## Components touched

| Area | Files | Change |
|---|---|---|
| Export | `mlb_baseball/export.py`, `mlb_baseball/dump.py`, `cli.py` | new relation→file export; delete dump demo; rights-filtered bundle |
| Rights map | `mlb_baseball/source_profiles.py` (+ new relation map) | relation→profile lookup for `public_safe` bundle |
| Housekeeping | `migrations/`, whatever #76 touches | #76 fresh-DB init fix only — no new commands |
| Views | `migrations/` | player-game view (maybe); column docs |
| Docs | `docs/USER_MANUAL.md`, `README.md`, `docs/RESEARCH_QUERY_RUNBOOK.md`, `docs/DATA_DICTIONARY.md` | rewrite for outside user |
| Board | GitHub issues / PRs | triage + land/close |

## Data flow (export)

```
caller: mlb export <relation> [--season N] [--format csv|xlsx|parquet] [--out PATH]
  -> resolve relation (allow-list: raw.*, core.*, gold.* views/tables; reject arbitrary SQL)
  -> open READ ONLY, REPEATABLE READ transaction
  -> stream rows (server-side cursor) -> writer (csv | openpyxl | pyarrow)
  -> write file, print path + row count

caller: mlb export --profile public_safe --out DIR
  -> for each relation in RELATION_RIGHTS where profile allows public_safe:
       export to DIR/<schema>.<relation>.parquet
  -> write a MANIFEST.json (relation, rows, source-rights note, generated_at)
  -> optional --zip
```

## Error handling

- Unknown / disallowed relation → clear error naming the allow-list, non-zero
  exit. No arbitrary SQL execution path.
- Missing optional dependency (`openpyxl`, `pyarrow`) → explicit message
  ("install the `export` extra"), not a raw ImportError.
- Empty result set → write the file with headers, exit 0, print "0 rows".
- `public_safe` bundle: if a relation in the rights map does not exist in the
  database, skip it with a logged warning; do not abort the whole bundle.
- Excel row limit (1,048,576) → refuse `.xlsx` for an over-limit relation with
  a message pointing at `.parquet` / `.csv`; do not silently truncate.

## Testing

- `tests/integration/` — real `mlb_test` Postgres. Load fixture rows into a
  `gold` view, export each format, read the file back, assert row/column
  parity. Re-run: same output (idempotent).
- `public_safe` bundle test: seed one public-safe and one restricted relation,
  assert the restricted one is absent from the bundle and the manifest.
- `tests/unit/` — relation allow-list parsing, rights-map lookup, the Excel
  row-limit guard, missing-dependency message.
- CLI-dispatch test through `cli.main([...])` and real argparse for every new
  subcommand / flag (repo rule).
- `mlb doctor` gains a check per new command; `tests/` covers the check.

## Workstreams (parallelizable)

1. **WS1 — export & interop (A).** Largest. Bounded and mechanical enough to
   delegate to Agy against this spec + a detailed task brief; Claude writes the
   brief and reviews the diff.
2. **WS2 — housekeeping (C).** Issue #76 fresh-DB init fix only. Claude or a
   Claude subagent.
3. **WS3 — docs (D).** After WS1 lands the command surface, so the manual is
   accurate.
4. **WS4 — board triage + PR landing (E).** Claude, in parallel from the
   start.

## Acceptance

- `mlb export` writes correct CSV / XLSX / Parquet from any allowed relation,
  round-trip verified, idempotent, dispatch-tested, doctor-checked.
- `mlb export --profile public_safe` produces a bundle with zero restricted
  data and a manifest, verified by test.
- A fresh `mlb_test` database initializes clean (#76 closed).
- `docs/USER_MANUAL.md` commands all run as written against a clean bootstrap.
- Every open issue is labelled; non-`research-db` issues are closed or deferred
  with a comment; PRs #116–#119 are landed or closed.
- The frozen surface is untouched by this work.
