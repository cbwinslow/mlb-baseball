## Why

The owner's rule is simple: find every free, lawful data source, find everything each one offers, land all of it in organised per-source raw tables with repeatable functions, then build workflows on top. The 2026-10-05 audit (`docs/SOURCE_COVERAGE_AUDIT.md`, `docs/RAW_INVENTORY.md`) shows the project did not do this. Earlier decisions (ADR-017/018/019) skipped MLB data because another source "duplicates" it, the MLB Stats API connector is MLB-only (`sportId=1`), nobody wrote down what each source offers, and the 12.6M win-probability rows were loaded straight into the database with no saved responses (the artifact staging commit came on 2026-08-09, after the 2026-07-28/29 load), so `meta.ingestion_item` is empty and loads cannot be replayed or proven. Overlap between sources is wanted: each source stays separate in `raw` and is reconciled in `core`.

## What Changes

- **Source catalogue and data models.** One page per source (`docs/sources/<source>.md`): what it offers (endpoints, tables, years), what we store, what is missing and why, request cost, rights profile. The MLB page is built from the official Stats API OpenAPI spec once its origin and terms are verified.
- **Replayable ingestion pattern for every dataset.** Each new or re-run dataset saves the original response (compressed, checksummed, under `downloads/<source>/`), writes ledger rows (`loaded` / `unavailable` / `failed`) and loads typed raw tables from the saved artifact, so a load can be replayed with no network. Reuses `manifest.persist_artifact`, `ingest.record_items`, `replace_dataframe_scopes`.
- **MLB Stats API, pro data first.** In cost order: cheap per-season endpoints (schedule hydrates incl. weather/officials/decisions/broadcasts, extra stat groups and types, sabermetrics, splits, `highLow`, `meta` enums, draft prospects, postseason series, milestones, awards, transactions incl. trades); then the full per-game GUMBO feed (pitchData, hitData, playEvents, runners, credits, officials, weather, decisions) for all years the API has it; pre-2026 play-by-play, box scores and umpires parsed from that same feed; the 1950+ win-probability and context responses re-saved (or imported from the owner's `cbwlap1` copy after comparison).
- **Completeness of the other free pro sources**: Retrosheet (box scores hold 18k of 211k games), Chadwick register, Lahman, Statcast (per-year coverage), FanGraphs unbuilt boards, Baseball-Reference, odds/markets, plus free sources for weather and any trades/transaction history not in MLB data, each behind a rights check.
- **Minor leagues (sportId 11-16, winter, independent) and college last.** Seamheads, KBO, NPB only after a recorded rights review.
- **Bootstrap documented** in `docs/BOOTSTRAP_RUNBOOK.md` so a new person can reproduce all of it on their own server; doctor and ledger-coverage checks per new dataset; numbered migrations for new raw tables.
- **No paid providers. No new frameworks.**

## Capabilities

### New Capabilities
- `source-ingestion`: the rules every raw dataset follows (catalogue entry, saved responses, ledger, typed tables, idempotent and resumable loads, request budgets, rights gate, documented bootstrap) and the phase order for pro-first coverage.

### Modified Capabilities

(none; `odds-capture`, `source-refresh` and the connector DOX files keep their own scope and are extended only where a task says so)

## Impact

- Code: `mlb_baseball/connectors/mlb_api.py` (and a split-out feed parser module if it grows), `connectors/*` completeness work, `cli.py` (stage flags), `manifest.py`, `doctor` checks; new migrations from `0111`.
- Data: many new `raw.*` tables; large disk use (saved responses; budget set in Phase 0); long production runs, each owner-approved and logged in `pipeline-recovery/results.md`.
- Docs: `docs/sources/*`, `docs/DATA_SOURCES.md`, `docs/SOURCE_RIGHTS.md`, `docs/BOOTSTRAP_RUNBOOK.md`, regenerated `docs/RAW_INVENTORY.md`, connector `.dox.md` files, ADR superseding the "skip if redundant" parts of ADR-017/018/019.
- Rights: MLB Stats API / GUMBO / Savant stay `local_research` (owner-risk); every new source gets a row in `docs/SOURCE_RIGHTS.md` before ingest.
- Phase gate: `openspec/project.md` limits expansion work. The owner explicitly directed this change on 2026-10-05; the first task records that decision there. It must not delay `pipeline-recovery` close-out.
