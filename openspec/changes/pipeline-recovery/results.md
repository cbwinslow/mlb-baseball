# pipeline-recovery — results

## Approval log (task 0.1)

Every production write adds a row before and after it runs. Read-only queries are not logged here.

| Step | Exact command | Target DB | Run by | Time (UTC) | Output captured | Backup id in force |
|------|---------------|-----------|--------|------------|-----------------|--------------------|
| (none yet — all work so far is read-only) | | | | | | |

## 1.1 Starting point (read-only), 2026-10-03

- Database queried: `mlb` (production), via `psql -d mlb`; `select current_database()` returned `mlb` at 01:32 UTC.
- Free disk (`/`): 250 GB free of 547 GB (52% used). On 2026-10-02 it was 94 GB free (82% used). Cause of the change not yet known.
- Full `mlb doctor` output (2026-10-03, 343/370 checks passed, 27 failing): saved in the table of section 1.5.

## 1.2 The 14:23 UTC 2026-10-02 run

Evidence (read-only):

- `meta.ingestion_run` ids 17254–17264: `migrate` (mode `nightly`) succeeded 14:23:05–14:23:11; then 11 `update` runs started 14:23:16. Seven finished (retrosheet, register, bref, lahman, news, fangraphs); four never did: statcast (17256), polymarket (17258), kalshi (17261), retrosheet_box (17264) — still `running`.
- `logs/mlb_daily_update.log` shows activity from this run up to 14:27:32, ending in Kalshi `429 Too Many Requests`, Polymarket schema-drift warnings, and a Retrosheet box warning. No later lines.
- The run was the manual test of the unmerged `mlb nightly` supervisor (`migrate` with mode `nightly` is its marker; commit 7f37700 landed at 14:28). The 06:00 cron job and the 07:20–08:07 model bootstrap that day succeeded.
- No process is running these jobs now; the only open database sessions on `mlb` are idle (no `idle in transaction`).

Cause: the manual test was interrupted (cause of the interruption is unknown; the Kalshi 429 is the last error logged). Not a cron failure.

## 1.3 What the interrupted run wrote to raw (read-only)

| Source | Finding |
|--------|---------|
| kalshi (events, markets, snapshots) | Untouched since the 06:00 run (max `_loaded_at` 06:07–06:08). `kalshi_series` was fully reloaded at 14:23 (187 rows, a small reference table). |
| polymarket (all four tables) | Untouched since 06:04. |
| statcast | Summary tables untouched since 06:22. `statcast_pitch` has rows loaded at 14:26 for 2026 (normal per-season replace; the table's delete/insert counters are consistent with that). |
| retrosheet_box | Re-loaded at 14:24 for most seasons (13,984 games loaded 14:24; 4,483 from earlier loads). Seasons 1936–1949 and other Negro-league-era files were not reloaded (their rows date from 2026-08-08 or 06:02). No duplicate `game_id` in 1903 or 1904 (the two seasons holding both old and new rows). The log shows the new code skipping the official 1936 Negro League box file. |

Conclusion so far: no sign of duplicated or half-loaded raw rows. The retrosheet_box tables hold a newer load than the one core was last built from (core built 06:22–07:06). Whether the 14:24 content equals the 06:02 content has not been compared (the 06:02 rows were replaced); `mlb conform` would pick up the new content on its next run. No raw rows were changed by this review. Remaining open: confirm with the owner that the Retrosheet box reload at 14:24 is acceptable, and decide whether to compare box counts against `core` before the next conform.

## 1.4 Live lock and session state (read-only), 2026-10-03 01:32 UTC

- Advisory locks in `pg_locks`: none held.
- Sessions on `mlb`: three idle, no `idle in transaction`.
- The doctor failure "workflow lock held by pid 2344001" is therefore no longer true; it cleared on its own (PostgreSQL releases advisory locks when the session ends).

## 1.5 Doctor failures

Classification is provisional until the owner signs off (task 1.5 stays open for that). Review date for every accepted item: 2026-11-03. "Evidence" is from read-only queries on `mlb` on 2026-10-03.

| # | Failure (short) | Class | Evidence / next step |
|---|-----------------|-------|----------------------|
| 1 | migrations: 0109 pending | action | One unapplied migration (`query_stat_snapshot`); handled by task 2.6. |
| 2 | stale ingestion runs (4) | action | Rows 17256, 17258, 17261, 17264 `running`, no live process; task 2.5. |
| 3 | metric catalog empty | action | `meta.metric` 0 rows, 50 YAML files; task 2.7. |
| 4 | never-vacuumed tables (4) | real defect | Dead tuples 80,169 / 27,534 / 20,174 / 1,614; task 2.8. |
| 5 | mlb_api analytics durable coverage (76 incomplete, 1950 on) | real defect (ledger empty); gaps in early 1950s expected | Check counts ledger rows in `meta.ingestion_item`, which has 0 rows (verified), so every season scores 0%. The raw data is largely present: of 162,659 final games 1950-2025 only 1,192 have no win-probability/game-context rows (352 in 1951, 185 in 1950, long tail after). The connector notes say MLB has this data from 1950 and 404s before 1949, so the early gaps are a source limit. Fix: backfill the ledger from the existing raw tables without re-downloading; check the ledger write path in `mlb_api.py` (~1528, 1697-1788). |
| 6-8 | retrosheet_box, statcast, polymarket, kalshi: last run `running`, freshness | consequence of #2 | Clear when #2 is repaired; no separate defect. |
| 9, 11 | `raw.polymarket_price`, `raw.kalshi_candle` missing | wrong check | Tables exist only after the owner-triggered historical backfill (`polymarket.py:108`, `conform.py:1337`); the snapshot tables exist and are current. Task 3.1. |
| 10 | gbm-v2 model file missing | accepted candidate (owner to confirm) | `models/artifacts/` has no trained model; training is not part of the current NOW work. Owner to confirm. |
| 12 | away_woba coverage: 50 eligible rows missing | real defect (code) | `team_woba_live_update.sql` sets both `home_woba` and `away_woba` but its WHERE is only `home_woba IS NULL` (line 52); when the home team is on its first covered game the live pass overwrites the correct away value with NULL. About 1 game per season (e.g. 16202679, 2021-04-06). Fix: set each side only when NULL (`COALESCE`), rebuild, rerun wRC+. |
| 13 | model.bsr_comprehensive.domain (86) | wrong check | All 86 are `wsb` (running season total of steal runs) outside ±20: min -21.64, max 23.40, in 1910-12, 1924, 1962, 1975, 1985-86, 1993 and late in the season. Plausible for the eras. Fix: widen the `wsb` bound to ±30. |
| 14 | model.catcher_framing.domain (61,107 rows) | **real defect (computation), not the bounds** | `catcher_framing_csae_update.sql` lines 36-38 count "called strikes" as `event_cd='3' OR event_tx LIKE '%C%'` and "takes" with `'%B%'`, but `event_tx` is the play-description text, not the pitch sequence, so the counts mix strikeouts, walks, steals and balks. Mean CSAE% is about +0.30 in the 2010s and almost never negative, so it is not a framing signal. The metric file marks it `implemented-untested`. Values are season-to-date cumulative, so bounds from the literature are right. Fix: count real called strikes/balls from the pitch sequence or Statcast `called_strike`, or null the columns until then; do not widen the check. |
| 15, 16 | prediction count above expected (Polymarket 1,822 vs 538; Kalshi 1,262 vs 643) | wrong check (counts rows, not games) | No join fan-out. `gold.prediction` is keyed by (game, model_version, generated_at), so each run adds a row: Polymarket 1,827 rows for 585 games over 31 runs; Kalshi 1,265 rows for 663 games over 33 runs (verified). Fix: count distinct games or the latest run per game. After that Polymarket still shows 584 games against 538 expected; that gap is unexplained and stays open. |
| 17 | starter first-pitch strike% outside [0,1] (3 rows) | real defect (code) | In `team_pitch_discipline_retrosheet_update.sql` the numerator counts first-pitch strikes on every event row, while the denominator counts only batter-event rows (`bat_event_fl='T'`), so steals, wild pitches and pickoffs inflate it (rows 1.05, 1.20, 1.17). The metric reads about 1.5% high everywhere, not only in the 3 rows. Fix: count on batter-event rows only; fully correct counting needs the first pitch of each plate appearance. |
| 18 | model.pitcher_estimators.domain (31) | wrong check | All 31 are slightly negative SIERA/xFIP (min SIERA -1.86); the published SIERA polynomial can go below 0 for very good pitchers on small samples. 20 rows are 1908-1948, 8 are 2019-2025. Fix: lower SIERA bound to about -3; keep xFIP at 0 or allow a small band. |
| 19 | model.pitch_movement.domain (1) | wrong check (borderline) | One row (game 16201858, 2020): vertical separation -14.06 against a -10 floor; the metric mixes FF/SI/FC and CU/SL/ST. 60 of 41,522 values are below 0. Fix: widen the lower bound to about -25. |
| 20 | platoon_matchup_woba_diff_bounds (158 home, 155 away) | wrong check (bound too tight) | 313 rows of 217,495 (0.14%); min -0.621, max +0.417, mostly April-May. Cause: the starter split is unshrunk with only 15 PA required. Fix: warn above ±0.45 now; shrinkage toward league mean is a separate modelling decision. Separate issue found: the same SQL does `COALESCE(..., 0.320)`, which fills missing wOBA with a league average and conflicts with the "missing is not zero" rule. |
| 21 | gold.player_season / team_season outside regular-season envelope (4 rows) | **real defect, cause found** | Four 2026 players (Albies 165 G, Harper 165, Olson 165, Crow-Armstrong 164; bound 163). Not a live-ingestion problem: `core.game` already marks 2026 correctly (regular 2026-03-25 to 2026-09-27; 9 `wildcard` games 2026-09-29 to 2026-10-01). Cause: Baseball-Reference's date window in `connectors/bref.py` ends at `_REGULAR_SEASON_END`, a hardcoded list with no 2026 entry, so it falls back to `2026-10-01` and pulls in the 3 wild-card games (162 + 3 = 165). The code comment names this exact case. Code fix merged 2026-10-03 as PR #279 (e20be18a): 2026 end date added and unlisted seasons now end the day before their first scheduled postseason game. Still to do: owner-run re-ingest of `raw.bref_*` 2026 and rebuild (task 3.4). Fix = task 3.4 (derive the end date from `core.game`, then re-ingest `raw.bref_*` 2026 and rebuild). No raw value needs editing; raw keeps what the source returned. |
| 22 | `feat` health check raised Binder Error (`home_pa_30d`) | stale file, check is correct | `~/.mlb/mlb.duckdb` was built 2026-09-23; `home_pa_30d` was added 2026-09-26 (commit f5382d5). Fix: rebuild with `mlb build`; optionally make the failure say "stale schema". |
| 23 | backup freshness: never run | wrong check (a good backup exists elsewhere) | The check only reads `meta.ingestion_run` rows written by the project's own `mlb backup`, which has never run. A host-level job (`~/workspace/infra/scripts/validated_backup.sh`, cron 02:00 daily, weekly, monthly) already dumps `mlb` (PG16, port 5432) in `pg_dump -Fc` zstd format: 5.6 GB, verified with `pg_restore -l`, SHA256SUMS, 7 daily / 4 weekly / 3 monthly kept under `~/workspace/backups/postgres/`, mirrored to `postgres-mirror` and restic. Latest: `daily/20261003_020001`, `pg16_mlb.dump` taken 02:14-02:32 UTC, checksum verified 2026-10-03. Not yet proven: an actual restore (tasks 2.3-2.4). Fix: make the doctor check read the host backup's state instead of demanding a second 61 GB plain-SQL dump; owner to decide whether `mlb backup` is kept or retired. |

The earlier "workflow lock held" failure has cleared (section 1.4), so it is not in this table. Count: 27 failing checks in 23 table rows (rows 6-8 group four sources' last-run and freshness failures; 9/11 and 15/16 group pairs).


## Status log

### 2026-10-03

Merged to `main` (owner asked for each merge; all required checks green, review threads resolved):

| PR | What | Commit |
|----|------|--------|
| #279 | bref: unlisted season's window ends the day before its first scheduled postseason game; 2026 end date added (fix for the 4-player 164-165 G leak, doctor failure 21) | e20be18 |
| #280 | this change's planning artifacts | a51a778 |
| #276 | stable-ids + job-retries plan, `mlb nightly` supervisor, per-step timing logs, `meta.query_stat_snapshot` (migration 0109). Review fixes added before merge: per-step timeout that kills a hung step, separate 300 s timeout and logging for `repair-runs`, CLI dispatch test, NULL query text allowed in 0109 | e7d42d1 |

Task 0.2 is decided: #276 merged first. The shared checkout `~/workspace/mlb` (where cron runs) was switched back to `main`.

**Risk accepted for tonight, recorded on purpose:** the 06:00 UTC cron entry now runs `mlb nightly` for the first time (previously a long shell script). `mlb nightly` starts with `mlb migrate`, so migration 0109 (creates one small new table, `meta.query_stat_snapshot`) will be applied by that run, before the backup gate in tasks 2.4-2.6 has been met. It adds a table and changes no existing data. Follow-up after the run: check `logs/mlb_daily_update.log`, `mlb runs --check`, `meta.ingestion_run` for the `nightly` rows, and `mlb doctor`.

**Still open after tonight:**
- 3.4 owner-run re-download of `raw.bref_*` 2026 and gold rebuild (the nightly's bref update may do the download itself; confirm, then confirm Albies 2026 = 162 G).
- 1.5 owner sign-off on the doctor classification; investigate the "not yet examined" rows.
- 2.x backup gate, repairs, vacuum; 4.x measurement; 5-7 incremental conform.
- Stale rows 17256, 17258, 17261, 17264 are still `running`; `mlb nightly` runs `repair-runs`, which should clear them tonight.

### 2026-10-03, after the first `mlb nightly` run (06:00-08:00 UTC)

- Run finished `rc=0` in about 2 h 0 min: migrate 5 s, update 14 m 28 s (3 attempts allowed, 1 needed), conform 2573 s, report 854 s, predict 2915 s, populated 5 s. One `meta.ingestion_run` row per step (mode `nightly`). Migration 0109 applied by the run; `meta.query_stat_snapshot` wrote 1,642 statements.
- Before the speed work: total about 2 h 7 min on 2026-10-02 against about 2 h 0 min now. The difference is the update step; conform, report and predict are unchanged, as expected.
- The four stale `running` rows (17256, 17258, 17261, 17264) are gone; no `running` rows older than an hour.
- Playoff leak fixed by the bref update in this run: Albies, Harper, Olson, Crow-Armstrong all 162 G in `gold.player_season` 2026 (was 164-165). Doctor envelope check passes. The owner-run re-ingest in task 3.4 was not needed; the nightly bref update does it.
- `mlb doctor`: 353 of 370 pass (was 343 of 370). Cleared: migrations, stale runs, workflow lock, all source last-run and freshness checks, regular-season envelope. Remaining 17: metric catalog empty, never-vacuumed tables, mlb_api analytics ledger, polymarket price / kalshi candle (wrong check), gbm-v2 model file, away_woba coverage, bsr wsb, catcher framing, prediction counts (2), first-pitch strike%, pitcher estimators, pitch movement, platoon bound, feat stale file, backup never run. All are classified in section 1.5; fixes are tasks 2.x, 3.x and 9.x.

### 2026-10-03 (evening): backups and disk, corrected

- **Disk:** the production database lives on `/mnt/storage` (`/var/lib` is not used; PG16 data dir `/mnt/storage/postgres-data`), a separate 1.5 TB volume with 840 GB free (42% used). The earlier "94 GB / 251 GB free" figures were for the system disk `/` and do not limit backups or restores of `mlb`. Task 2.1's free-space rule applies to `/mnt/storage`.
- **Backups:** see row 23. `mlb` is backed up nightly by the host job; this change does not add a second backup.
- **Restore test (tasks 2.3-2.4), done:** restore `daily/20261003_020001/pg16_mlb.dump` with `pg_restore -j 4` into a new database `mlb_restore_check` (never `mlb`), compare it against production, then drop it. Approval log: owner said "keep going" on 2026-10-03 after the plain-language description; target database `mlb_restore_check`; backup id in force `daily/20261003_020001`.

### Restore test result (2026-10-03, 21:57-22:20 UTC)

Restored `daily/20261003_020001/pg16_mlb.dump` (checksum verified first) into `mlb_restore_check` with `pg_restore -j 4 --no-owner --no-privileges`, then compared with production `mlb`, then dropped the test database (confirmed gone). Production `mlb` was only read.

- **Time and size:** 23.5 min; 43 GB restored against 61 GB in production (production carries dead-row bloat; the restore is compact).
- **Errors:** pg_restore exit 1 with 12 ignored errors, all about `pg_cron` (extension can only be created in database `mlb`; `cron.job` has 0 rows in `mlb`) and one TimescaleDB catalog table (`mlb` has 0 hypertables). None touch project data. A real disaster restore must go into a database named `mlb` to get `pg_cron`; neither extension holds anything `mlb` uses.
- **Structure:** 219 of 220 tables present (the one missing, `meta.query_stat_snapshot`, was created by migration 0109 at 06:00, after the dump); indexes 775 vs 776 and constraints 1,622 vs 1,623, the difference being that new table's primary key; sequences 23 vs 23; views 18 vs 18.
- **Row counts, exact:** 172 tables identical. 47 differ, all tables that are written after the 02:14-02:32 dump (06:00 nightly update/conform/report, the 5-minute `mlb_api` job, ingestion run history). Differences are small (a few rows to a few thousand). The cases where production now has FEWER rows than the dump: `raw.kalshi_market` 377,694 → 363,100, `core.market` 45,638 → 45,572, `raw.mlb_roster` 111,601 → 111,561, and single-row changes in `raw.bref_pitching`, `raw.statcast_*` leaderboards. Leaderboards and the roster are whole-season replacements. `raw.kalshi_market` was replaced as a whole table at 06:08 (all rows share one load time) and lost 14,594 rows; whether that is intended is **open** (observation, not yet classed a defect; the market history is kept in `raw.kalshi_snapshot`).
- **Conclusion:** the nightly host backup restores into a working copy of `mlb` with the same structure. Task 2.3 done. Remaining for 2.4: make `mlb doctor` backup freshness read the host backup (owner decides whether `mlb backup` is kept or retired).

### 2026-10-04: `away_woba` fixed at source (task 9.2)

- **Source cause (confirmed by two failing tests before the fix):** `team_woba_live_update.sql` was gated only on `home_woba IS NULL` but set both `home_woba` and `away_woba` from live play-by-play. The home team's first covered game of a season has a legitimately NULL home value, so the live pass ran and overwrote the away value that Retrosheet had already filled, with NULL when it had no live data (every pre-2026 game). The mirror case (home value present, away missing) was never filled.
- **Layer / file:** gold feature build, `mlb_baseball/sql/team_woba_live_update.sql`.
- **Fix:** each side is filled only where still NULL and only where the live data yields a value (`COALESCE` per side, and a WHERE that requires something to fill). It no longer rewrites historical rows, which also removes needless row churn. `compute_live` now returns the number of rows it filled something in (the existing test's expected count changed from 2 to 1, which is the correct reading: G1 has no history to fill from).
- **Tests:** two new integration tests (away value survives when only home is missing; away value filled when only it is missing), both fail on the old SQL; `test_model_offense.py` 15 passed, 60 related model tests passed; ruff, mypy, sqlfluff, check_dox pass.
- **Not changed:** no bound or check was touched. The other live-update files use the same gating shape; they are audited in new task 9.2b rather than changed blind.

### 2026-10-04: first-pitch strike% traced to a wider source cause (task 9.3, ADR-293)

- **What the doctor showed:** 3 rows above 1.0 (1.05, 1.17, 1.20). The first diagnosis (count first-pitch strikes only on batter-event rows) was right but incomplete.
- **Source cause, found by reading the raw rows:** Retrosheet writes a plate appearance's pitches cumulatively. A mid-plate-appearance runner event carries the pitches so far and the batter's final row repeats them (`BCBFF>B` then `BCBFF>B.>B`). The SQL summed every row, so those pitches were counted twice: 218,120 of 7,165,617 rows and 545,642 of 26,709,183 pitches (2.0%) over all history. First-pitch strike% was about 1.5 points high everywhere (2014+2019: 62.3% before, 60.7% after); CSW%/whiff% barely move (2019 CSW% 0.2850 to 0.2848) because numerator and denominator are inflated together.
- **Layer / file:** gold feature build, `mlb_baseball/sql/team_pitch_discipline_retrosheet_update.sql` (`clean_events`).
- **Fix:** drop a row followed by a continuation row of the same plate appearance (`pa_new_fl = 'F'`); count first-pitch strikes only when `bat_event_fl = 'T'`. A plate appearance cut short by an out on the bases is kept. No bound changed. Measured cost on production data (read-only): the SELECT part goes from about 5 s to 24 s; predict is about 49 min.
- **Check done:** earlier row is the start of the later row in 10,891 of 10,896 continuation rows (2014, 2019); the other 5 differ only in annotation characters.
- **Tests:** new integration test (fixture with a steal mid-plate-appearance and a plate appearance ended by a caught stealing) fails on the old SQL (csw 5/28 instead of 4/26) and passes now; the file's 6 tests pass; ruff, mypy, sqlfluff, check_dox pass.
- **Other readers:** only this SQL reads `pitch_seq_tx` in production. The unpromoted SQLMesh spike copy (`transforms/models/pitch_discipline.sql`) has the old logic and is frozen (ADR-271); recorded in ADR-293 and the metric file.
- **After merge:** the next nightly predict recomputes the feature; confirm the doctor first-pitch strike check passes.

### 2026-10-05: sibling live-update SQL audited and fixed (task 9.2b)

- **What was checked (read-only, production `mlb`):** `team_starter_live_update.sql`, `team_bullpen_live_update.sql` and `starter_workload_live_update.sql` have the same shape as the wOBA bug: gate on the home value `IS NULL`, then write both sides. Rows with only one side filled: starter about 40-60 per season in each direction (balanced), workload the same (2026 higher, 114 home-only and 102 away-only, mostly April-May, which fits first starts of the season having no prior start), bullpen 496 home-only, of which 470 are before 1990 (older Retrosheet-era gaps), 22 are 1990-2019 and 4 are 2020s.
- **Reading:** no sign in the data that the pattern has already damaged production rows (the gaps are symmetric and explained by missing history). The defect is latent: a home side with no live value would overwrite a filled away side with NULL, as it did for `away_woba`.
- **Fix at the source:** all three files now fill each column with `COALESCE(existing, live)` and the WHERE requires something to fill on either side. Starter ids are filled the same way. The live passes now return only rows where something was filled.
- **Tests:** three new integration tests (one per file; away value survives when only the home value is missing) fail on the old SQL and pass now. Two existing row-count assertions changed (workload 4 to 2, bullpen 2 to 1) because rows with nothing to fill are no longer rewritten. Related unit test updated.

### 2026-10-05: catcher framing rebuild attempt did not tie out to Savant (task 9.4, no decision yet)

- **Why the current columns are wrong:** `catcher_framing_csae_update.sql` counts "called strikes" from play text (`event_cd = '3'` is every strikeout, including swinging ones; `event_tx LIKE '%C%'` matches other letters) and uses a flat 0.33 baseline and 0.125 runs per strike that nothing cites. Doctor: 61,107 values outside bounds.
- **What was tried (read-only, production `mlb`, 2024 regular season, Statcast `raw.statcast_pitch`, takes = called_strike/ball/blocked_ball):** expected called-strike rate from prior-season (2023) league rates by plate location bin. Compared each catcher's strikes-above-expected with Savant's published 2024 `raw.statcast_framing.rv_tot` (source-faithful; the live CSV matches the table).
  - location only: correlation 0.32 (45 catchers, 800+ takes); centred 0.35 (39 catchers)
  - plus batter/pitcher hand and count: 0.36 (36 catchers)
  - shadow-zone pitches only, finer bins: 0.29 (40 catchers)
  - plus a pitcher adjustment: 0.18 (worse)
- **Scale does not match either:** top catcher Patrick Bailey is +96 strikes in the shadow-zone model against Savant's roughly 5 extra strikes (rv_tot 3.5). Savant adjusts for more (umpire, park, pitcher) than the pitch columns we hold.
- **Reading:** a location-only model does not reproduce Savant, so it cannot be called correct. The prior-season Savant value (`team_framing_update.sql`) ties to its source by construction.
- **Recommendation to the owner:** withhold the in-season columns (`*_catcher_csae_pct`, `*_catcher_framing_runs`) and keep the prior-season Savant value; no bound widened. Owner decision pending.

## 9.9 prediction-count checks count games (2026-10-05)

- Cause: `market._polymarket_coverage_check` / `_kalshi_coverage_check` used `count(*)`
  on `gold.prediction`, which keeps one row per run per game, so any game predicted
  more than once read as "join fan-out".
- Fix: both checks count `DISTINCT` games (`game_instance_key` / `core.game.id`).
  Test `test_coverage_check_counts_games_not_prediction_rows` failed first (`2 > expected 1`).
- The remaining gap (read-only query on `mlb`, 2026-10-05): Polymarket 585 predicted
  games vs 529 with a conformed price. 56 predicted games have no conformed price: 55
  are decided games whose prediction was written from live snapshots while upcoming
  (ADR-267) but `core.market` has no Polymarket row for them (0 of 55), dates
  2026-08-02..2026-09-27; 1 is an upcoming game. Likely cause: `core.market` Polymarket
  rows come from price history, and the history backfill had not been run (odds-history-capture
  4.2, started 2026-10-05). **Re-check after the backfill and the next conform; if the 55
  remain, it is a conform defect and needs its own task.**

## Production writes approved by the owner, 2026-10-05 (odds-history-capture 4.2, 4.3, 5.2)

| step | command | target | run by | when | result |
|---|---|---|---|---|---|
| 4.2 / 4.3 | `mlb ingest polymarket --mode backfill`, then `mlb ingest kalshi --mode backfill` (one nohup chain, log `logs/odds_backfill.log`) | `mlb` | owner (`!`) | 2026-10-05 | started; result pending (check the log for `polymarket rc=` / `kalshi rc=`) |
| 5.2 | cron `*/15 * * * * ~/workspace/mlb/scripts/mlb_odds_capture.sh` | host crontab | owner (`!`) | 2026-10-05 | installed (`crontab -l` shows it) |
Backup in force: host job `validated_backup.sh` (nightly 02:00).

## 9.5 ingestion ledger: finding, owner decision pending (2026-10-05)

- Facts (read-only on `mlb`): `meta.ingestion_item` has 0 rows; raw analytics hold 164,362 games
  (win_prob, game_context) and 77 seasons of linescores; no `downloads/mlb_api` artifacts exist.
  1,192 finished games (seasons 1950-2012) have no analytics rows.
- The ledger write path is wired and correct (`record_items` in `_load_linescores_for_season`,
  `_load_analytics_batch`, `_record_failed_analytics_items`; reached only by
  `mlb ingest mlb_api --stage analytics`). It is empty because that stage has not run since the
  ledger shipped (migration 0038); the raw data came from an earlier load.
- The existing contract (`_analytics_season_complete`, `_terminal_analytics_games`) requires each
  ledger row to carry a valid saved artifact + checksum; a "legacy raw-only load is replayed once
  into the durable ledger". Seeding artifact-less rows from raw would break that contract and
  claim provenance that does not exist, so it is NOT done. The task text "backfill from raw without
  re-downloading" is therefore not possible without weakening the contract.
- Real fix = run the staged analytics backfill once (about 2 requests per game, ~325k requests,
  resumable per season, 404s recorded as `unavailable`). Owner decision: run it, and over which years.
