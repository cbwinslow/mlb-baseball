# 2026-10-12 — nightly: health findings no longer fail the night; run watchdog

Change: `openspec/changes/stabilize-and-market-store` tasks 1.2, 1.3 (code only; no production data touched).

- `mlb nightly` now treats `doctor --populated`, `coverage`, `schema-watch` and `repair --dry-run` as health steps: they still run, but a finding does not change the exit code or alert per step. One "health digest" alert is sent at the end. Pipeline steps (migrate, update, conform, report, predict) behave as before.
- The run writes `~/.mlb/nightly_run.json` at start and finish. `mlb nightly --check` alerts if a run started but did not finish within 5 h, or none started in 26 h. It is not yet scheduled in cron (needs owner approval; see tasks.md 1.2).
- Alert path: `scripts/mlb_alert.sh` (local file, optional Discord/ntfy) and `scripts/mlb_alert_banner.sh` (login banner), configured through gitignored `mlb.toml`.
- Tests: `tests/unit/test_nightly_health.py` (17, no database). The existing integration test for `update` retries was not re-run locally (it needs a disposable PostgreSQL database); CI runs it.
