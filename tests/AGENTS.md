# Test subsystem DOX

## Purpose

This subtree owns executable correctness evidence for the repository. Its job is to prove pure logic, CLI behavior, source parsing, PostgreSQL behavior, ingestion idempotency, migrations, conformance, research/statistical formulas, and regressions without touching production data.

Read root `AGENTS.md` before this file. When test-database wording elsewhere conflicts with this file, verify `tests/conftest.py` and treat the executable fixture behavior as the observation source, then repair stale prose.

## Ownership

- `tests/unit/**`: pure or isolated behavior; no real external network and normally no database.
- `tests/integration/**`: behavior that depends on PostgreSQL, migrations, transactions, locks, COPY/load semantics, connector loads, conformance, and end-to-end contracts.
- `tests/conftest.py`: repository-wide pytest fixtures and disposable database lifecycle.
- Test fixtures/sample payloads used to make network-dependent code deterministic.

## Current Database Isolation Contract

The current `tests/conftest.py` implementation creates **one isolated disposable PostgreSQL database per pytest process** using `pytest-postgresql`'s `postgresql_noproc` fixture.

Important details:

- `TEST_DATABASE_URL` defaults from a base connection such as `postgresql:///mlb_test`, but the suite does **not** mutate that base database.
- Each pytest invocation creates a high-entropy name such as `mlb_test_<token>_tmpl` and points both `TEST_DATABASE_URL` and `DATABASE_URL` at that run-specific database before test modules are collected.
- The fixture migrates the isolated database once, applies test-only durability optimizations there, and lets pytest-postgresql's janitor remove it after the session.
- Concurrent pytest invocations therefore use separate databases and must not share mutable test state.
- `_assert_test_database_url()` must continue to reject any database name that is not clearly a disposable test target.
- Production database `mlb` must never be used by pytest.

Do not reintroduce a shared mutable `mlb_test` assumption in agent instructions, scripts, or tests unless the fixture architecture is deliberately redesigned and documented first.

## Local Contracts

- Use **real PostgreSQL** for behavior involving transactions, locks, migrations, COPY, constraints, SQL semantics, or database state. Mocking those behaviors can hide real regressions.
- Mock/capture the network, not the database, for routine connector integration tests.
- Tests must be order-independent and own/clean their state.
- If a failed transaction can occur, rollback before cleanup/teardown queries so cleanup does not fail inside an aborted transaction.
- Connector integration tests should prove rows load and prove idempotency/scoped replacement by running the operation twice.
- New CLI subcommands need dispatch-level coverage through the real argument parser, not only direct calls to handler functions.
- Statistical formulas need deterministic hand-calculated fixtures and credible external/tie-out evidence where the project doctrine requires it.
- Point-in-time tests must make future leakage impossible or detectable; do not make tests pass by relaxing availability semantics.
- Regression tests should reproduce the actual bug mechanism, not only the final symptom.
- Test-only speed changes are permitted only inside disposable test databases and must never leak into production configuration.

## Work Guidance

- Start with the smallest test that can fail for the intended reason.
- Prefer explicit fixtures over hidden cross-test state.
- Keep sample network payloads minimal but structurally representative.
- Do not depend on public-network availability in CI.
- If adding xdist later, first prove per-worker/per-process database isolation and fixture safety; do not assume the current one-database-per-pytest-process contract is automatically xdist-safe.
- `pytest-randomly` is useful only after deterministic ordering assumptions have been removed; randomization failures must be treated as real state-coupling bugs until proven otherwise.
- Mutation testing belongs on a small set of critical identity/math/PIT code, not indiscriminately across the whole repository.

## Verification

Typical commands:

- `uv run pytest tests/unit/<target>.py`
- `uv run pytest tests/integration/<target>.py`
- `uv run pytest`

Also run the relevant lint/type/SQL checks for changed production code. Do not claim full-suite success unless it was run in the current environment.

## Documentation Contract

When `tests/conftest.py` changes database lifecycle, fixture scoping, environment variables, or safety guards, update this file and any root/Claude docs that describe those mechanics in the same change.

## Child DOX Index

No child DOX yet. Add `unit/AGENTS.md` or `integration/AGENTS.md` only if those subtrees accumulate stable, distinct rules that cannot remain concise here.
