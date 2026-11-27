# Independent architecture review (Opus 5.5, 2026-10-12)

Read-only review requested by the owner, who asked that the existing ADRs not bind it. Saved here as evidence for `design.md`; it is a point-in-time review, not governing truth. Tags: **[V]** checked by the reviewer (file, log or read-only query); **[A]** assumption. The main session re-checked these: nightly run time and exit code, 690 GB free on `/mnt/storage`, ClickHouse 25.8, raw text-column count (4,897 of 5,049). Everything else below is the reviewer's own labelled claim.

## Bottom line
The pipeline is slow and fragile mainly because it rewrites history it already has, every night and every 5 minutes. The disk and text columns are not the main cause. Fix that, compress the two market tables inside Postgres with Timescale, then move the feature math one family at a time. ClickHouse, Prefect, Redis, Alembic and a dlt migration are not needed now.

## Corrections to the evidence the reviewer was given
- Nightly takes about 3 h 43 min (2026-10-11): update 18, conform 82, report 15, predict 50, coverage 35, repair dry-run 23 min. rc=1 on 10-08, 10-10, 10-11; on 10-09 the process died partway through `update` with no finished line.
- Conform roughly doubled in a week (build_plays 1457 s to 2521 s; build_pitches 900 s to 2065 s) right after `core.pitch` was widened to 118 columns (migration 0117, 2026-10-10).
- About 21k lines of real SQL, not 65k (44k is the committed schema dump `backups/mlb_schema_20260807.sql`).
- Text columns are almost all in `raw` (4,897 of 5,049); `core` 114/416 and `gold` 42/755 are mostly typed.
- `/mnt/storage` has 690 GB free; all six disks spin (5-disk RAID5 plus a root disk).
- Local ClickHouse is 25.8 LTS (langfuse's container runs 24.3). `docs/CLICKHOUSE_DECISION.md` (2026-08-06) decided against ClickHouse without measuring a ClickHouse side.
- Prototype `mlb-quant`: BaseRuns uses `C = 3*outs` (correct is `C = outs`: 5.96 not 3.738 for its test game); docker-compose has empty values; the handoff's "25 GB WAL" and "45 min to 15 s" figures are unmeasured.

## Verdicts
- **Sabermetrics package (pure Polars + tests):** feasible, high value, about 1 week for core formulas (wOBA/FIP from Guts constants, BaseRuns with correct C, RE24/WE builders, LI), tested against FanGraphs/B-Ref golden values. Keep joins/aggregations in SQL/DuckDB. Real maintainability problem: 51 SQL files read `raw.retrosheet_event`/`raw.statcast_pitch` directly and only 9 read `core.play`/`core.pitch`, so parsing is repeated (the framing bug at `catcher_framing_csae_update.sql:36-38`). Polars is not installed in the venv; DuckDB 1.5.5 is.
- **DuckDB feature store replacing `gold.game_feature`:** right direction, 6-10 weeks done family by family. `~/.mlb/mlb.duckdb` (2.9 GB) already has `feat.game`, `feat.player_form`, `feat.pitcher_form`. Today `features.py:32` TRUNCATEs then 35 UPDATE passes run (`model/__init__.py:164-200`): 18.2M row updates in 3.3 days plus Elo's 659,775 single-row UPDATEs. Largest steps 345 s (RE24), 223 s, 213 s. Most output feeds nothing now (`gbm-v1` last predicted 2026-08-04; only Elo ran 10-11).
- **Seasonal freezing:** use change detection, not a hard freeze (Retrosheet, Chadwick, Statcast correct history). Loaders rewrite unchanged data: `retrosheet_event.update()` force-reloads the current decade nightly with no hash (`retrosheet_event.py:256-273`); the 5-minute `mlb_api` cron delete-and-reloads about 60k `mlb_transaction` rows each tick (19 GB WAL in 3.3 days, the biggest WAL writer). Fix by skipping when a content hash / Last-Modified is unchanged. The stable-ids design's fingerprint (D3) would otherwise mark everything dirty every night.
- **dlt:** not for existing connectors (1-3 day fix inside current loaders instead; migrating 38 connectors adds a second state store beside `meta.ingestion_item` [A]); consider per new simple REST source.
- **ClickHouse vs Timescale:** Timescale in Postgres. Extension loaded (2.28). Keeps Polymarket, Kalshi, snapshots and `core.market` in one transactional store. ClickHouse-local on 924k Polymarket rows: 0.93 bytes/row; Kalshi 774k rows x 8 columns: 1.43 bytes/row. Timescale estimated 2-8 bytes/row [A] (later measured in `results.md`: 3.5 and 6.2). Nothing downstream reads these tables except connectors, coverage and repair.
- **Prefect:** not now; `mlb nightly` (336 lines) is adequate. The fragility is in what steps do and in alerting: no `mlb.toml`, `MLB_ALERT_COMMAND` unset, rc=1 every night (coverage + schema-watch fail), nothing notices if the supervisor dies. Fix alerting, add an outside "did it finish" ping, separate pipeline failure from health warnings.
- **Redis:** not needed. A real in-game design is one asyncio service under systemd: Kalshi websocket (signed), Polymarket CLOB websocket (public), MLB GUMBO `feed/live` polled every 5-10 s (no public MLB websocket) [A docs]. Batch-COPY every 1-2 s into append-only hypertables storing both source time and received time; keep latest state in memory; Postgres NOTIFY. Add Redis only when a website must fan out to many readers.
- **Type optimization:** only the two market tables (and snapshots); leave other `raw` text. Procedure is in `design.md` D2-D4.
- **Alembic:** no (118 numbered SQL migrations behind `mlb migrate`; nothing to fix).
- **Core/gold redesign (all [V]):** `conform.run()` (`conform.py:1764-1880`) TRUNCATEs 24 tables and rebuilds about 30M rows in one transaction (ids reissued, about 80 min of locks, gold empty until `report`, any error discards the run). WAL/night: `core.pitch` 9.6 GB, `core.play` 5.7 GB, `core.play_retro` 12 GB, `batting_game` 2.1 GB. RE24 features join the same-season matrix (`team_leverage_re24_update.sql:120-128`): each game valued with run expectancies computed over the whole season including later games, a probable point-in-time leak despite a "zero lookahead" header; also COALESCEs missing states to 0. Effect size unmeasured. Two feature stores exist (`gold.game_feature` and DuckDB `feat.*`); 18 SQLMesh models exist but nightly never runs SQLMesh. Proposed: season-scoped conform into staging tables, validate, swap via DETACH/ATTACH PARTITION (`core.play`/`core.pitch` already have 316 partitions); upsert entities on natural keys; weekly `--full` rebuild as oracle with diff report; features read only `core`, export per-season Parquet, built in DuckDB; drop SQLMesh from the plan.

## Root causes, ranked
1. Rebuild-everything: conform, report, predict recompute 1910-2026 nightly (about 2.5 of 3.7 h); current season is about 5% of pitch rows, so incremental should be about 10-15 min [A].
2. Loaders rewrite unchanged data (44 GB WAL/day; 123 WAL-forced checkpoints vs 150 timed; 99 GB written by backends).
3. Health checks do full scans: coverage + repair take 58 min a night; `postgres_exporter` calls `pg_database_size` about 0.86 times/s.
4. Spinning RAID5 amplifies all of it [A]; shared host.
5. Fragile design: one giant transaction, gold emptied mid-run, alerts going nowhere, rc=1 normalized, no watchdog.
6. Text types mostly cost space, backup time (`pg_dump` 55 min nightly) and coverage scans; not the main cause of slowness.

## Phased plan (at most 2 open changes: one ops, one build)
- **Phase 0 stabilize (2-3 days):** alert command + watchdog; coverage/repair weekly; 5-min tick limited to live games + today's schedule (transactions/roster/draft hourly, skipped when unchanged); Retrosheet conditional GET; commit per stage in conform at minimum; exporter tuning. Exit: nightly under 2 h, WAL/day down 40%+, forced failure alerts, 7 nights rc=0 or a real alert.
- **Phase 1 market store (1 week):** Timescale test, then typed hypertable swap. Exit: 10 GB or less; per-token per-month counts and price sums match; loader run-twice passes.
- **Phase 2 incremental core (2-3 weeks):** absorbs `stable-ids-incremental-conform` and the rest of `widen-core-pitch-play`. Exit: no-change night conform 10 min or less; second run changes nothing; weekly full-rebuild diff 0; ids stable 7 nights. Rollback `mlb conform --full`.
- **Phase 3 sabermetrics package + DuckDB features (6-10 weeks, one family per PR):** first ask which features any live model uses and archive the rest unported; per family port, parity report on closed seasons, PIT check, switch consumer, delete the SQL file/UPDATE step/module. Fix known defects (framing, RE24 same-season leak, first-pitch-strike denominator, `away_woba` WHERE clause). Exit: `gold.game_feature` dropped.
- **Phase 4 live daemon (2-3 weeks, Feb-Mar 2027, test on spring training):** 2 weeks parity against 15-min snapshots; delete `capture_live`, the odds-capture cron, `live.py` polling.

## The 20 open OpenSpec changes (judged from titles and task counts; check each before closing)
- Archive: feature-store-v1 (32/32), model-readiness-audit, governance-convergence, metric-catalog, source-inventory, job-retries-alerts (move its alert task to Phase 0).
- Fold into Phase 0: pipeline-recovery, pipeline-freshness, operating-contract-v2, data-completeness.
- Fold into Phase 1: odds-bulk-history, odds-history-capture.
- Fold into Phase 2: stable-ids-incremental-conform, widen-core-pitch-play, section 7 of streamline-core-gold-direction.
- Park: negro-league-scope, play-engine, full-source-ingestion, fresh-database-bootstrap, retrosheet-state-engine.

## ADRs
- Keep (correctness): 277 truthful `observed_at`, 293 count each pitch once, 294 append-only snapshots, 297 stable ids, 299 Chadwick C tools, 283/284 game-type reference / player identity, 274 promotion is a review; implied price strictly before first pitch; point-in-time, `SOURCE_RIGHTS` (Polymarket/Kalshi data stays out of public exports), idempotent loads, missing is not zero.
- Keep (preference): 288 fungo, 298 supervisor, 295, the no-SQL-in-Python lint.
- Change: 287 (DuckDB becomes the feature build engine; retire `gold.game_feature`); 300 (dlt allowed per source); 305 (do not widen `core` until Phase 2); 271/266 (drop SQLMesh from the critical path); 285 is stale (its 2-hourly cron is gone), supersede it.
- Drop: "not adopting TimescaleDB"; Phase A/B/C gates as blockers (replace with the 2-change cap); `CLICKHOUSE_DECISION.md` as governing (keep as history).
- Charter claims: "never use pychadwick" holds (fails to build, DECISIONS.md:5301); "fungo for FanGraphs" holds; schema renaming correctly dropped.

## Risks and unverified
Unverified: Timescale ratio on this data (since measured, `results.md`), WAL cost of the market migration, cause of the 10-09 death (notes say network), Kalshi/Polymarket websocket details and limits, whether cron's environment has an alert command, the size of the RE24 leak, the incremental-core gain. Risks: market swap during an active backfill (pause first); partition-swap correctness in incremental conform (weekly full oracle); parity tolerance in Phase 3 hiding a real change; host contention from langfuse/datahub.
Owner questions: (1) which predictions are needed next season (owner: not decided, keep it easy to change); (2) must market ticks ever be published (rights doc says no today; still open); (3) scratch Timescale test and Phase 0 cron changes (owner approved the test and Phase 0).
