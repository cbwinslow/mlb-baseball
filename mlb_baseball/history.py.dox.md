# `history.py` DOX

## Purpose

Own the shared rule for when a prediction-market history is complete, and the threaded
per-market trade backfill used by the Kalshi and Polymarket connectors (ADR-304).

## Ownership

Implementation: `history.py`. Callers: `connectors/kalshi.py`, `connectors/polymarket.py`.

## Contracts

- `is_complete`: the item ended at least a day ago **and** was fetched after it ended.
- `backfill_trades`: one market per transaction (delete that market's rows, copy the new ones,
  write the ledger item). No rows returned keeps what is stored. Failures are ledgered and the
  run raises after trying every market. It takes no workflow lock.
- Values are stored as text, as in other `raw` tables.

## Verification

`tests/integration/test_kalshi_load.py` and `test_polymarket_load.py` (trade and refetch cases).

## Child DOX Index

No child DOX files.
