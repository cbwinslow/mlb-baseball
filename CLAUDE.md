# CLAUDE.md — Operating rules for this repo

This project was rebuilt from scratch after the original (Gemini-built) version accumulated bugs and inconsistent code quality. The rules below exist to prevent a repeat. Read [AGENTS.md](AGENTS.md), [docs/NORTH_STAR.md](docs/NORTH_STAR.md), and [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) before making changes.

## Database names — golden rule

There are exactly two Postgres databases for this project, and their names are fixed, always:

- **`mlb`** — the real, production database. Real ingested data lives here. A destructive command against it is real and, without a backup, unrecoverable.
- **`mlb_test`** — the disposable integration-test database. Tests are free to truncate, drop, and recreate anything in it, any time.

Never conflate the two — not in code, not in scripts, not in an ad-hoc shell command, not in conversation. `TEST_DATABASE_URL` always means `mlb_test` and nothing else; `tests/conftest.py::_assert_test_database_url` hard-fails the entire suite if it doesn't — that guard is why the dangerous direction (a test run touching real data) already can't happen by accident. Don't weaken or remove it. `DATABASE_URL` means "whichever database this process should act on" — production by default, or `mlb_test` only for the duration of a pytest run, which `tests/conftest.py` points it at deliberately and temporarily.

Before running anything destructive (`DROP`, `TRUNCATE`, `DELETE`, `pg_restore`, `mlb restore`, a migration) — including one-off scratch commands, not just committed code — say out loud, in the command itself or in a message to the owner, which database it targets. If a command's target database isn't obvious at a glance, that's a sign to make it explicit before running it, not after.

## Talking to the owner

Explain things in plain, simple language — no heavy technical jargon, no dense paragraphs. Short sentences. If something needs a technical detail, give the plain-English version first and only add the technical term if it's actually needed. Give a direct bottom line before the supporting detail, not after it.

## Suggesting next steps

After finishing a piece of work — writing code, or digging through data/docs — if there's a genuinely useful next step or improvement worth flagging, say so briefly at the end, in plain language. Only offer it once there's actually enough evidence to be confident it's right and that it fits this project's existing rules and direction; spending a few extra minutes checking first is worth it if it turns a guess into a real recommendation. Don't pad every response with a suggestion just to have one — only when there's a real one worth making.

## Scope discipline

- Work is governed by the active plan sequence in `plans/` and durable doctrine in `AGENTS.md`. Do not pull work forward from later plans without explicit authorization and Sol gate review.
- Don't add a data source that isn't listed in `docs/DATA_SOURCES.md`. If a new source is genuinely needed, add it to that doc (cost, access method, license note) in the same change.
- Assume $0/month budget. No paid API, database, or hosting dependency without asking first.

## ML modeling work

Broad technique search is welcome — don't rule out ensembles, neural/attention models, or domain-engineered features. But every technique clears the same bar before it counts as a result: chronological (never random) folds, transparent baselines beaten first, and honest calibration/uncertainty reporting. See `docs/NORTH_STAR.md` and `plans/04-modeling-simulation-and-experiments.md`'s acceptance gate for the full contract; `docs/RESEARCH.md` documents this domain's known leakage failure modes and honest accuracy ceiling.

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
- A new CLI subcommand needs its own CLI-dispatch-level test (through `cli.main([...])` and real argparse, not just a test of the underlying function it calls) — an argparse argument silently missing from a subparser while the handler still reads it crashes at runtime with nothing to catch it otherwise. `tests/unit/test_cli_dispatch.py::test_experiment_run_command_parses_all_its_own_arguments` is the reference example: it caught exactly that (a `--seed` argument accidentally dropped from one subparser while being added to a sibling one), which direct calls to the underlying Python function couldn't have surfaced.

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
- Before writing or changing code, read the module/class it belongs to and its near neighbors first — reuse the patterns and helpers already there instead of duplicating them, and if the change leaves nearby code inconsistent, stale, or duplicated, fix that in the same change rather than filing it away for later.
- When something you're building really will be reused or extended — a real, current need, not a hypothetical one — give it proper structure: small composable pieces, clear interfaces, no hidden coupling. That's still "do today's job well," not the speculative abstraction the rule above warns against; the difference is whether the reuse is real right now, not imagined for later.

## GitHub workflow

Use GitHub for what it's actually good at, not for its own sake — this is a solo project, so the goal is a clear, durable record and correct process, not team-review ceremony.

- **Commits**: direct to `main`, proactively and often — commit after each meaningful, working change rather than batching unrelated work into one commit or waiting to be asked. Push after committing. Every message explains *why*, not just what changed, in enough detail that the reasoning is still clear without the surrounding conversation; see this repo's own history for the pattern. Don't commit half-finished or broken states — "often" means small coherent steps, not partial work.
- **Pull requests**: not the default — direct-to-main is normal here. Open one when a change genuinely benefits from being isolated for review before merging (a large or risky architectural change), or when explicitly asked for one.
- **Issues**: open one for (a) a known, real gap or limitation documented in an ADR (see `docs/DECISIONS.md`) — e.g. a "Revisit if" clause worth tracking as concrete follow-up work, not left as prose only; (b) a real bug found but not fixed in the same change, so it isn't lost; (c) a roadmap/future-work item worth tracking outside `docs/ROADMAP.md`'s prose. Don't open issues for minor style nits, vague hunches, or anything trivial enough to just fix inline.
- **Pre-authorized**: committing, pushing, and creating issues and pull requests on `cbwinslow/mlb-baseball` doesn't need a fresh ask each time — this section is that authorization, per the project owner's explicit instruction. Force-push, closing issues, merging PRs, deleting branches, or editing someone else's content still needs an explicit ask, same as always.

## Before declaring a task finished

- Run the actual test suite and linter — don't assert success without having run them in this session.
- When accepting work from a dispatched or delegated agent (including an external tool), re-run the tests and read the diff yourself before treating it as done — a dispatch's own passing self-report isn't sufficient evidence on its own.
