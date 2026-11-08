# Operational Milestone: 2026 season and World Series completeness audit

**Date:** 2026-11-08
**Target database:** PostgreSQL `mlb` (production, `localhost:5432`)
**Scope:** verify what the database holds for the 2026 regular season and 2026
World Series, and close every raw-data gap that a source can still fill.

## Background

`mlb coverage` reported two repairable 2026 gaps: Polymarket price windows and
Kalshi candle windows for markets opened during the season. The 2026 World
Series ended 2026-10-28; the audit asks whether every played 2026 game has its
audit tables, and whether every 2026 market has its history.

## Actions

1. `mlb ingest polymarket --mode backfill` (run 32641) — 11,014 windows loaded,
   850 unavailable (recorded source gaps), nothing failed.
2. `mlb ingest kalshi --mode backfill` (run 32642) — 7,665 markets, 7,788,452
   candle rows loaded, nothing unavailable or failed. Resumed from the ledger
   after an earlier interruption.
3. Targeted additive fill of `raw.mlb_person` for 2026 roster ids the Stats API
   had never been asked for (46 rows). A full `mlb ingest mlb_api` bootstrap was
   deliberately not run: it re-downloads all 2,469 game-detail records, and its
   planned `TRUNCATE` was blocked behind the 02:09–03:18 weekly `pg_dump`.
4. Read-only verification with `mlb coverage` and direct SQL (below).

Reproduce the fix path with:

```bash
.venv/bin/mlb ingest polymarket --mode backfill
.venv/bin/mlb ingest kalshi --mode backfill
.venv/bin/mlb coverage --source kalshi --missing-only
.venv/bin/mlb coverage --missing-only
.venv/bin/mlb coverage --unexplained --missing-only
```

## Verification

Played 2026 games, all game types, `status in ('Final','Completed Early')` in
`raw.mlb_schedule._season = '2026'`:

| phase | games | dates |
| --- | --- | --- |
| regular (`R`) | 2,429 | 2026-03-25 → 2026-09-27 |
| wild card (`F`) | 9 | 2026-09-29 → 2026-10-01 |
| division (`D`) | 16 | 2026-10-03 → 2026-10-10 |
| LCS (`L`) | 10 | 2026-10-11 → 2026-10-19 |
| World Series (`W`) | 5 | 2026-10-23 → 2026-10-28 |
| spring (`S`) | 448 | — |
| exhibition (`E`) | 38 | — |
| All-Star (`A`) | 1 | — |

All 2,956 played rows have play-by-play, batting/pitching/fielding box scores, a
linescore, win probability, game context, umpires, and — for the 2,469 regular
and postseason games, the connector's `STATCAST_GAME_TYPES` scope — Statcast
pitches. Zero missing in every one of those columns.

2026 World Series (Milwaukee Brewers over Tampa Bay Rays, 4–1):

| game_id | date | matchup | score | pbp | umpires | statcast |
| --- | --- | --- | --- | --- | --- | --- |
| 849805 | 2026-10-23 | TB @ MIL | 2–3 | 69 | 6 | 264 |
| 849802 | 2026-10-24 | TB @ MIL | 4–5 | 78 | 6 | 341 |
| 849804 | 2026-10-26 | MIL @ TB | 10–1 | 76 | 6 | 294 |
| 849803 | 2026-10-27 | MIL @ TB | 3–4 | 92 | 6 | 367 |
| 849799 | 2026-10-28 | MIL @ TB | 4–1 | 70 | 6 | 255 |

`raw.mlb_schedule.series_status` carries the full bracket progression through
`MIL wins 4-1`. Regular-season games carry 4 umpire rows and postseason games 6,
which is the source's assignment pattern, not a gap.

2026 elsewhere: `raw.bref_batting` 664 rows, `raw.bref_pitching` 868,
`raw.fangraphs_batting` 1,472, `raw.fangraphs_pitching` 868,
`raw.fangraphs_fielding` 2,305; `gold.batting_season` 1,401,
`gold.pitching_season` 1,870, `gold.player_season` 1,532,
`gold.division_standing` 30.

Coverage results after the backfills:

- `mlb coverage --source kalshi --missing-only` → `nothing to report`.
- `mlb coverage --source polymarket --missing-only` → `nothing to report`.
- `mlb coverage --missing-only` → only `mlb_api` and `register` rows remain (below).
- `mlb coverage --unexplained --missing-only` → one entry, `raw.mlb_person`.

## Remaining gaps and their owners

| gap | owner | current state |
| --- | --- | --- |
| `gold.team_season`, `gold.batting_postseason`, `gold.pitching_postseason` max season 2025 | Lahman | 2026 rows do not exist upstream; local archive is `lahman_1871-2025_csv.zip`. Postseason gold is Lahman-only by `migrations/0100_gold_postseason.sql`. |
| `raw.retrosheet_event` / `raw.retrosheet_game` max `_season` 2025 | Retrosheet | Publisher has not released 2026 event/game files; `raw.retrosheet_schedule` 2026 (2,430 rows) is present. |
| `raw.mlb_game_context`, `raw.mlb_win_prob`: 2 games in 2011 | accepted gap | Games 305461 and 308207 return HTTP 500 from the source; recorded in `mlb_baseball/coverage/accepted_gaps.toml`. |
| `raw.register_people`: 43 ids (ceiling 50) | accepted gap | Negro League/exhibition players and umpire placeholders; see the registry note. |
| `raw.mlb_person`: 128,984 referenced ids absent | scope decision | The roster line is 1 person (a 1933–1936 placeholder the API does not return); the rest are draft/transaction amateurs and minor leaguers the loader does not fetch. Documented, not a 2026 defect. |

The 2026 postseason player statistics are still available from
`raw.mlb_boxscore_*` and `raw.statcast_pitch`; only the Lahman-sourced gold
postseason relations are waiting on the next Lahman release.

## Operational notes

- Kalshi backfill throughput dropped to roughly 1.5 items/s while four parallel
  workers from an unrelated `count(*)` were scanning a large table; cancelling
  them restored the rate. Avoid broad `count(*)` scans on `raw.polymarket_price`
  and `raw.kalshi_candle` during a backfill.
- No schedule still runs these backfills (`openspec/changes/data-completeness`
  task 3.3), so market history will need another pass before the next audit.
