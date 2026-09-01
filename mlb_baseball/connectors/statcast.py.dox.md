# statcast.py DOX

## Purpose

Own Baseball Savant pitch-level tracking ingestion through `pybaseball.statcast()`.
This is the project's detailed pitch/batted-ball tracking source and intentionally
contains both PITCHf/x-era and full Statcast-era records.

## Ownership

Source implementation: `statcast.py`.

Owned raw relation: `raw.statcast_pitch`.

Registry source name: `statcast`.

Focused integration test: `tests/integration/test_statcast_load.py`.

## Source and Coverage Contracts

- Coverage begins in 2008 based on verified pybaseball/Savant availability.
- 2008-2014 is the PITCHf/x era: pitch trajectory/velocity/location can exist but
  later Statcast-specific tracking fields are legitimately null.
- 2015-present is the full Statcast/Trackman era, with broader batted-ball, spin,
  derived, and later bat-tracking fields.
- Do not backfill, synthesize, or drop pre-2015 rows merely because modern columns
  are null. Coverage metadata must distinguish "not measured" from zero/missing
  due to pipeline failure.
- MLB Stats API pitch detail is deliberately not duplicated as the main tracking
  source because Savant provides a substantially richer and more efficient shape.

## Runtime and Scope Contracts

- Data is fetched in weekly date chunks across each season window.
- Each chunk has independent `_scope = <season>_<chunk-start-date>` replacement
  semantics and commits independently.
- `_season` is retained separately for research/querying.
- `bootstrap()` loads 2008 through current year, skips fully loaded completed
  seasons, and always refreshes the in-progress season.
- `update()` reloads only the current season.
- A failed week is rolled back/logged and does not discard successful weeks.
- Requests use bounded retry/backoff.
- `CHUNK_PAUSE_SECONDS` is deliberate source politeness and remains patchable to
  zero in tests.

Do not accumulate a whole season in memory before one giant write; weekly commit
boundaries are both a memory and resilience contract.

## Performance Contract

The weekly batching strategy was chosen from measured source behavior. Do not
switch to per-day/per-game fetching or concurrency on intuition alone. Benchmark
representative ranges and preserve source etiquette before changing the fetch
shape.

## Downstream Context

This raw relation feeds pitch/batted-ball research and later features. Statistical
use must respect era coverage and point-in-time availability. Source-provided
expected/derived columns still require definition/coverage documentation before
becoming a governed project stat.

Statcast is currently local-research restricted under the project's rights
profile; do not place it into `public_safe` exports without an explicit rights
change.

## Verification

Run:

```bash
uv run pytest tests/integration/test_statcast_load.py -q
uv run ruff check mlb_baseball/connectors/statcast.py tests/integration/test_statcast_load.py
```

Verify weekly scope replacement, failed-week isolation, completed-season skip,
current-season refresh, and pre-2015 null semantics when changing this connector.
