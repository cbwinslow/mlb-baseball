# Plan 05 — Serving marts, Astro product, and launch

## Objective

Turn verified research and forecasts into an original, fast, transparent public
product that is useful to fans and impressive to technical reviewers.

**Status:** Queued (depends on Plan 04).

## Work packages

### 05A — Product benchmark and contracts

Maintain a current, source-cited inventory of OddsTrader's useful surface: daily
grid, projected results, moneyline/run-line/totals, EV, cover probability, rating,
best line, movement, props, and content. Translate capabilities—not design—into
our own requirements. Define lawful data, freshness, latency, accessibility,
responsible-use, and zero-cost degradation contracts.

### 05B — Read-only serving layer

Build SQLMesh `serve.daily_game`, `serve.game_detail`, `serve.model_scorecard`,
research, player/team/park, forecast-history, and content-fact marts. Make them
narrow, cached, documented, and accessible only through the serving role. Publish
generated/data cutoff and input-state fields everywhere.

Serving objects must carry game-instance identity and source/rights lineage;
they may expose only `public_safe` inputs until a separately documented license
permits more. PostgreSQL remains the first serving store; no public database or
paid hosting is required for the static Astro MVP.

### 05C — Astro MVP

Create an original visual system and ship daily forecast board, game forecast
story, model scorecards, methodology, data sources/rights, research, engineering,
and responsible-use pages. Use static output for evergreen material and minimal
server/island code for changing data and charts. Do not copy competitor assets,
layout, or prose.

### 05D — Betting and scenario tools

Separate forecast, fair price, winner lean, playable threshold, market edge, and
conditional pick. Until a permitted odds feed exists, use Polymarket/Kalshi as
distinct comparisons and a client-side user-entered odds/EV calculator. Add
clearly hypothetical starter/lineup/weather scenarios only when backed by real
versioned model inputs.

### 05E — Content, observability, and launch

Generate prose only from bounded fact packets with stored lineage. Monitor source
freshness, prediction failures, missing inputs, stale pages, model drift,
calibration, latency, and errors. Add CI, backup/restore rehearsal, security and
accessibility checks, privacy/terms, responsible-gambling resources, attribution,
and a launch runbook. Ads/affiliates remain disabled adapters until separate
rights/compliance approval.

Add a daily-board truth contract: distinguish model probability, fair price,
market comparison, uncertainty, missing inputs, and stale data. Never present a
likely winner as positive expected value without a permitted price input and a
verified calculation.

### 05F — ClickHouse revisit

Load-test real serving/research traffic. If PostgreSQL serving marts miss recorded
SLOs after optimization, run the Plan 02 benchmark with current workloads and
consider a read-only ClickHouse analytical replica. Do not make launch depend on
speculative infrastructure.

## Acceptance gate

- A user can trace every displayed number to model/data/source provenance.
- The daily board and game page meet recorded performance/accessibility/freshness
  SLOs and fail honestly when inputs are unavailable.
- Odds calculations have verified fixtures and never equate likely winner with
  positive expected value without price.
- Calibration/history includes losses and cannot be selectively rewritten.
- A clean deployment works with ads, affiliates, paid feeds, and ClickHouse all
  disabled.
