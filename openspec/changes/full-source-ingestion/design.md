## Context

Evidence (read-only, 2026-10-05): `docs/SOURCE_COVERAGE_AUDIT.md` and the generated `docs/RAW_INVENTORY.md` (148 raw tables, exact counts). The MLB connector (`mlb_baseball/connectors/mlb_api.py`, 3,125 lines) is MLB-only and keeps ~17 plate-appearance fields from play-by-play, 2026 onward. Win probability, game context and linescore go back to 1950 but their responses were not saved, so the ledger (`meta.ingestion_item`) is empty and the existing completeness check (`_analytics_season_complete`) correctly refuses a raw-only load. Existing building blocks to reuse: `manifest.persist_artifact`, `ingest.record_items`, `replace_dataframe_scopes`, `track_run`, the staged `--stage analytics` backfill with workers, and `replay_analytics`.

## Goals / Non-Goals

**Goals**
- Everything free and lawful that each source offers is stored, source-faithful, replayable and documented. Pro data before minors/college.
- One repeatable pattern for all datasets, so adding a dataset is a table + a parser, not a new framework.

**Non-Goals**
- No paid providers. No dbt/Airflow/etc. No core/gold reconciliation of the new data in this change (separate changes per dataset family). No model use of new fields (admission rules stay in `model-readiness-audit`).

## Decisions

**D1. Save the response, then parse.** Each fetch writes a gzip artifact (NDJSON batches for per-game calls, one file per season for per-season calls) via `persist_artifact`, a ledger row with path + sha256, and only then loads typed rows from that artifact. Replay = read artifacts, verify checksums, load. This is the existing analytics pattern; it is generalised, not replaced.

**D2. One feed call per game for the rich MLB data.** The GUMBO feed (`/api/v1.1/game/{pk}/feed/live`) contains plays, pitch events, hit data, runners, credits, boxscore, officials, weather, decisions. Fetch it once per game, save it, and parse several raw tables from the one artifact (`raw.mlb_feed_*`), rather than calling playByPlay, boxscore and others separately. The existing 2026 tables (`raw.mlb_playbyplay`, `raw.mlb_boxscore_*`, `raw.mlb_umpire`) keep their writers unchanged; the new tables are separate raw tables, so no dual-writer problem arises (different tables, different endpoint). Whether to later extend the old tables' years is decided after parity evidence (task 5.x).

**D3. Year ranges are probed, not assumed.** Each endpoint gets a recorded probe (first year with real values, not empty shells) before its backfill range is fixed. The research agent found pitch-level keys exist for 1950-2007 but may be empty placeholders; the probe decides whether pre-2008 pitch rows are loaded.

**D4. Cost order and budgets.** Phase 1 (per-season endpoints) ~hundreds of calls; Phase 2 (feed) ~185k calls for 2008-2025, ~75k more to reach 1950; Phase 3 analytics re-save ~325k calls if the `cbwlap1` copy cannot be used. Each phase declares concurrency (config `analytics_workers` pattern) and a per-second rate, and runs resumable per season in the background after owner approval.

**D5. `cbwlap1` copy is evidence first.** The owner's other machine (PostgreSQL 17, port 5433, LAN/ZeroTier) may hold the win-probability data. Dump the relevant tables over rsync into a scratch database (never `mlb`), compare keys/counts/values with `raw.mlb_win_prob`, and only then decide whether it can seed anything. Rows without saved responses still cannot satisfy the artifact-backed ledger contract; a copy can avoid re-fetching only if its source JSON exists there.

**D6. Rights.** MLB terms prohibit automated collection (`docs/SOURCE_RIGHTS.md`): MLB-owned sources stay `local_research`, owner-risk, with the existing profile guard. New sources get a rights row before ingest; unverified sources (Seamheads, KBO, NPB, any weather/odds site) are blocked until reviewed.

**D7. Documentation is part of the pattern.** `docs/sources/<source>.md` (offers vs stored), `docs/RAW_INVENTORY.md` (generated, `mlb inventory --markdown`), connector `.dox.md`, and `docs/BOOTSTRAP_RUNBOOK.md` change in the same PR as the code.

**D8. Table naming and migrations.** `raw.<source>_<dataset>`; each dataset family is one numbered migration (from `0111`) created before its loader. Raw keeps source field names where practical; every row carries `_season` (or a scope column), `_loaded_at`, and a link to its ledger item.

## Risks / Trade-offs

- Disk: saved feeds for ~200k games could reach tens of GB. Phase 0 measures one season and sets a budget; artifacts are gzip; storage is on `/mnt/storage` (840 GB free).
- API load and terms: heavy automated calls against a source whose terms restrict bots. Mitigation: conservative rate, owner-approved runs, local_research only, no redistribution.
- Scope creep versus `pipeline-recovery`: this change must not block recovery close-out; production runs are scheduled outside the nightly window and one at a time.
- Parser fragility across eras (fields appear/disappear by year): the field table per year in the source page is the contract; unknown keys are kept in the saved artifact, so nothing is lost.

## Migration Plan

New tables only (additive migrations), loaded by new stages. Existing tables and writers are unchanged. Rollback = stop the stage; tables can be dropped or left empty; artifacts are kept. Production runs are logged with command, database, time and result.

## Open Questions

- Does `cbwlap1` hold the original response JSON, or only parsed rows? (decides D5)
- Origin and terms of `mlb-statsapi-spec.json` (committed to the repo only after verification).
- Which free sources for weather, historical odds and trades are lawful (research task in Phase 4, rights row first).
- Pre-2008 feed years: worth loading if pitch data is empty? (D3 probe)
