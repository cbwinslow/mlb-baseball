# statcast_leaderboard.py DOX

## Purpose

Own Baseball Savant season-level tracking and official aggregate leaderboards
that either are not derivable from `raw.statcast_pitch` or are worth landing as
an independent MLB/Savant cross-validation source.

## Ownership

Source implementation: `statcast_leaderboard.py`.

Owned raw relations include:

- `raw.statcast_sprint_speed`
- `raw.statcast_poptime`
- `raw.statcast_framing`
- `raw.statcast_jump`
- `raw.statcast_oaa`
- `raw.statcast_catch_prob`
- `raw.statcast_oaa_direction`
- `raw.statcast_running_split`
- batter/pitcher exit-velocity, expected-stat, percentile, and arsenal tables
- `raw.statcast_pitcher_arsenal_stat`
- `raw.statcast_spin_dir`

Registry source name: `statcast_leaderboard`.

Focused integration test: `tests/integration/test_statcast_leaderboard_load.py`.

## Source and Coverage Contracts

- Leaderboard coverage begins in 2015, matching the full Statcast tracking era.
- Tracking-only leaderboards expose fielder positioning, hang time,
  catcher throw/framing, sprint/running, and related information not present in
  the pitch-level Savant CSV.
- Official aggregate leaderboards that can be recomputed from pitch data are
  intentionally retained as independent cross-validation evidence rather than
  treated as redundant junk.
- Catchers are excluded from the OAA position loop because the upstream OAA
  leaderboard does not support catcher in that view.

## Upstream Library Quirks

The installed pybaseball catcher-framing helper points at a moved Savant endpoint
and returns HTML rather than CSV. `_fetch_framing()` calls the verified current
Savant framing leaderboard directly.

Do not remove that override merely to make all leaderboards use one library path;
first verify pybaseball has actually fixed the endpoint and tie out columns/rows.

## Runtime Contracts

- Most leaderboards are one call per season and use `_season` scoped replacement.
- OAA is loaded once per supported fielding position and uses a composite
  season/position scope.
- `bootstrap()` loads 2015-present and may skip a completed past season **only if
  every currently registered leaderboard table has that season**.
- `_season_fully_loaded()` must remain all-table aware. A single proxy table
  previously caused newly added leaderboard families to miss historical backfill.
- `update()` reloads the current season.
- Each leaderboard is failure-isolated with rollback/commit so one upstream
  endpoint does not block every other table for that season.

## Downstream Context

These are raw source aggregates. A raw Savant leaderboard value is not yet a
project-governed statistic definition: the Stat Registry/coverage/tie-out layer
should own durable formula/version/public semantics when introduced.

Statcast-derived data remains local-research restricted unless the source-rights
profile explicitly changes.

## Verification

Run:

```bash
uv run pytest tests/integration/test_statcast_leaderboard_load.py -q
uv run ruff check mlb_baseball/connectors/statcast_leaderboard.py tests/integration/test_statcast_leaderboard_load.py
```

When adding a leaderboard, update `SIMPLE_LEADERBOARDS`, health coverage, and the
all-table historical-completeness check together.
