# Kalshi

Same layout and ownership rules as [`mlb_api.md`](mlb_api.md). Facts below are from the connector sidecar, which records live checks dated 2026-10-05; this page did not re-probe the API.

| Question | Owner |
|---|---|
| Tables, rows, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `kalshi`) |
| Offered vs. held vs. missing | `mlb coverage --source kalshi` (candles are compared with the market catalog and the ledger) |
| Connector contract, pacing, ledger, PIT rules | [`kalshi.py.dox.md`](../../mlb_baseball/connectors/kalshi.py.dox.md) |
| Backfill progress and speed | `mlb runs`, `meta.run_health` |
| Plan for trades history | `openspec/changes/odds-bulk-history` task 4.3 |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "Polymarket / Kalshi") |

## Access

- **API:** `api.elections.kalshi.com/trade-api/v2`, public market-data reads. Trading and portfolio calls are not part of the connector.
- **Signing:** optional. With `KALSHI_API_KEY` and `KALSHI_PRIVATE_KEY_PATH` (a free key) requests are RSA-PSS signed and get the Basic tier: 200 read tokens per second at 10 per request, so about 20 requests per second; the connector paces at 16 per second. Unsigned requests returned HTTP 429 from about 5 requests per second (measured 2026-10-05), so unsigned pacing is 5 per second. Overrides: `MLB_KALSHI_WORKERS`, `MLB_KALSHI_MAX_RPS`; raise only with a new measurement.
- **History split:** `GET /historical/cutoff` was 2026-08-06 on 2026-10-05. Markets and candles settled before it exist only on the `/historical` endpoints; the live `/markets` listing no longer returns them. The connector pages both and merges (live wins on a ticker).
- **Saved before load:** no; the ledger (`meta.ingestion_item`, dataset `candles`, one item per market) records `loaded`, `unavailable` or `failed`.

## Rights

Public read access is not a redistribution or display license. `local_research` only (record: `SOURCE_RIGHTS.md`). No first-hand reading of Kalshi's terms is in this repo yet; add the wording to `SOURCE_RIGHTS.md` before any public use.

## Products

| Table | Content | Rule |
|---|---|---|
| `raw.kalshi_series`, `_event`, `_market` | catalog: series, events, yes/no contracts | upsert by key; rows the source stops returning are kept (ADR-294) |
| `raw.kalshi_snapshot` | price observations of open markets | append-only, key `(ticker, captured_at)`; also written every 15 minutes by `mlb odds-capture` |
| `raw.kalshi_candle` | 1-minute candles | per market, windows of at most 4,000 minutes; empty trades stay NULL while bid/ask are kept |

Scope is every true MLB market: game lines, spreads and totals, season totals, player props, awards, futures, draft, All-Star and Home Run Derby. Non-MLB baseball series (KBO, NPB, MiLB, NCAA, WBC and others) are excluded by an evidence-based list, not by name guessing.

## Coverage boundaries

- The daily game-moneyline series `KXMLBGAME` begins in 2026; do not invent earlier depth.
- Not covered: per-market trades (`/historical/trades`, `/markets/trades`).
- Point-in-time: a settled or current price is not a pregame probability. Use a timestamped snapshot or candle before the cutoff; with none, keep NULL.

## Known gaps and open questions

- The backfill of candles was still running on 2026-10-06 (about two thirds done at the time of writing); counts on this page are deliberately not recorded because they are moving. Use `mlb coverage --source kalshi`.
