-- Adds 'backfill' as a valid meta.ingestion_run.mode value, alongside the
-- existing 'bootstrap'/'update'. Needed for polymarket.py's price-history
-- backfill and kalshi.py's candlestick backfill (see docs/DECISIONS.md
-- ADR-049) — both are one-off, owner-triggered historical loads, distinct
-- from the two-function bootstrap()/update() connector contract
-- (docs/ARCHITECTURE.md "Connector contract"), so they get their own mode
-- value rather than overloading 'bootstrap' for something that isn't run
-- as part of a normal bootstrap.

ALTER TABLE meta.ingestion_run DROP CONSTRAINT ingestion_run_mode_check;
ALTER TABLE meta.ingestion_run ADD CONSTRAINT ingestion_run_mode_check
    CHECK (mode IN ('bootstrap', 'update', 'backfill'));
