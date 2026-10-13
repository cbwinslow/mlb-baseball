# Tasks

Tags: **[auto]** the agent can finish and test it alone; **[owner]** needs an owner decision, approval or credential; **[measure]** code is done, proof needs elapsed time on production. A goal-seek run works only `[auto]` tasks and stops at the first other tag. Production `mlb` writes need owner approval at the step and a `changelog/` entry. Parity comparisons run on scratch tables in a disposable database, never against production tables.

## 1. Spike and gate (no production change)

- [x] 1.1 [auto] Add `dlt` (range `>=1.21,<2`, no database extras) to `pyproject.toml` and `uv.lock`; verify `uv run python -c "import dlt"` works and the unit suite still passes.
- [x] 1.2 [auto] Spike the custom destination: a `dlt` resource feeding a project-owned destination that writes one ledger item's rows and its `meta.ingestion_item` row in one transaction (`max_parallel_load_jobs=1` or `batch_size=0` file jobs); verify with a real-PostgreSQL test that a mid-item failure leaves neither rows nor ledger row, and a second run writes nothing.
- [x] 1.3 [auto] (not needed, 1.2 passed) If 1.2 fails, build the fallback (`pipeline.extract()` and `normalize()` only, our loader reads the load-package files, one transaction per item) and verify the same two tests.
- [x] 1.4 [auto] Benchmark `dlt` overhead per batch against the current Polymarket price loader on recorded payloads (no network); record rows/s for both in `results.md`.
- [x] 1.5 [owner] (accepted 2026-10-13 with the Opus review changes D6, D9, D10 below) Decision gate on `results.md`: accept the hand-off (1.2 or 1.3), the overhead from 1.4, and the migration order in design D7. Approves writing the ADR that supersedes ADR-300.

## 2. Layer scaffolding

- [ ] 2.0 [auto] Destination rules D10: pipeline per item or abort-before-run, many items per transaction with a ledger row each, landing policies incl. zero-row item, rows inserted counted, provenance fields filled; verify a test per rule plus a run-twice test per policy and a leftover-package test with a shared state folder.
- [ ] 2.0b [auto] Type contract D9: `ingest_layer/types.py` pyarrow schemas from `market_store`, schema-vs-`information_schema` test, polars cast with empty-to-NULL and reject rows, empty-versus-NULL CSV quoting test.

- [ ] 2.1 [auto] Create `mlb_baseball/ingest_layer/` with the `Downloader`, `Loader` and `Check` Protocols, the custom destination and the per-table landing policy list (scoped replace, append-only typed, upsert, truncate-and-reload) reusing `load.py`, `market_store.py`, `manifest.py`, `ingest.py`; verify unit tests per policy and that nothing outside `ingest_layer/` imports its internals.
- [ ] 2.2 [auto] Configure `dlt` for `direct` naming, no nesting, no `_dlt_*` objects in `raw`/`core`/`gold`, state under `~/.mlb/dlt`; verify a test that lists schemas after a run and finds no `_dlt_*` table, and a test that deletes the state directory and resumes without duplicates (spec: tool state is lost).
- [ ] 2.3 [auto] Add a `mlb doctor` line for the `dlt` state directory (informational, never failing) and a `schema-watch` check that a new source field is landed as text and reported; verify with tests.
- [ ] 2.4 [auto] Write the connector contract for the staged layer into `docs/ARCHITECTURE.md` and a `.dox.md` for `ingest_layer/`; verify `python scripts/check_dox.py` passes.
- [ ] 2.5 [owner] Approve the ADR text superseding ADR-300 and the Timescale-for-market-data ADR; then add both to `docs/DECISIONS.md` and cite their numbers in `design.md`.

## 3. Market sources (Polymarket, Kalshi)

- [ ] 3.1 [auto] Polymarket price history on the staged layer (typed tables from `stabilize-and-market-store`); parity test against the old loader on a recorded token range into scratch tables; results in `results.md`; sidecar updated.
- [ ] 3.2 [auto] Kalshi candles the same way, including the duplicate (ticker, ts) handling; parity test and sidecar.
- [ ] 3.3 [auto] Polymarket and Kalshi catalogs and snapshots (cursor paging via `dlt`); parity test and sidecar.
- [ ] 3.4 [owner] Switch the market sources to the new path in production behind the setting (after the typed-table swap in `stabilize-and-market-store`); changelog entry.
- [ ] 3.5 [measure] 7 scheduled runs without a failure the old path would not have had.
- [ ] 3.6 [owner] Retire the old market loader code, tests and docs.

## 4. Simple file sources (register, lahman)

- [ ] 4.1 [auto] `register` and `lahman` on the staged layer reading `manifest`-kept files; parity test on the full files into scratch tables; sidecars.
- [ ] 4.2 [owner] Switch, then [measure] 7 runs, then [owner] retire (one step per source).

## 5. Retrosheet family

- [ ] 5.1 [auto] `retrosheet`, `retrosheet_gamelog`, `retrosheet_schedule`, `retrosheet_roster`, `retrosheet_transaction`, `retrosheet_reference`, `retrosheet_box` on the staged layer, one source per task, each with parity test and sidecar; the unchanged-archive skip from `stabilize-and-market-store` is kept.
- [ ] 5.2 [auto] `retrosheet_event` with the Chadwick parse as the step between download and load (ADR-299 unchanged); parity on one decade archive.
- [ ] 5.3 [owner] Switch, [measure] 7 runs, [owner] retire (one source per step).

## 6. Scraped and API sources

- [ ] 6.1 [auto] `statcast`, `statcast_leaderboard`, `bref`, `fangraphs` (keeping the ADR-288 user-agent exemption in its download stage) and `news`, one source per task with parity test and sidecar.
- [ ] 6.2 [owner] Switch, [measure] 7 runs, [owner] retire (one source per step).

## 7. mlb_api, by endpoint family

- [ ] 7.1 [auto] Split `mlb_api.py` by endpoint family (schedule and standings; roster, transactions and draft; live games and game detail; reference and personnel; analytics) without behavior change, one family per task, each with parity test; the 5-minute tick keeps its hourly/hash rules.
- [ ] 7.2 [owner] Switch, [measure] 7 runs, [owner] retire (one family per step).

## 8. Close-out

- [ ] 8.1 [auto] Update `docs/DATA_SOURCES.md` and every migrated source's sidecar so no document describes a retired path; verify `scripts/check_dox.py` and a repo search for the removed names.
- [ ] 8.2 [owner] Fold or archive the changes this supersedes (the `dlt` pilot task in `stabilize-and-market-store`, parts of `pipeline-recovery`, `odds-bulk-history`, `odds-history-capture`, `job-retries-alerts`), one at a time.

## Workflow follow-up

- Archive the change after every source is retired and the owner approves.
- Verify the archived result.
