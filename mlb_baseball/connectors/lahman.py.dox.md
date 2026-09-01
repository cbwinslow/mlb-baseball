# lahman.py DOX

## Purpose

Own ingestion of the Lahman Baseball Database into source-faithful
`raw.lahman_*` relations.

## Ownership

Source implementation: `lahman.py`.

The connector owns the Lahman people, batting, pitching, fielding, teams,
postseason, appearances, awards, salaries, Hall of Fame, parks, schools,
managers, franchise, and related source tables enumerated by `TABLES`.

Registry source name: `lahman`.

Focused integration test: `tests/integration/test_lahman_load.py`.

## Source Contracts

- The preferred current source is a manually downloaded SABR Lahman ZIP under
  `downloads/` because the current Box-hosted distribution has no stable
  anonymous/scriptable download API.
- If no local ZIP exists, the connector falls back to the project's preserved
  `baseballdatabank` fork, which is frozen at the 2021 season.
- The fallback must remain visibly labeled stale; do not make a successful
  fallback load look like current Lahman coverage.
- Table/CSV names preserve Lahman's established vocabulary even when they exceed
  the project's usual short-name convention.

## Runtime Contracts

- Lahman is treated as a whole-dataset snapshot.
- `bootstrap()` and `update()` both full-reload all registered Lahman tables.
- If a local ZIP exists, every table is read from that same archive so the
  snapshot is release-coherent.
- Network fallback functions are only used when no local archive is present.
- The run commits after the complete table set is loaded and reports combined row
  count.

Do not silently mix some current local tables with some frozen network tables in
one run.

## Currency and Health

`health_check()` reports a distinct data-currency failure when no local Lahman ZIP
is present, even if the frozen network fallback successfully populated tables.
That distinction is intentional and must remain visible.

## Downstream Context

Lahman is valuable historical/season-level reference and cross-validation data,
not an authoritative replacement for pitch/play-level facts. Preserve source IDs
and schemas so identity/conformance can reconcile evidence explicitly.

Lahman source/reuse rights must be evaluated through `docs/SOURCE_RIGHTS.md`; do
not infer public redistribution permission from package availability.

## Verification

Run:

```bash
uv run pytest tests/integration/test_lahman_load.py -q
uv run ruff check mlb_baseball/connectors/lahman.py tests/integration/test_lahman_load.py
```

Test both local-ZIP and fallback behavior when changing source selection or
currency reporting.
