# CLAUDE.md — Operating rules for this repo

This project was rebuilt from scratch after the original (Gemini-built) version accumulated bugs and inconsistent code quality. The rules below exist to prevent a repeat. Read [docs/NORTH_STAR.md](docs/NORTH_STAR.md) and [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) before making changes.

## Scope discipline

- We are in **Phase 1: data ingestion pipeline**. Do not start on ML modeling or the Astro website unless explicitly asked, even if it seems convenient to do "just a little" of it now.
- Don't add a data source that isn't listed in `docs/DATA_SOURCES.md`. If a new source is genuinely needed, add it to that doc (cost, access method, license note) in the same change.
- Assume $0/month budget. No paid API, database, or hosting dependency without asking first.

## Definition of done

A task is not complete until:
1. Tests exist and pass for the new/changed code — see "Testing" below for what kind goes where.
2. The linter/formatter/type-checker configured for the repo passes clean.
3. Re-running the ingestion step is idempotent — running it twice doesn't duplicate or corrupt data. (This should be a *test*, not just a claim — see `tests/integration/test_load_dataframe.py::test_rerunning_truncates_instead_of_duplicating` for the pattern.)
4. Errors from upstream sources (rate limits, malformed responses, schema drift) are handled explicitly, not silently swallowed.
5. Any new data source or schema change is reflected in the docs in the same change, not as a follow-up.

## Testing

- `tests/unit/` — pure logic, no I/O (parsing, column-name sanitizing, dispatch logic with mocked connectors). Fast, no fixtures needed beyond `monkeypatch`.
- `tests/integration/` — anything that touches Postgres. Runs against a real, dedicated `mlb_test` database (never the real `mlb` one) — see `README.md` "Testing". Mock the network (fixture CSV/JSON content), not the database — real Postgres is cheap to run against locally and mocking it hides real bugs (e.g. transaction/lock behavior, COPY column mismatches).
- Every connector needs an integration test that actually loads rows and asserts idempotency (run twice, same row count) — not just a unit test on its parsing helpers.
- If a bug involved a transaction, a lock, or connection state, write the regression test through the real fixtures (`db_conn`, non-autocommit, matching production) — not a mock, or the regression can silently stop being tested. `tests/integration/test_ingest_tracking.py::test_failure_path_logs_error_and_leaves_connection_usable` is the reference example: it caught a real bug (`track_run` not rolling back before logging a failure) that a mocked connection would never have surfaced.

## Naming convention

- Every object we name ourselves — schemas, tables, columns, functions, modules, config keys — gets a short name: **one word, two at most.** Not `bref_pitching_war_raw`; `pitching_war` (schema already says `raw`).
- Prefixes are allowed but only when actually needed to disambiguate (e.g. two different sources landing conceptually similar data). Don't prefix by default.
- Exception: raw-layer columns *and table names* that mirror a source's own established naming verbatim (e.g. the Chadwick register's `key_mlbam` column, or Lahman's own table names like `AwardsPlayers`/`HallOfFame` snake_cased to `awards_players`/`hall_of_fame`) are exempt — don't abbreviate a well-known source's own vocabulary to hit the word-count target. Source-faithfulness there is the point (see `docs/ARCHITECTURE.md`), and community-familiar names beat invented shorthand that no one recognizes.

## Operational health checks

`mlb doctor` exists to answer "is everything actually working?" in one command — DB connectivity, schema presence, migration status, and per-connector health. When writing or changing a connector or shared module, think about how `mlb doctor` should be able to check it, in the same change, not bolted on later:

- Every connector module exposes `health_check() -> list[Check]` (see `mlb_baseball/health.py` for the `Check` type and shared helpers like `check_table_has_rows`/`check_last_run`). Use the shared helpers instead of writing ad-hoc queries per connector.
- If a new shared module has a way to be "unhealthy" (unreachable dependency, stale data, a check worth automating), give it a health check too rather than leaving it invisible until something breaks silently.

## Code quality

- No dead code, no commented-out blocks, no TODOs left behind as a substitute for finishing the work.
- No silent `except: pass` — failures in ingestion must be visible (logged with enough context to debug, and surfaced as a non-zero exit / failed run).
- Prefer explicit, boring code over cleverness. This is a data pipeline; predictability matters more than elegance.
- Don't build abstractions for sources we don't have yet. Three similar connectors is fine; a plugin framework for a hypothetical fourth is not, until there's a fourth.

## Before declaring a task finished

Run the actual test suite and linter — don't assert success without having run them in this session.
