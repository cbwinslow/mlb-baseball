# Results (2026-10-08)

Not closed: see "Open" below. Every number is from `mlb coverage` or a read-only query on the dates shown.

## Before and after

| Gap | Before | After | How |
|---|---|---|---|
| FanGraphs park factors 1871-1900 | 30 seasons missing | held | `mlb ingest fangraphs` (2.3) |
| FanGraphs fielding 2019 | missing | held (2,269 rows) | same |
| MLB reference and stat seasons (9 tables) | 2006, 2017-2025 missing | 2000-2026 held | bug fix (one 404 discarded a season) + `mlb ingest mlb_api --mode bootstrap` |
| mlb_person roster ids | 147 missing | 1 missing | same run |
| MLB linescores | 85 missing | 0 unexplained (source has none) | ledger marks, one analytics run |
| Venue ids | 351 "missing" | 0 | false gap: `17.0` vs `17` |
| Team ids | 70/80 "missing" | accepted (not clubs) | accepted list |
| Leaderboards, manifest files, a Statcast date | 10 wrong expectations | fixed | coverage changes |
| Statcast, 2026-10-05/06 | 4 games missing | held | nightly update |
| 2027 schedule | 0 games | 2,500 games | nightly update |
| Kalshi candles | 1,492 markets missing | 0 after the run; 1,175 new again next morning | `mlb ingest kalshi --mode backfill` (twice), 2026-10-08 |
| Polymarket price windows | 5,750 missing | 0 after the run; 3,824 new again next morning | `mlb ingest polymarket --mode backfill` (twice) |

## Open

- Kalshi and Polymarket reopen daily: new game-day markets arrive faster than anything fills them. Needs the bounded nightly backfill (task 3.3). Until then the nightly coverage alert fires every night.
- The nightly coverage step took 38 minutes; it should be measured alone and made cheaper (3.3 follow-up).
- Statcast: 4 games of 2026-10-07 should arrive with the next nightly.
- MLB games 305461 and 308207 (2011): the source answers HTTP 500; accepted with a ceiling of 2.
- One roster person (116751), and the 129k person ids seen only in box scores, drafts and transactions (scope: `full-source-ingestion` 0.14, `negro-league-scope`).
- Task 1.5 (live checks for the other sources) and 3.5 (docs pass) are not finished.

## Made permanent

- Nightly step `mlb coverage --unexplained --missing-only --fail-on-gap` alerts on any gap not in `mlb_baseball/coverage/accepted_gaps.toml`. Seen working on 2026-10-08 (it alerted).
- Every MLB reference table loads one at a time and heals per table; FanGraphs and the MLB bootstrap fetch only what is missing.
- Source pages in `docs/sources/` carry facts verified on 2026-10-07; Kalshi and Polymarket re-probed (#382).
- Kalshi and Polymarket reviewed: all baseball, keep everything (owner decision).

## Not yet proven

- A full bootstrap from an empty database (task 3.1; it would take days; every connector has a real-database load test).
