# Tasks

Tags: **[auto]** agent can finish and test alone; **[owner]** needs owner approval or a production write; **[measure]** needs elapsed time. Production writes need approval at the step, a backup, and a `changelog/` entry. Scratch work uses `mlb_test` (free) or `cbwsff1`.

## 1. Lahman and register (done in scratch)

- [x] 1.1 [auto] Schemas proposed from the real files and committed; real Lahman 2025 and register landed typed in `mlb_test`; value-by-value comparison against production (results in `dlt-ingestion-layer/results.md`).
- [ ] 1.2 [auto] Reader inventory for the 31 Lahman/register tables (conform SQL, reports, export, health, mlb_api, field census, coverage, migrations 0002 and later): list each query touching a retyped column and fix it; verify the existing integration tests (`test_conform`, `test_report*`, `test_health`, lahman/register load tests) pass on typed tables.
- [ ] 1.3 [auto] `ingest_layer` swap tool: load `<t>__new`, compare, rename in one transaction, keep `<t>__old`; tested twice (second run changes nothing).
- [ ] 1.4 [owner] Backup the 31 tables, then swap on production (approval at the step); changelog entry; `<t>__old` kept.
- [ ] 1.5 [owner] Approve dropping the `__old` tables after a clean week.

## 2. Inventory and rehearsal for the rest

- [ ] 2.1 [auto] Run `infer.py` read-only over every other `raw` table on production (sampled for the big ones, full scan to verify), write proposed schemas, list columns the guess cannot settle.
- [ ] 2.2 [auto] Set up the `cbwsff1` rehearsal target (Postgres with the needed extensions in Docker), document it, restore a small family from a dump and time it.
- [ ] 2.3 [owner] Review the proposed schemas table family by table family (overrides listed).
- [ ] 2.4 [auto] Reader inventory per family before each swap (design D7).

## 3. Families, one per step (each: schema, reader fixes, rehearsal on cbwsff1, parity, owner swap)

- [ ] 3.1 Small API/file tables (`mlb_*` small, `bref`, `fangraphs`, `news`, `retrosheet_*` reference).
- [ ] 3.2 `statcast_pitch` and leaderboards.
- [ ] 3.3 `retrosheet_plays`, `retrosheet_event`, `retrosheet_batting/fielding/pitching/gamelog`.
- [ ] 3.4 Polymarket and Kalshi: follow `stabilize-and-market-store`.

## Workflow follow-up
- Archive after every family is retyped and the owner approves.
