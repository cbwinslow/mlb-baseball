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
| 5 | mlb_api analytics durable coverage (76 incomplete, 1950 on) | needs owner decision | Years such as 1950–1959 show 0 of ~1,240 games; likely the MLB API has no analytics for those years, so the check expects data that cannot exist. Needs a source-coverage fact check before classing as wrong check or accepted. |
| 6-8 | retrosheet_box, statcast, polymarket, kalshi: last run `running`, freshness | consequence of #2 | Clear when #2 is repaired; no separate defect. |
| 9, 11 | `raw.polymarket_price`, `raw.kalshi_candle` missing | wrong check | Tables exist only after the owner-triggered historical backfill (`polymarket.py:108`, `conform.py:1337`); the snapshot tables exist and are current. Task 3.1. |
| 10 | gbm-v2 model file missing | accepted candidate | `models/artifacts/` has no trained model; training is not part of the current NOW work. Owner to confirm. |
| 12 | away_woba coverage: 50 eligible rows missing | needs investigation | Not yet examined. |
| 13 | model.bsr_comprehensive.domain (86) | needs investigation | Not yet examined. |
| 14 | model.catcher_framing.domain (61,107 rows) | likely wrong bounds, owner decision | In `gold.game_feature` (217,495 rows): 48,556 rows have catcher CSAE% outside ±0.30 (observed up to 0.5629) and 29,047 have framing runs outside ±30 (observed up to 77.76); spread over every season (≈900 per season), so it is systematic, not a bad load. The bounds in `catcher_framing_csae_health_check.sql` or the feature definition need review. |
| 15, 16 | prediction count above expected for decided games with a Polymarket (1,822 vs 538) / Kalshi (1,262 vs 643) price | needs investigation | Possible join fan-out per the check message; not yet examined. |
| 17 | starter first-pitch strike% outside [0,1] (3 rows) | real defect candidate | Not yet examined; three rows. |
| 18 | model.pitcher_estimators.domain (31) | needs investigation | Not yet examined. |
| 19 | model.pitch_movement.domain (1) | needs investigation | Not yet examined. |
| 20 | platoon_matchup_woba_diff_bounds (158 home, 155 away) | needs investigation | Not yet examined. |
| 21 | gold.player_season / team_season outside regular-season envelope (4 rows) | **real defect, cause found** | Four 2026 players (Albies 165 G, Harper 165, Olson 165, Crow-Armstrong 164; bound 163). Not a live-ingestion problem: `core.game` already marks 2026 correctly (regular 2026-03-25 to 2026-09-27; 9 `wildcard` games 2026-09-29 to 2026-10-01). Cause: Baseball-Reference's date window in `connectors/bref.py` ends at `_REGULAR_SEASON_END`, a hardcoded list with no 2026 entry, so it falls back to `2026-10-01` and pulls in the 3 wild-card games (162 + 3 = 165). The code comment names this exact case. Fix = new task 3.5 (derive the end date from `core.game`, then re-ingest `raw.bref_*` 2026 and rebuild). No raw value needs editing; raw keeps what the source returned. |
| 22 | `feat` health check raised Binder Error (`home_pa_30d`) | real defect (check cannot run) | Column `home_pa_30d` not found; the check crashes, so its result is unknown. Task 3.2 makes this an ERROR. |
| 23 | backup freshness: never run | action | No backup row in `meta.ingestion_run`; only an old schema-only file (2026-08-21) in `backups/`. Tasks 2.1-2.4. |

The earlier "workflow lock held" failure has cleared (section 1.4), so it is not in this table. Count: 27 failing checks in 23 table rows (rows 6-8 group four sources' last-run and freshness failures; 9/11 and 15/16 group pairs).
