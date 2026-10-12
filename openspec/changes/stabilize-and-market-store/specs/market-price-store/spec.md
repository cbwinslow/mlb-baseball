# Spec Delta

## Purpose
Defines how Polymarket and Kalshi price history is stored in PostgreSQL so that it is typed, compact, point-in-time honest, and kept together in one store.

## ADDED Requirements

### Requirement: One store for all market data
Polymarket and Kalshi market definitions, snapshots, candles and prices SHALL live in the same PostgreSQL database.

#### Scenario: Matching a market price to a game
- **WHEN** a query joins a market price to a game
- **THEN** it needs no cross-database join

### Requirement: Names and meaning are preserved
The retyped tables SHALL keep the existing schema, table names and column names, and `ts` SHALL keep its epoch-seconds meaning.

#### Scenario: Existing reader after the swap
- **WHEN** an existing query selects columns from `raw.polymarket_price` or `raw.kalshi_candle` by name
- **THEN** it returns the same values with no change to the query other than removing now-unneeded casts

### Requirement: Missing is not zero
An empty source value SHALL be stored as NULL and SHALL NOT be stored as zero.

#### Scenario: Kalshi candle with no trade
- **WHEN** a candle has an empty `price_close_dollars`
- **THEN** the stored value is NULL

### Requirement: Values that cannot be typed are kept, not lost
A source value that fails its type check SHALL be written to a reject table as text with its source key, and SHALL NOT abort the load.

#### Scenario: A malformed price
- **WHEN** a row has a non-numeric price
- **THEN** the row is written to the reject table and the rest of the batch loads

### Requirement: Loads are idempotent and append-only
The market loaders SHALL be re-runnable, with a unique key on (`clob_token_id`, `ts`) for Polymarket prices, and a second run over the same input SHALL change nothing.

#### Scenario: Run twice
- **WHEN** a loader processes the same input twice
- **THEN** the table row count and contents are identical after the second run

### Requirement: Swap is verified and reversible
The retyped table SHALL replace the old table only after row counts and price sums match per token per month, and the old table SHALL be kept for 7 days.

#### Scenario: Verification fails
- **WHEN** the per-token per-month counts or price sums differ
- **THEN** the swap is not performed and the old table remains in use

### Requirement: Size target
The two market tables SHALL total 10 GB or less after compression.

#### Scenario: Post-swap size check
- **WHEN** the swap is complete and all chunks are compressed
- **THEN** the combined size of the two tables is at most 10 GB
