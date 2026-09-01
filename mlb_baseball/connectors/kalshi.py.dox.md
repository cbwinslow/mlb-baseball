# kalshi.py DOX

## Purpose

Own read-only MLB prediction-market acquisition from Kalshi's public REST API,
including market catalog data, forward price snapshots, and the explicitly scoped
historical candlestick backfill.

## Ownership

Source implementation: `kalshi.py`.

Owned raw relations:

- `raw.kalshi_series`
- `raw.kalshi_event`
- `raw.kalshi_market`
- `raw.kalshi_snapshot` — append-only point-in-time observations
- `raw.kalshi_candle` — historical candlestick backfill

Registry source name: `kalshi`.

Focused integration test: `tests/integration/test_kalshi_load.py`.

## Source and Scope Contracts

- Read-only market endpoints currently work without authentication. Do not add
  trading/private-key signing requirements to read paths unless Kalshi changes the
  API contract.
- Baseball-tagged series are not synonymous with MLB. The explicit exclusion set
  removes KBO, NPB, MiLB, NCAA, WBC, charity/deprecated and other non-MLB series
  after title-level verification.
- A Kalshi market is already the atomic yes/no contract; there is no separate
  outcome table analogous to Polymarket.
- Historical sports-market depth is shallow. `KXMLBGAME` daily MLB game markets
  begin in 2026; do not imply years of sportsbook-style history that does not
  exist.

## Runtime Contracts

- `bootstrap()` and `update()` perform the same paginated full catalog refresh
  because the API has no reliable per-season partial-reload contract.
- Series/events/markets are replacement-style current catalog relations.
- Every run appends a `captured_at` snapshot only for active markets into
  `raw.kalshi_snapshot`; historical observations must never be overwritten.
- Snapshot identity is `(ticker, captured_at)`.
- Per-series event/market failures are isolated so one bad series does not erase
  usable data from the rest of the run.
- Pagination sizes differ intentionally: the market endpoint tolerates a much
  larger page than the event endpoint.

## Historical Backfill Contract

`backfill_history()` is separate from normal bootstrap/update.

- It is scoped to `KXMLBGAME` daily MLB game moneylines.
- It uses the public candlesticks endpoint at one-minute granularity.
- Requests are chunked because the endpoint enforces a real maximum candle count.
- A small sleep between markets is deliberate rate-limit etiquette.
- Do not broaden backfill scope to every Kalshi sports/prop/futures market without
  a measured storage/API/runtime and product-value review.

## Time Semantics

`captured_at`/candlestick time is critical research evidence. Market prices must
not be joined to predictions using final/current values when evaluating a past
forecast cutoff.

Future canonical market architecture should distinguish contract identity from
observation time series; this raw connector must preserve enough source identity
and timing to support that split.

## Rights and Safety

Kalshi data is not automatically `public_safe`. Follow `docs/SOURCE_RIGHTS.md`
and source-profile enforcement. This connector is read-only; do not add order
placement/trading side effects here.

## Verification

Run:

```bash
uv run pytest tests/integration/test_kalshi_load.py -q
uv run ruff check mlb_baseball/connectors/kalshi.py tests/integration/test_kalshi_load.py
```

Verify pagination, exclusion filtering, snapshot append semantics, idempotent
catalog reloads, and candle chunking when those areas change.
