# Coverage DOX (`mlb coverage`)

## Purpose

`mlb coverage` answers "what are we supposed to hold, and what do we hold?" for every raw table: the unit of coverage (season, game, date, market, file), the expected count and where the expectation comes from, the held count, what is missing, and the exact `mlb ingest ...` command that closes the gap. It is the comparison target for the idempotent ingest commands: run it, run the printed fix, run it again.

Read root `AGENTS.md` and `mlb_baseball/AGENTS.md` first.

## Ownership

- `registry.py`: the single list of datasets. One `Dataset(...)` entry per raw table: expectation, fix command, caveat. Year bounds come from the connectors' own constants (`FIRST_WIN_PROB_YEAR`, `FIRST_YEAR`, ...), not copies.
- `model.py`: the expectation kinds (`Seasons`, `Games`, `GameDates`, `KalshiCandles`, `PolymarketWindows`, `Present`, `Referenced` (entity tables: every id other tables use exists here, one line per referencing column), `ManifestFiles`, `NoExpectation`) and `Group`. Each kind turns an expectation into `expected / held / accounted` counts per bucket with plain SELECTs.
- `live.py`: live checks (`--probe` only): ask the publisher, then compare with the table. Today `MlbScheduleTotals` (Stats API `totalGames` per season over plain HTTP, with the American/National League count alongside). Paced, finite timeout, shared retry; a request that fails is reported as an error, never counted as zero. A check lives in `registry.LIVE_CHECKS`.
- `engine.py`: runs the measurements in one `READ ONLY` transaction and builds the report; reports any raw table that is not registered.
- `render.py`: text, markdown and JSON views. JSON has sorted keys and no timestamps.
- `__init__.py`: the `run()` entry point that `cli.py` calls; `cli.py` only parses arguments.

## Local Contracts

- Dates: `registry.DATE_COLUMNS` declares one text date column per table; `meta.data_date_range` (migration 0113) reports first/last date and how many values are not a date. A table not listed reports no range; a unit test checks every declared column exists in `docs/RAW_INVENTORY.md`.
- Flags: `--probe` (live checks), `--source`, `--table`, `--json|--markdown`, `--missing-only` (hide clean tables), `--fail-on-gap` (exit 1 on any gap; a gap is any status except `complete` and `no_expectation`, so an unmeasurable table fails closed). There is deliberately no flag that runs a fix.
- Read-only. The engine opens the transaction with `SET TRANSACTION READ ONLY`; a write is a database error, not a policy. Never add a write here, and never a repair step: the command reports, the existing idempotent ingest fixes.
- Never pass silently. A table with no derivable expectation prints `no expectation defined: <reason>`; a table in the database that the registry lacks is reported as unregistered; an expectation with nothing to derive it from reports `no_basis`; a missing table or input reports `table_absent` / `inputs_absent`.
- A game or market whose ledger item (`meta.ingestion_item`) is `unavailable` is a recorded source gap: it counts as accounted for, not missing. `loaded` and `unavailable` are the only accounted statuses; `failed` stays missing. The ledger dataset must match the table (a `context_metrics` gap does not excuse a win-probability row).
- Game expectations use the same definition as the doctor coverage check (`mlb_api.py::_analytics_durable_coverage_check`): distinct final games in `raw.mlb_schedule`. Keep the two in step; if one changes, change the other.
- A fix command must be a real `mlb ingest` invocation. If the idempotent command cannot repair a gap (for example Statcast's `season_already_loaded` skip of a partly loaded past season), say so in the entry's `caveat` instead of printing a command that will do nothing.
- Expectations are derived from data we hold or constants the connectors already record. Do not hard-code a count taken from what the database holds today; that would make the comparison circular.
- Adding a raw table: add its `Dataset` entry in the same change; `tests/unit/test_coverage_registry.py` fails if a table in `docs/RAW_INVENTORY.md` is not registered.

## Verification

- `uv run pytest tests/unit/test_coverage_registry.py tests/integration/test_coverage.py` (real PostgreSQL; the integration file seeds a gap, a ledger source gap, an empty table, Kalshi markets and a download manifest).
- `uv run mypy mlb_baseball/coverage`, `uv run ruff check`, `python3 scripts/check_dox.py`.
- Manual, read-only: `mlb coverage --source mlb_api` against the production database (needs `DATABASE_URL`; it never writes).

## Child DOX Index

No child DOX.
