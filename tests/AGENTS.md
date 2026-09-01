# Tests DOX

## Purpose

Own automated correctness verification for pure Python logic, CLI behavior,
PostgreSQL integration behavior, source connector loading, statistical formulas,
and regression cases.

## Ownership

This subtree owns:

- `tests/unit/**` pure/unit and dispatch-level tests;
- `tests/integration/**` real-PostgreSQL integration tests;
- `tests/conftest.py` database isolation and shared fixtures;
- deterministic fixture data used instead of live network calls;
- test-only database performance relaxations and teardown discipline.

Application behavior remains owned by source modules. Tests prove contracts; they
must not become a second implementation of production logic.

## Local Contracts

### Database isolation

`tests/conftest.py` is the source of truth.

- Each pytest process gets a unique high-entropy disposable PostgreSQL database
  created through `pytest-postgresql`'s `postgresql_noproc` machinery.
- `TEST_DATABASE_URL` is the base connection/default and is rewritten at import
  time to the per-run working template database.
- `DATABASE_URL` is also redirected to that disposable database for the suite.
- The production database must never be a test target.
- `_assert_test_database_url()` must continue rejecting database names without
  `test` in the name; never weaken that guard casually.
- Do not restore the former shared mutable `mlb_test` test-run model. Concurrent
  pytest invocations must remain isolated from one another.
- Current test-only durability relaxations (`synchronous_commit=off` and UNLOGGED
  play/pitch partitions) are allowed only for the disposable test database.

### Unit vs integration

- Unit tests contain no real network or database I/O.
- Anything whose correctness depends on PostgreSQL types, transactions, locks,
  `COPY`, constraints, partition behavior, SQL semantics, migrations, or teardown
  must use the real integration database.
- Do not mock PostgreSQL when the bug could be transaction/connection/DDL/COPY
  specific.
- Mock/capture the **network**, not the database, for connector integration tests.

### Fixture ownership and cleanup

- Fixtures must clean up state they create and must be order-independent.
- When teardown SQL uses the same non-autocommit connection as the test, rollback
  lingering transactions before destructive cleanup as required by
  `drop_tables_after`.
- A fixture that creates durable relation state owns deleting/resetting it even
  when the test fails.
- Avoid hidden dependencies on prior tests, alphabetical order, or one worker.

### Regression quality

- Reproduce the real failure mode at the lowest layer that can catch it.
- CLI subcommands require dispatch-level tests through `cli.main([...])` and real
  argparse, not only direct handler tests.
- Formula/stat changes require deterministic hand-calculated examples and domain
  edge cases; where a credible external aggregate exists, add an explicit tie-out
  tolerance instead of testing only against our own implementation.
- Connector changes require idempotency coverage: run the load/update behavior
  twice and prove row identity/count semantics remain correct.
- Bugs involving failure paths should assert that connections remain usable and
  run/error bookkeeping is correct after exceptions.

## Work Guidance

Before changing a test, read the production code it verifies and nearby tests so a
new fixture/helper does not duplicate an established pattern.

Prefer small tests with explicit expected values. Hypothesis/property tests are
useful for invariant-heavy pure logic but do not replace concrete regression
fixtures.

Do not hide flaky behavior with sleeps or broad retries. Fix time/order/isolation
causes or document a truly external nondeterministic dependency.

When xdist is eventually introduced, per-worker database isolation must be proven
before enabling it in default CI; do not assume current per-process isolation is
worker-safe without measurement.

## Verification

Use the repository's current toolchain:

```bash
uv run pytest tests/unit/<relevant_test>.py
uv run pytest tests/integration/<relevant_test>.py
uv run pytest
uv run ruff check .
uv run mypy mlb_baseball
```

Run only proportional checks during development, then the repository-required CI
set before merge. SQL changes also require the SQLFluff/SQL ownership checks
configured in CI.

Never claim tests passed unless they were run in the current environment/session;
when a connector/tool cannot run them, state that clearly and rely on CI rather
than inventing success.

## Child DOX Index

No child DOX files yet. Add `unit/AGENTS.md` or `integration/AGENTS.md` only if the
local contracts diverge enough that this file becomes noisy.
