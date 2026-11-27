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

## Overlap with unmerged work
Branch `stabilize-market-clean` rewrites the same loaders as append-only (duplicates ignored).
Before it merges it must keep this change's behaviour: re-fetched candle rows have to update
rows saved without volume.

## Verification
Trial on real API data in a scratch database: Kalshi trade totals equalled the market's listed
volume for two markets; Polymarket taker totals equalled listed volume for two of three markets
(the third was 97%, cause not established).

## Production runs
Not yet run.
