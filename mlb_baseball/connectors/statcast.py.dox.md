# `statcast.py` DOX

## Purpose

Own Baseball Savant/Statcast **pitch-level tracking ingestion** into `raw.statcast_pitch`. This connector intentionally carries both the 2008–2014 PITCHf/x era and 2015+ full Statcast era in one source-faithful raw table, with real era-dependent missingness preserved.

## Ownership

Implementation: `statcast.py`.

Primary output:

- `raw.statcast_pitch`

Public connector capabilities:

- `bootstrap()` — historical 2008-present load, skipping already-complete past seasons.
- `update()` — refresh current season.
- `health_check()` — existence/last-run health without pretending this non-real-time source needs minute-level freshness.

## Source Contract

- Source: Baseball Savant through `pybaseball.statcast()`.
- First supported year is 2008 based on direct source testing.
- The source contains two genuine measurement eras:
  - **2008–2014 PITCHf/x**: pitch movement/velocity/location exists, while many Statcast-exclusive tracking/derived fields are unavailable and legitimately NULL.
  - **2015+ Statcast/Trackman**: broad pitch/batted-ball/spin/derived tracking fields are available, with newer bat-tracking fields appearing only in later seasons.
- Do not backfill, zero-fill, drop, or otherwise smooth away pre-2015 missingness merely to make one rectangular modeling matrix.
- This connector is the project's canonical rich pitch-tracking landing source; MLB Stats API pitch detail is intentionally not duplicated as a competing full tracking feed.
- Repository source-rights/profile metadata remains authoritative for permitted use/redistribution.

## Grain and Data Contract

- Raw grain is one source Statcast/PITCHf/x pitch/event row as returned by Baseball Savant.
- `_season` records the MLB season used for ingestion management.
- `_scope` identifies a weekly chunk as `<season>_<chunk-start-date>` and is the loader's idempotent replacement scope.
- Raw columns remain source-shaped/text-landed according to the generic loader contract. Typed canonical pitch facts belong downstream.
- Era-specific unavailable measurements are missing measurements, not zero.

## Runtime Contracts

### Weekly chunking

- Season windows are fetched in 7-day ranges from February through December/current date.
- Weekly batching was selected from direct performance measurement: it materially reduces request overhead relative to one-day pulls while keeping memory/retry scope manageable.
- Do not switch to one request per full season without measuring memory/source reliability and resumability.
- Do not switch to per-day/per-game fetching for stylistic uniformity without measured evidence.

### Scoped replace and commits

- Each weekly chunk lands via scoped replacement on `_scope`; rerunning a week is idempotent and leaves other weeks intact.
- Each successful week commits independently.
- A failed week rolls back/logs/skips while later weeks continue; one transient source problem should not discard an entire multi-hour bootstrap.
- Never accumulate an entire season's 100+-column pitch data in memory merely to perform one terminal write unless a measured alternative proves better and preserves failure recovery.

### Historical resume

- Past seasons are treated as published/complete and skipped on bootstrap reruns when `season_already_loaded()` confirms data exists.
- The current season always refreshes because it is still in progress.
- If source corrections to historical Statcast require a future refresh strategy, make that explicit rather than silently disabling historical resume optimization.

### Retry and source politeness

- Every pybaseball Statcast request is wrapped in shared retry/backoff.
- A deliberate pause occurs between weekly chunks.
- The pause is preventative politeness for a large public-source workload, not evidence of a published fixed rate limit.
- Keep `CHUNK_PAUSE_SECONDS` configurable/test-patchable so deterministic tests do not sleep through a season.
- Do not introduce aggressive nested concurrency against Baseball Savant without measured source behavior and coordination with the `statcast_leaderboard` connector, which hits the same upstream host.

## Point-in-Time / Research Semantics

Most Statcast pitch observations describe what happened during/after a game, not what was knowable before it. Therefore:

- raw pitch outcomes/tracking are valid for descriptive/postgame research;
- they may contribute to future-game features only through aggregates whose event/availability cutoff precedes the target game;
- do not join a target game's own pitch outcomes into its pregame feature row;
- downstream features must declare the history window/cutoff explicitly.

The connector itself lands source history; it does not decide predictive availability.

## Dependencies

- `pybaseball`
- pandas / psycopg
- shared `load_dataframe` / `season_already_loaded`
- shared `call_with_retry`
- run tracking, DB, and health helpers

## Downstream Consumers

- `conform.py` builds canonical `core.pitch` and monitors join coverage against `raw.statcast_pitch`.
- Research/statistical models may derive pitch, contact, expected-stat, arsenal, movement, batter/pitcher, and other historical features from this source.
- Statcast leaderboard connector provides additional source products that are not always derivable from pitch rows and official aggregate cross-validation tables.

## Known Quirks / Decisions

- 2008–2014 nulls in later Statcast-only fields are real historical nonmeasurement.
- Weekly batching and independent commits are both performance and resilience decisions based on the size of full-history ingestion.
- This connector is not scheduled as a minute-level live feed; health should not manufacture stale alarms for a successfully loaded historical source.
- Baseball Savant/pybaseball can change upstream behavior; isolate callers through this connector rather than leaking pybaseball details into core schemas.

## Work Guidance

- Before changing source dates/columns, compare multiple historical eras, not only a modern-season sample.
- Preserve scope/idempotency semantics when refactoring batching.
- New pitch-level source fields should land source-faithfully first; type/meaning decisions belong in core/gold/stat registries.
- If pybaseball breaks or becomes insufficient, compare a replacement adapter against historical coverage, columns, nulls, retries, runtime, and rights before switching.
- Coordinate Baseball Savant request/concurrency changes with `statcast_leaderboard.py` and CLI same-server grouping.

## Verification

For behavior changes, verify:

- season date-range construction including current/future-year boundaries;
- weekly `_scope` generation and scoped rerun idempotency;
- independent commit/rollback behavior around a failed week;
- historical season skip vs current-season refresh;
- retry/pause behavior with network mocked and sleep patched;
- representative 2008–2014 and 2015+ schema/null fixtures;
- downstream `core.pitch` join-coverage/conformance tests;
- no target-game leakage in any changed downstream feature logic.

Use bounded real-source probes only to verify material coverage/schema claims, then keep CI deterministic.

## Child DOX Index

No child DOX files. This is a leaf connector contract.
