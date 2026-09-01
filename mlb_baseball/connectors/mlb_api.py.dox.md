# mlb_api.py DOX

## Purpose

Own the MLB Stats API acquisition subsystem. This module currently combines
schedule/history, standings, rosters, transactions, game detail, analytics,
reference data, probable starters, and live snapshots behind one registry
connector facade.

It is a known gravity well and a future decomposition candidate. Preserve
`bootstrap()`, `update()`, health behavior, and registry-facing semantics while
splitting internals; do not rewrite the subsystem wholesale.

## Ownership

Source implementation: `mlb_api.py`.

Major owned raw relations include:

- `raw.mlb_schedule`
- `raw.mlb_standing`
- `raw.mlb_roster`
- `raw.mlb_transaction`
- `raw.mlb_playbyplay`
- `raw.mlb_live_game` — append-only live state snapshots
- `raw.mlb_venue`
- `raw.mlb_team_history`
- `raw.mlb_person`
- `raw.mlb_draft`
- `raw.mlb_boxscore_batting`
- `raw.mlb_boxscore_pitching`
- `raw.mlb_boxscore_fielding`
- `raw.mlb_umpire`
- `raw.mlb_win_prob`
- `raw.mlb_linescore`
- `raw.mlb_game_context`
- `raw.mlb_probable` — probable-pitcher change snapshots
- official-scorer/datacaster reference outputs currently handled by this subsystem.

Registry source name: `mlb_api`.

Primary integration contract: `tests/integration/test_mlb_api_load.py`.

## Source and Coverage Map

This connector deliberately uses different historical boundaries by endpoint
because API availability and duplication cost differ:

- schedule: 1901-present;
- standings: 1969-present (division era);
- rosters: 1901-present;
- transactions: about 2000-present;
- draft: 1965-present;
- play-by-play / box score / per-game umpire detail: current Retrosheet-gap era
  beginning at the configured `FIRST_PLAYBYPLAY_YEAR` (currently 2026);
- win probability / line score / game context: verified from 1950-present;
- venues/team history/person: reference-style full/current catalog derived through
  the API and historical roster/team IDs.

Do not force one global `FIRST_YEAR` across these endpoint families. The differing
boundaries encode measured source capability and duplication strategy.

## Third-Party Client Contract

The subsystem currently uses ToddRob's `MLB-StatsAPI` (`statsapi`) behind project
wrappers.

- All normal `statsapi.get()` calls must receive an explicit request timeout
  through `_get()` or another bounded adapter; an unbounded third-party request
  previously hung historical bootstrap indefinitely.
- The `statsapi.schedule()` convenience helper does not expose request kwargs, so
  `_timed_schedule()` temporarily swaps a timed adapter under a process-local
  reentrant lock. Preserve thread safety if this path changes.
- Transactions use `force=True` because the installed library's required-param
  validation rejects a valid date-range parameter combination.
- A future sportsdataverse/new MLB client may replace transport/parsing only after
  a bounded parity spike proves coverage, history, null/type behavior, retries,
  performance, provenance, and tests. Keep the project adapter/facade stable.

## Runtime Contracts

### Bootstrap

- Loads cheap per-season history (schedule/standings/rosters/transactions) with
  independent season commit/failure boundaries.
- Loads reference families (venues, team history, people, draft) in bounded steps.
- Loads expensive game detail only for the configured non-duplicative era, with
  per-game isolation so one broken game cannot abort a season/history run.
- Completed immutable historical analytics/seasons may be skipped using explicit
  completeness checks; adding a new table must not make an old proxy-completeness
  check incorrectly skip its backfill.

### Update

- Refreshes current-season schedule/standings/roster/transactions/draft and
  appropriate current game detail.
- Refreshes in-progress/finished current games with game-scoped replacement as
  plays/stat lines evolve.
- Captures live state as append-only observations.
- Captures probable pitchers as append-only **changes**, preserving scratches and
  announcement history rather than only the latest name.
- Expensive reference catalogs are not refreshed every five-minute update; that is
  a deliberate cadence tradeoff, not an omission.

## Point-in-Time Contracts

### Live game snapshots

`raw.mlb_live_game` is append-only. Each capture represents what the MLB API
reported at that observation time. Never replace historical captures with final
game state.

### Probable pitchers

`raw.mlb_probable` preserves announcement/scratch changes and source person IDs.
This relation exists specifically so future-game starter features can be joined to
canonical players without using a bare display name or future final starter.

### Analytics

Win-probability/game-context fields are source-provided analytics. When used in
project research, distinguish source-provided retrospective values from features
that were actually knowable pregame/at a given in-game cutoff.

## Concurrency and Retry Contracts

- General requests have bounded timeout/retry behavior.
- Historical analytics use a faster timeout and bounded parallel worker strategy
  because thousands of independent game requests are involved.
- Server `Retry-After` handling for the analytics hot path is capped so one worker
  cannot stall an entire bounded batch for minutes.
- Do not increase worker count or reduce timeouts without representative
  measurements and source-rate-limit consideration.
- Per-season/per-game exception isolation remains a second resilience layer after
  retry exhaustion.

## Relationship to Other Sources

- Retrosheet remains the major independent historical event/game source and a
  cross-validation asset.
- Statcast/Savant remains the richer pitch-tracking source; do not duplicate its
  ~119-column tracking surface through the less-detailed MLB game feed.
- MLB transactions continue beyond Retrosheet's frozen transaction database.
- MLB schedule/live/probables provide current/future state Retrosheet cannot.

Overlap is deliberate where it creates independent validation. Avoid duplicate
remote cost when another source is clearly richer and historically complete.

## Decomposition Direction

When this module is next substantially refactored, prefer a stable facade over
submodules such as:

```text
connectors/mlb/
  connector.py
  transport.py
  schedule.py
  standings.py
  rosters.py
  people.py
  venues.py
  transactions.py
  play_by_play.py
  boxscore.py
  analytics.py
  probable.py
  live.py
```

Exact names are not binding. The binding requirement is cohesive ownership with
backward-compatible registry behavior and focused tests. Move this `.dox.md` into
a child `connectors/mlb/AGENTS.md`/local DOX map as decomposition lands rather
than leaving stale documentation at the old path.

## Rights

MLB Stats API data is not currently part of the conservative Retrosheet-only
`public_safe` release. Preserve source-profile enforcement and do not broaden
redistribution from this connector alone.

## Verification

Primary focused suite:

```bash
uv run pytest tests/integration/test_mlb_api_load.py -q
uv run ruff check mlb_baseball/connectors/mlb_api.py tests/integration/test_mlb_api_load.py
uv run mypy mlb_baseball/connectors/mlb_api.py
```

Depending on the changed family, also run downstream conformance, starter/
probable, market/PIT, health, or pipeline tests. For transport/client replacement,
perform a bounded live parity check against representative schedule, person,
roster, venue, PBP, analytics, and probable-pitcher endpoints; mocked tests alone
cannot prove upstream response parity.
