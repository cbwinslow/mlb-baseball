# Operational Milestone: prediction-market collector fixes

**Date:** 2026-11-27
**Target database:** PostgreSQL `mlb` (production runs are logged below as they happen)
**Change:** `openspec/changes/odds-bulk-history` section 7; ADR-305

## Scope
Gaps measured 2026-11-27 (read-only): cut-off candle histories, candle rows without volume,
undiscovered series and events, no price history outside daily games, no trades.

## Actions
Code: both connectors, `history.py`, coverage and repair lists, `--mode trades`, MLB slug filter.

Also: the 5-minute `mlb_api` update now raises one alert after three failures in a row, using
`scripts/mlb_alert.sh` (taken unchanged from branch `stabilize-market-clean`, because the
configured alert command did not exist on `main`).

Follow-up: runs refused because conform/predict hold the database (nightly, about 50 minutes)
would have raised that alert every night. They are now counted apart and alert only after 24
in a row (two hours); they neither count as failures nor clear them.

Review (PR 407) found two defects, fixed before merge: a shorter reply could erase stored
trades, bars or points inside the returned range; and coverage counted an early fetch as held
until the 14-day window ended even when the market had closed sooner; and a history was
dated when it was saved, so a market closing mid-request (or after a long run started) could
be marked complete without its last minutes. It is now dated when the source was asked.

## Overlap with unmerged work
Branch `stabilize-market-clean` rewrites the same loaders as append-only (duplicates ignored).
Before it merges it must keep this change's behaviour: re-fetched candle rows have to update
rows saved without volume.

## Verification
Trial on real API data in a scratch database: Kalshi trade totals equalled the market's listed
volume for two markets; Polymarket taker totals equalled listed volume for two of three markets
(the third was 97%, cause not established).

## Production runs
Candle re-download on 2026-11-27 was far too slow: about one market every 6 seconds across
8 workers, while the Polymarket price backfill kept the disk saturated.

## Run monitor stalled every worker
All workers record timing through one connection under one lock, and each insert waited for
the disk. Measured under that load: a waiting commit took a median 1.2 s (mean 1.8 s, max
12 s); a non-waiting one a median 0.2 ms (mean 0.24 s). The monitor connection now sets
`synchronous_commit = off`: a crash can lose the last timing rows, never data or ledger rows.
The candle backfill also committed nothing after planning, so its connection stayed
`idle in transaction` for the whole run and blocked vacuum; it now commits there, as the trade
backfill already did.
