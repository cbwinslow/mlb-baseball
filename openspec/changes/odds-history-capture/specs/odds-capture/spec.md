## Purpose

Defines how prediction-market odds (Kalshi, Polymarket) are captured, retained and backfilled so price history over time is available for point-in-time research.

## ADDED Requirements

### Requirement: Odds observations are captured at a fine, independent cadence
The system SHALL append one timestamped price observation per open MLB market outcome on a schedule independent of the nightly pipeline, at an interval of at most 15 minutes while MLB games are scheduled that day. An observation SHALL carry its own capture time and SHALL NOT be replaced or deleted by a later run.

#### Scenario: Two captures an interval apart both survive
- **WHEN** the capture job runs twice with different prices for the same market
- **THEN** both rows exist, distinguished by capture time

#### Scenario: Capture does not depend on the nightly run
- **WHEN** the nightly pipeline is not running or has failed
- **THEN** odds capture still runs on its own schedule

#### Scenario: No open markets
- **WHEN** a capture finds no open markets
- **THEN** it completes successfully with zero rows and the snapshot tables still exist

### Requirement: Capture is light and overlap-safe
A capture run SHALL read only open-market prices (not the full historical catalog) and SHALL NOT start while a previous capture is still running.

#### Scenario: Overlapping run is skipped
- **WHEN** a capture is still running when the next tick fires
- **THEN** the new tick exits without fetching and logs that it skipped

### Requirement: Catalog history is retained
The Kalshi and Polymarket catalog tables (series, event, market, outcome) SHALL NOT delete rows that stop appearing in a source pull. Each row SHALL record when it was last seen in a pull.

#### Scenario: A market vanishes from the source
- **WHEN** a market present in the previous run is absent from the next pull
- **THEN** its row remains and its last-seen time is not advanced

#### Scenario: A market changes
- **WHEN** a pull returns different values for an existing market
- **THEN** the row holds the newest values and last-seen advances

### Requirement: Historical price backfill is explicit, resumable and idempotent
Polymarket price history and Kalshi candlesticks SHALL be backfilled only by an explicit command, never as a side effect of routine updates. Re-running after an interruption SHALL replace only the markets it reprocesses and SHALL NOT duplicate rows. Empty or no-trade source observations SHALL be stored as missing values, not zero.

#### Scenario: Interrupted backfill resumes
- **WHEN** a backfill stops partway and is run again
- **THEN** already-landed markets are not duplicated and remaining markets are loaded

#### Scenario: No-trade candle
- **WHEN** a candle has no trades
- **THEN** its price fields are stored as missing

### Requirement: Observations are source-faithful and point-in-time
Stored odds SHALL keep the source's bid, ask and last-price fields separate and SHALL keep the source's observation time. No stored field SHALL be derived from settlement or outcome state.

#### Scenario: Pregame selection
- **WHEN** a researcher selects the latest observation at or before a cutoff time
- **THEN** no observation captured after the cutoff is returned, and a missing result is returned as missing

### Requirement: Capture health is checked
`mlb doctor` SHALL report a failure when, on a day with scheduled MLB games, the gap between consecutive snapshots during game hours exceeds twice the capture interval, and SHALL NOT report the backfill tables as defects before the backfill has been run.

#### Scenario: Missed captures
- **WHEN** no snapshot lands for more than twice the interval during game hours
- **THEN** doctor fails with the gap length

#### Scenario: Backfill not yet run
- **WHEN** the backfill has never been run
- **THEN** doctor reports it as not run, not as a missing-table defect
