# polymarket.py DOX

## Purpose

Own read-only MLB prediction-market acquisition from Polymarket's public Gamma
API and historical per-token prices from the public CLOB API.

## Ownership

Source implementation: `polymarket.py`.

Owned raw relations:

- `raw.polymarket_event`
- `raw.polymarket_market`
- `raw.polymarket_outcome`
- `raw.polymarket_snapshot` — append-only forward observations
- `raw.polymarket_price` — historical CLOB token-price backfill

Registry source name: `polymarket`.

Focused integration test: `tests/integration/test_polymarket_load.py`.
Related market-time repair/evaluation tests may also apply.

## Source and Scope Contracts

MLB discovery intentionally combines two overlapping surfaces:

- daily MLB series (`series_id=3`);
- broader MLB-tagged events (`tag_slug=mlb`) including futures, postseason,
  draft, All-Star, and related props.

Events must be de-duplicated by source event ID before loading because the two
queries overlap heavily.

Each market contains JSON-encoded parallel arrays for outcomes, prices, and CLOB
token IDs. These are exploded into one source-faithful outcome row per label/token;
do not leave them as opaque arrays in the canonical raw shape.

## Pagination Contract

Use `/events/keyset` cursor pagination. Plain offset pagination has a real depth
limit and previously truncated historical results. Do not revert to offset-based
pagination without proving the upstream behavior changed.

## Runtime Contracts

- `bootstrap()` and `update()` full-reload event/market/outcome catalog data.
- Each run appends current prices for still-open outcomes into
  `raw.polymarket_snapshot` at a new `captured_at` timestamp.
- Snapshot identity is `(market_id, outcome, captured_at)` and historical
  observations must never be overwritten.
- Empty current-open-market sets are still valid and should not make table
  existence depend on market timing.
- Public Gamma/CLOB reads currently require no authentication; keep this connector
  read-only unless a separate design explicitly introduces authenticated actions.

## Historical Price Backfill

`backfill_history()` is an explicitly separate long-running operation.

- It calls CLOB `/prices-history` by `clob_token_id` with `interval=max`.
- Current scope is daily-game events only (`e.sport IS NOT NULL`), including the
  tokens under those events; it deliberately excludes unrelated season-futures/
  postseason/draft-only event groups from this backfill.
- Empty history is a valid source response, not automatically an error.
- Loads are scoped by token so reruns replace that token's history rather than
  duplicating it.
- Commits are bounded so an interruption loses limited work and can resume safely.

## Time and Evaluation Semantics

Market price is time-varying evidence. Preserve `captured_at`/history timestamps
and source contract identity so future evaluation can compare a forecast only to a
price observable at or before its cutoff. Current/final price is never a valid
stand-in for an earlier market observation.

## Rights and Safety

Follow `docs/SOURCE_RIGHTS.md` and source-profile enforcement. Public API access
does not automatically make Polymarket-derived relations redistributable through
`public_safe`.

## Verification

Run:

```bash
uv run pytest tests/integration/test_polymarket_load.py -q
uv run ruff check mlb_baseball/connectors/polymarket.py tests/integration/test_polymarket_load.py
```

When changing timing/backfill behavior, also run the relevant market-time repair
and downstream market-model regression tests.
