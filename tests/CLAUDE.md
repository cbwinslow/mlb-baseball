@AGENTS.md

# Claude Code — test rules

Shared test/database-isolation truth lives in `AGENTS.md` and `tests/conftest.py`. This file adds Claude-specific behavior for test work.

## Claude-specific discipline

- Before changing database fixtures, read `tests/conftest.py` directly. Do not rely on older root prose about a shared `mlb_test` database.
- When generating a regression test, reproduce the mechanism that failed (transaction state, argparse dispatch, identity collision, PIT cutoff, schema drift) rather than only asserting the final symptom.
- Do not ask a subagent to run destructive SQL against an ambiguous database. Its prompt must say that pytest owns a run-specific disposable database and production `mlb` is forbidden.
- For a failing integration test, inspect the real PostgreSQL error/transaction state before proposing mocks or fixture relaxation.
- When tests expose stale documentation/DOX, fix the owning context in the same change if the verified behavior is clear.

## Verification

- Run the narrow failing/changed test first.
- Re-run related integration coverage after fixing a transaction/conformance/connector bug.
- Do not report a full-suite pass unless Claude actually ran the full suite in the current environment.
- Treat order/randomization failures as potential hidden shared-state bugs, not flaky noise by default.
