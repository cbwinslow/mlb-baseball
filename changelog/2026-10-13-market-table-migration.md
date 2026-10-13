# 2026-10-13 — migration 0117: typed market price tables (code only; nothing run on production)

Change: `openspec/changes/stabilize-and-market-store` task 2.5.

- `0117_market_price_tables.sql` adds `meta.create_market_tables(suffix)` (typed tables; TimescaleDB hypertables with columnar compression when the extension exists, plain tables otherwise) and empty `raw.polymarket_price_reject` / `raw.kalshi_candle_reject`. It does not touch `raw.polymarket_price` or `raw.kalshi_candle`.
- `0116_postgres_extensions.sql` now also creates `timescaledb`, first in the list, because `pg_duckdb` defines `time_bucket` and blocks a later `CREATE EXTENSION timescaledb`. Production already has the extension; re-applying is a no-op.
- Tests: `tests/integration/test_market_tables.py`, `test_optional_extensions.py`, `test_migrations.py` on a disposable database.
- Production steps (create `_new`, copy, swap) are tasks 2.6 and 2.8 and need owner approval.
