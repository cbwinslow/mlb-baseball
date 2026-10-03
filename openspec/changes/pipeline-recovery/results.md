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
| 23 | backup freshness: never run | action | No backup row in `meta.ingestion_run`; only an old schema-only file (2026-08-21) in `backups/`. Tasks 2.1-2.4. |

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
