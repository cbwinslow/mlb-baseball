# 2026-10-12 — less nightly/5-minute load (code only; nothing deployed or run on production)

Change: `openspec/changes/stabilize-and-market-store` tasks 1.5, 1.6 (code and unit tests; no production data touched).

- Retrosheet event refresh (1.5): a forced refresh whose archive bytes and parser version match the last load skips parse/load (`tests/unit/test_retrosheet_event_skip.py`).
- `mlb_api` update (1.6): roster, transactions and draft are checked at most hourly and written only when the fetched rows changed. The 5-minute tick no longer rewrites ~60k transaction rows. Live games and today's schedule are untouched. Not yet measured: WAL drop over 3 days.
- Coverage/repair (1.4): already handled on `main` by ADR-303 (`repair --apply` then `coverage --light`, no exact counts or date ranges). No change needed here; the open part is only the `pg_stat_statements` check that the nightly run issues no `count(*)` on the market tables.
- Unit suite: 1153 passed, 4 skipped. DB-backed integration tests were not run locally; CI runs them.
