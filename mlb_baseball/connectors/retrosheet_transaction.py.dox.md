# retrosheet_transaction.py DOX

## Purpose

Own Retrosheet's historical transaction database: trades, sales, releases,
waivers, free agency, injured-list moves, call-ups, draft transactions, and related
transaction records.

## Ownership

Source implementation: `retrosheet_transaction.py`.

Owned raw relation: `raw.retrosheet_transaction`.

Registry source name: `retrosheet_transaction`.

Focused integration test: `tests/integration/test_retrosheet_transaction_load.py`.

## Source and Coverage Contracts

- Source archive: `retrosheet.org/transactions/tranDB.zip`.
- `tran.txt` is headerless with the explicit 16-field layout defined by
  `TRANSACTION_FIELDS`.
- Retrosheet froze this transaction product on 2021-11-26. This is a real source
  boundary, not connector staleness to hide or repair.
- Post-freeze/current transactions are supplied by other sources such as MLB Stats
  API; do not imply this table is current beyond the Retrosheet freeze.

## Runtime Contracts

- `bootstrap()` full-loads/replaces the historical snapshot.
- Despite older prose describing `update()` as a no-op, the current implementation
  intentionally reruns the same full load so an upstream correction to the frozen
  archive can be picked up. Treat the implementation as current truth.
- The source file is manifest-tracked before parsing.
- Reruns replace the snapshot and remain idempotent.
- The source's transaction IDs, team/league IDs, dates, approximation flags, and
  free-text info remain source-faithful in raw.

## Downstream Context

Do not conflate source freshness with event date. Historical transaction records
remain useful after the feed's maintenance freeze; current roster/transaction
research must join or prefer a source that actually covers the relevant date.

Canonical transaction modeling should preserve source and observed/retrieved
provenance when multiple sources overlap.

## Verification

Run:

```bash
uv run pytest tests/integration/test_retrosheet_transaction_load.py -q
uv run ruff check mlb_baseball/connectors/retrosheet_transaction.py tests/integration/test_retrosheet_transaction_load.py
```

Verify the 16-column source alignment and full-reload idempotency when parsing or
update semantics change.
