## Why

Prediction-market odds are only useful for research if we hold their history over time. Today `raw.kalshi_snapshot` and `raw.polymarket_snapshot` get one observation per day (inside the 06:00 `mlb nightly` run, since 2026-08-02), which is too coarse to plot how a price moves toward first pitch. The Kalshi and Polymarket catalog tables are replaced whole on every run (Kalshi lost 14,594 market rows on 2026-10-03), and the one-time historical backfills (`raw.polymarket_price`, `raw.kalshi_candle`) have never been run, so two `mlb doctor` checks fail and years of available history are not stored.

## What Changes

- Add a light, separate odds-capture job (own cron entry, own lock, minutes not hours) that appends price observations for open markets only. It does not re-pull the full catalog.
- Stop replacing the Kalshi and Polymarket catalog tables whole; rows that disappear from a source pull are kept, and each row records when it was last seen.
- Run the existing one-time historical backfills (Polymarket CLOB price history back to 2021; Kalshi candles for `KXMLBGAME` from 2026) once, with owner approval, and keep them resumable.
- Correct the two `mlb doctor` checks that report the backfill tables as defects before the backfill has been run, and add checks for snapshot cadence (gaps while games are live).
- Write the failing test first for each change (TDD).

## Capabilities

### New Capabilities
- `odds-capture`: how Kalshi and Polymarket odds history is captured, retained and backfilled in `raw`.

### Modified Capabilities

(none: no existing spec covers market ingestion; `source-refresh` is about file sources)

## Impact

- Code: `mlb_baseball/connectors/kalshi.py`, `polymarket.py` (+ their `.dox.md`), `mlb_baseball/cli.py` (new capture entry), a new `scripts/mlb_odds_capture.sh`, doctor checks.
- Data: `raw.kalshi_*` and `raw.polymarket_*` catalog semantics change from replace to keep-and-stamp (migration if a column is added); two new tables populated by backfill. Production writes are owner-approved and logged in `pipeline-recovery/results.md`.
- Downstream: `conform.py` market resolution reads these tables; it must keep working on rows that are no longer replaced.
- Rights: public unauthenticated reads only; no change to `docs/SOURCE_RIGHTS.md` profile.
