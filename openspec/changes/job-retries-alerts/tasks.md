## 1. Quick view

- [x] 1.1 Migration: add `attempt` to `meta.ingestion_run` and admit `nightly` in the `mode` check; verify it applies on the disposable test database and existing run tracking tests still pass
- [x] 1.2 Implement `mlb runs` (one query, last result, age, duration per job) and `--check` with per-source thresholds; verify `tests/unit/test_cli_dispatch.py` cases for healthy, failed-last and stale (real argparse via `cli.main`) and an integration test against seeded `meta.ingestion_run` rows

## 2. Alert hook

- [x] 2.1 Add the `alert_command` setting (env and `mlb.toml`) and a small `alert()` helper that runs it without a shell, passes the message on stdin and `$1`, and swallows its own failure; verify unit tests for unset, success and failing command (exit code unchanged)

## 3. Supervisor

- [x] 3.1 Add `mlb_baseball/nightly.py` running migrate, update, conform, report, predict and the populated check as child processes with the current gates (migrate failure stops all; report only after a successful conform); verify tests with fake child commands that cover each gate
- [x] 3.2 Add bounded retry for `update` limited to failed sources, treating a killed child as a failed attempt, and record one `meta.ingestion_run` row per attempt; verify a PostgreSQL integration test with a source that fails once then succeeds (no duplicate rows) and one that exhausts retries (alert called once)
- [x] 3.3 Register `mlb nightly` in the CLI and reduce `scripts/mlb_daily_update.sh` to flock + log + `exec mlb nightly`, keeping the existing log file name; verify the script's existing tests and a manual dry run through the shim

## 4. Docs and the real run

- [x] 4.1 Document `alert_command` with the ntfy and webhook examples in `docs/USER_MANUAL.md` and update `cli.py.dox.md`; verify `scripts/check_dox.py` and `openspec validate job-retries-alerts` pass
- [ ] 4.2 Run `mlb runs` and `mlb runs --check` against production (read-only) and one real `mlb nightly` night; record outputs in `results.md` and verify a deliberately failing source triggers exactly one alert on a test configuration
