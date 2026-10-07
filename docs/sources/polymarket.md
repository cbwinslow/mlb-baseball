# Polymarket

Same layout and ownership rules as [`mlb_api.md`](mlb_api.md). Facts below were re-probed live on 2026-10-07 (read-only) and compared with what the database holds; where the connector sidecar differs, this page records the newer fact.

| Question | Owner |
|---|---|
| Tables, rows, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `polymarket`) |
| Offered vs. held vs. missing | `mlb coverage --source polymarket` (price history is compared with token windows and the ledger) |
| Connector contract, windows, ledger, PIT rules | [`polymarket.py.dox.md`](../../mlb_baseball/connectors/polymarket.py.dox.md) |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "Polymarket / Kalshi") |

## Access

- **Catalog:** public Gamma API, `gamma-api.polymarket.com`. Daily MLB games come from series id `3`; everything else MLB comes from `tag_slug=mlb`. The two overlap and are de-duplicated by event id.
- **Price history:** public CLOB, `clob.polymarket.com`, `POST /batch-prices-history`, 20 tokens per request, fixed 14-day windows, newest first. Verified live 2026-10-05: `interval=max` returns an empty list for a settled market; re-probed 2026-10-07: a 30-day window is still rejected (`interval is too long`), while 14-day and 15-day windows and a 21-token request were accepted (the connector keeps 14 days and 20 tokens). For an open market `interval=max` returned a coarse series, not an empty one.
- **Pagination:** deep history needs `/events/keyset`. Plain offset paging stops at a shallow ceiling and silently truncates history.
- **Rate limit:** documented ceiling of 1,000 requests per 10 seconds with no key. Measured: throughput stops rising past about 8 to 16 concurrent requests and 32 concurrent heavy requests timed out. The backfill uses 4 processes of 4 threads.
- **Auth:** none. Trading and account actions are not part of the connector.
- **Saved before load:** no; the ledger (`meta.ingestion_item`, dataset `price_history`, key `<token>:<window start>`) records `loaded`, `unavailable` (empty window, or a market with no start date) or `failed`.

## Rights

Public API access is not a redistribution, content or commercial-display license. `local_research` only (record: `SOURCE_RIGHTS.md`). No first-hand reading of Polymarket's terms is in this repo yet.

## Products

| Table | Content | Rule |
|---|---|---|
| `raw.polymarket_event`, `_market` | catalog | upsert by key; vanished rows are kept (ADR-294) |
| `raw.polymarket_outcome` | one row per outcome of a market, with its CLOB token | exploded from the market's parallel JSON arrays |
| `raw.polymarket_snapshot` | current prices of open markets | append-only, key `(market_id, outcome, captured_at)`; also every 15 minutes via `mlb odds-capture` |
| `raw.polymarket_price` | historical price per token and window | one transaction per window |

## Coverage boundaries

- Daily game catalog: the connector notes say 2021; the oldest event held under the MLB series or tag starts 2020-10-20 and the oldest ` vs. ` game title starts 2022-04-08 (database, 2026-10-07). Deeper than Kalshi (2025-04-16).
- Scale on 2026-10-05: about 217,000 markets and 435,000 tokens, which is the size of the price-history job.
- Point-in-time: a settled or current price is not a pregame probability; use a timestamped observation before the cutoff, otherwise NULL.

## Known gaps and open questions

- Counts are not recorded here because they move; use `mlb coverage --source polymarket`.
- On 2026-10-07: 11,593 events, 227,142 markets, 454,284 outcomes (454,274 distinct tokens). 5,750 items were missing price history (new markets since the backfill); the backfill is not scheduled and the owner deferred it.
- Use: only game-winner markets reach `core.market` (32,149 of 43,972 linked to a game). Player props, totals, awards, futures and all price history are kept for stage 3 research and read by nothing yet. Owner decision 2026-10-07: keep all of it.
- Not every market has a sport type (6,344 of 227,142 have none); they are mostly awards, futures and old game markets, and were not individually reviewed. One World Baseball Classic event is held (out of 11,593).
- Not checked: row-level price and result quality, and the documented rate limit (not re-measured).
