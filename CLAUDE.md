# CLAUDE.md — Operating rules for this repo

This project was rebuilt from scratch after the original (Gemini-built) version accumulated bugs and inconsistent code quality. The rules below exist to prevent a repeat. Read [AGENTS.md](AGENTS.md), [docs/NORTH_STAR.md](docs/NORTH_STAR.md), and [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) before making changes.

## Scope discipline

- Work is governed by the active plan sequence in `plans/` and durable doctrine in `AGENTS.md`. Do not pull work forward from later plans without explicit authorization and Sol gate review.
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
- Schema-layer names are exactly `raw`, `core`, `gold` — no `bronze`/`silver` prefixing on table names within them (the schema itself already says which layer a table is in; see `docs/ARCHITECTURE.md` "Layered schema" and ADR-013).

## Operational health checks

`mlb doctor` exists to answer "is everything actually working?" in one command — DB connectivity, schema presence, migration status, and per-connector health. When writing or changing a connector or shared module, think about how `mlb doctor` should be able to check it, in the same change, not bolted on later:

- Every connector module exposes `health_check() -> list[Check]` (see `mlb_baseball/health.py` for the `Check` type and shared helpers like `check_table_has_rows`/`check_last_run`). Use the shared helpers instead of writing ad-hoc queries per connector.
- If a new shared module has a way to be "unhealthy" (unreachable dependency, stale data, a check worth automating), give it a health check too rather than leaving it invisible until something breaks silently.

## Code quality

- No dead code, no commented-out blocks, no TODOs left behind as a substitute for finishing the work.
- No silent `except: pass` — failures in ingestion must be visible (logged with enough context to debug, and surfaced as a non-zero exit / failed run).
- Prefer explicit, boring code over cleverness. This is a data pipeline; predictability matters more than elegance.
- Don't build abstractions for sources we don't have yet. Three similar connectors is fine; a plugin framework for a hypothetical fourth is not, until there's a fourth.

## GitHub workflow

Use GitHub for what it's actually good at, not for its own sake — this is a solo project, so the goal is a clear, durable record and correct process, not team-review ceremony.

- **Commits**: direct to `main`, only when the user explicitly asks (never proactively — see the Git Safety Protocol). Every message explains *why*, not just what changed; see this repo's own history for the pattern.
- **Pull requests**: not the default — direct-to-main is normal here. Open one when a change genuinely benefits from being isolated for review before merging (a large or risky architectural change), or when explicitly asked for one.
- **Issues**: open one for (a) a known, real gap or limitation documented in an ADR (see `docs/DECISIONS.md`) — e.g. a "Revisit if" clause worth tracking as concrete follow-up work, not left as prose only; (b) a real bug found but not fixed in the same change, so it isn't lost; (c) a roadmap/future-work item worth tracking outside `docs/ROADMAP.md`'s prose. Don't open issues for minor style nits, vague hunches, or anything trivial enough to just fix inline.
- **Pre-authorized**: creating issues and pull requests on `cbwinslow/mlb-baseball` doesn't need a fresh ask each time — this section is that authorization, per the project owner's explicit instruction. Closing issues, merging PRs, or anything destructive (force-push, deleting branches, editing someone else's content) still needs an explicit ask, same as always.

## Before declaring a task finished

Run the actual test suite and linter — don't assert success without having run them in this session.
