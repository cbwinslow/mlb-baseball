# Operational Milestone: prediction-market collector fixes

**Date:** 2026-11-27
**Target database:** PostgreSQL `mlb` (production runs are logged below as they happen)
**Change:** `openspec/changes/odds-bulk-history` section 7; ADR-304

## Scope
Gaps measured 2026-11-27 (read-only): cut-off candle histories, candle rows without volume,
undiscovered series and events, no price history outside daily games, no trades.

## Actions
Code: both connectors, `history.py`, coverage and repair lists, `--mode trades`, MLB slug filter.

## Verification
Trial on real API data in a scratch database: Kalshi trade totals equalled the market's listed
volume for two markets; Polymarket taker totals equalled listed volume for two of three markets
(the third was 97%, cause not established).

## Production runs
Not yet run.
