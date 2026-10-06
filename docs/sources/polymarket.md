# Polymarket

Same layout and ownership rules as [`mlb_api.md`](mlb_api.md). Facts below are from the connector sidecar, which records live checks dated 2026-10-05; this page did not re-probe the API.

| Question | Owner |
|---|---|
| Tables, rows, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `polymarket`) |
| Offered vs. held vs. missing | `mlb coverage --source polymarket` (price history is compared with token windows and the ledger) |
| Connector contract, windows, ledger, PIT rules | [`polymarket.py.dox.md`](../../mlb_baseball/connectors/polymarket.py.dox.md) |
| Rights | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "Polymarket / Kalshi") |

## Access

- **Catalog:** public Gamma API, `gamma-api.polymarket.com`. Daily MLB games come from series id `3`; everything else MLB comes from `tag_slug=mlb`. The two overlap and are de-duplicated by event id.
- **Price history:** public CLOB, `clob.polymarket.com`, `POST /batch-prices-history`, 20 tokens per request, fixed 14-day windows, newest first. Verified live 2026-10-05: `interval=max` returns an empty list for a settled market and a 30-day window is rejected; both are avoided on purpose.
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

- Daily game catalog reaches back to 2021, deeper than Kalshi.
- Scale on 2026-10-05: about 217,000 markets and 435,000 tokens, which is the size of the price-history job.
- Point-in-time: a settled or current price is not a pregame probability; use a timestamped observation before the cutoff, otherwise NULL.

## Known gaps and open questions

- Counts are not recorded here because the backfill is moving; use `mlb coverage --source polymarket`.
