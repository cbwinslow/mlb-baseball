## Purpose

Defines how Polymarket and Kalshi history is fetched, tracked and stored so it is complete back to each site's start, fast within published limits, and resumable.

## ADDED Requirements

### Requirement: Polymarket history is fetched by explicit time window in batches
The Polymarket backfill SHALL request price history by explicit start/end window (never `interval=max` for a settled market), in windows no longer than the documented maximum, using the batch endpoint for up to its documented token limit per request, and SHALL stay under the documented request rate.

#### Scenario: A settled market has history
- **WHEN** a market closed months ago is backfilled
- **THEN** its price points are stored, where `interval=max` would have returned none

#### Scenario: A market spans longer than one window
- **WHEN** a market's life is longer than the maximum window
- **THEN** it is fetched in consecutive windows with no gap and no overlap

### Requirement: Newest data first, resumable per item
Backfills SHALL process newest markets first and SHALL record one ledger item per market and window (`loaded`, `unavailable` for a window with no points, or `failed`). A rerun SHALL skip items already `loaded` or `empty` and SHALL retry `failed` ones, so an interrupted run loses at most the in-flight batch.

#### Scenario: Interrupted run
- **WHEN** a backfill is stopped partway and started again
- **THEN** settled finished items are not fetched again and no rows are duplicated

### Requirement: Kalshi history crosses the live/historical cutoff
The Kalshi connector SHALL read `GET /historical/cutoff`, fetch markets, candlesticks and trades from the live endpoints for data after the cutoff and from the historical endpoints for data before it, and SHALL deduplicate by market ticker and trade id across the boundary.

#### Scenario: A market settled before the cutoff
- **WHEN** a baseball market settled before the cutoff is requested
- **THEN** it is found through the historical endpoints and stored, and appears once

### Requirement: Every baseball series is covered
The Kalshi connector SHALL discover baseball series from the series list (every `KXMLB*` and other baseball series) rather than a hard-coded single series, and record the discovery date.

#### Scenario: New series appears
- **WHEN** Kalshi lists a new MLB series
- **THEN** the next run ingests it without a code change

### Requirement: Bulk datasets stay separate and rights-checked
A third-party bulk dataset SHALL be loaded only after its licence and coverage are recorded in `docs/SOURCE_RIGHTS.md`, SHALL land in its own `raw` tables with the dataset name, version and download checksum, and SHALL never be written into the official-endpoint tables.

#### Scenario: Overlap check
- **WHEN** a bulk dataset and the official endpoints cover the same market
- **THEN** a comparison reports matching and differing points; differences are recorded, not silently resolved

### Requirement: Progress is visible
Long backfills SHALL log progress (items done, total, items/s, estimated finish) at least every minute and write it to the run record.

#### Scenario: A run takes hours
- **WHEN** an operator asks how far a running backfill is
- **THEN** the run record answers without counting rows by hand
