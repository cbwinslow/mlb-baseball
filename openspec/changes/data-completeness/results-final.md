# Results (interim, 2026-10-07)

Not final: Kalshi, Polymarket and two Statcast games are still open. See `tasks.md`.

## Before and after (`mlb coverage`)

| Gap | Before | After | How |
|---|---|---|---|
| FanGraphs park factors 1871-1900 | 30 seasons missing | held | `mlb ingest fangraphs` (task 2.3) |
| FanGraphs fielding 2019 | missing | held (2,269 rows) | same |
| MLB reference and stat seasons (9 tables) | 2006, 2017-2025 missing | 2000-2026 held | bug fix (one 404 discarded a season) + `mlb ingest mlb_api --mode bootstrap` |
| mlb_person roster ids | 147 missing | 1 missing | same run |
| MLB linescores | 85 missing | 0 unexplained (source has none) | ledger marks, one analytics run |
| Venue ids | 351 "missing" | 0 | false gap: `17.0` vs `17` |
| Team ids | 70/80 "missing" | accepted (not clubs) | accepted list |
| Leaderboards, manifest files, a Statcast date | 10 wrong expectations | fixed | coverage changes |

## Open

- Statcast: 2 games from 2026-10-05/06; the nightly update should load them.
- Kalshi candles (1,492 markets) and Polymarket price windows (5,750): deferred by the owner; connectors reviewed, idempotent and resumable; run `mlb ingest kalshi --mode backfill` and `mlb ingest polymarket --mode backfill` when wanted.
- MLB games 305461 and 308207 (2011): the source answers HTTP 500; accepted with a ceiling.
- One roster person (116751) should arrive with the next mlb_api person load.
- Negro League data and the widening of `raw.mlb_person` beyond rosters: scope, owned by `negro-league-scope` and `full-source-ingestion` 0.14.

## Made permanent

- Nightly step `mlb coverage --unexplained --missing-only --fail-on-gap` alerts on any gap not listed in `mlb_baseball/coverage/accepted_gaps.toml`.
- Every MLB reference table loads one at a time and heals per table; FanGraphs and the MLB bootstrap fetch only what is missing.
- Source pages in `docs/sources/` carry facts verified on 2026-10-07.

## Not yet proven

- A full bootstrap from an empty database (it would take days; every connector has a real-database load test, but no single end-to-end run exists).
- The main checkout `~/workspace/mlb` is behind main by today's fixes because of uncommitted owner edits; the nightly cron runs the older code until it is updated.
