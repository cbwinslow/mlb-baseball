# `mlb_api.py` DOX

## Purpose

Own ingestion from MLB's official Stats API (`statsapi.mlb.com`) through the maintained `statsapi` Python package plus project-owned wrappers/adapters. This is a broad multi-product connector and one of the highest-risk modules for accidental scope creep, so its durable contracts must remain explicit while the implementation is decomposed incrementally.

## Ownership

Implementation: `mlb_api.py`.

Major raw products currently owned include:

- `raw.mlb_schedule`
- `raw.mlb_standing`
- `raw.mlb_roster`
- `raw.mlb_transaction`
- `raw.mlb_playbyplay`
- `raw.mlb_live_game`
- `raw.mlb_venue`
- `raw.mlb_team_history`
- `raw.mlb_person`
- `raw.mlb_draft`
- `raw.mlb_boxscore_batting`
- `raw.mlb_boxscore_pitching`
- `raw.mlb_boxscore_fielding`
- `raw.mlb_umpire`
- `raw.mlb_win_prob`
- `raw.mlb_linescore`
- `raw.mlb_game_context`
- `raw.mlb_probable`
- official-scorer/datacaster products where implemented.

Public/runtime entry points include historical bootstrap, current update, live capture, health checks, and internal endpoint-specific loaders.

## Source Contract

- Authoritative source: MLB Stats API.
- Transport/client: currently `statsapi` (`ToddRob99/MLB-StatsAPI`) with project-owned timeout/retry wrappers.
- Do not expose the third-party library's object model as the project's canonical schema; map responses into project-owned raw relations.
- Coverage varies by product. Never infer a single global "MLB API starts in YEAR" rule.

Verified product-specific coverage/strategy from current source comments includes:

- schedule: 1901+;
- standings: 1969+;
- rosters: 1901+;
- transactions: approximately 2000+;
- draft: 1965+;
- win-probability / line-score / game-context family: verified from 1950+;
- play-by-play / game box score / umpire detail: intentionally limited to the post-Retrosheet-current gap (`FIRST_PLAYBYPLAY_YEAR`, currently 2026) to avoid expensive redundant historical fetching;
- probable pitchers: forward-looking append-only/change-history snapshots over a short schedule horizon;
- live game state: append-only snapshots while games are live.

If any boundary changes, update this sidecar and the relevant ADR/source docs based on direct endpoint evidence.

## Architectural Role

This connector intentionally overlaps some historical Retrosheet facts because independently sourced duplication can be valuable for cross-validation. It must not duplicate high-cost endpoint families without an explicit benefit.

Examples of deliberate exclusions/evaluations in current source:

- pitch-level physics should come from richer Statcast ingestion rather than duplicating MLB game-feed pitch fields;
- inaccessible/internal or low-value/cosmetic endpoint families are not ingested merely because they exist;
- third-party convenience helpers are used selectively when they are mature, but wrapped where they lack critical timeout/error controls.

Do not expand endpoint coverage mechanically. Every new family needs a data/research use case, source/rights check, coverage probe, request-cost estimate, raw grain/key design, health coverage, and test plan.

## Runtime Contracts

### Timeouts and retries

- Every Stats API call must have a finite request timeout.
- `_get()` currently wraps `statsapi.get()` with `REQUEST_TIMEOUT_SECONDS` so a stalled socket raises and can participate in retry behavior.
- Retry/backoff uses shared project networking logic; analytics hot paths may use tighter timeouts/retry-after caps because independent per-game workers must not freeze an entire batch.
- Do not remove finite timeouts because "requests usually return quickly"; a real historical bootstrap previously hung/faulted on upstream server behavior.

### Schedule adapter

- `_timed_schedule()` preserves `statsapi.schedule()`'s mature parser while injecting bounded request behavior.
- It uses a process-local lock while temporarily substituting the library's `get` function. Changes here are concurrency-sensitive.
- Historical schedule responses can contain team IDs without embedded names. Current code fills missing display names from the season-specific teams catalog only when absent so otherwise valid games are not dropped.
- Do not generalize that targeted source repair into broad mutation of API payloads.

### Historical bootstrap / transaction boundaries

- Cheap season-scoped products commit by natural season so a late failure does not discard decades already loaded.
- Expensive per-game detail commits at a finer per-game boundary.
- Individual season/game/step failures are caught/logged/skipped after rollback where appropriate rather than destroying all remaining work.
- Preserve resumability and clear run tracking when refactoring orchestration.

### Update behavior

- Current-season schedule/standings/roster/transactions/draft are refreshed with scoped-replace/idempotent behavior.
- Started/finished current games refresh game-scoped details so in-progress facts can grow safely across polls.
- Live game state is append-only snapshots.
- Venue/team-history/person reference data is intentionally not refreshed every short-interval update; bootstrap owns the heavier refresh cadence.
- Real-time freshness depends on actually scheduling `update()` repeatedly; connector code alone is not a daemon.

### Append/history semantics

- `raw.mlb_live_game`: append-only observation history.
- `raw.mlb_probable`: append a new `(game_pk, side)` snapshot only when the observed probable assignment changes; preserve scratch/announcement history rather than one-row current state.
- Do not replace historical observation tables with mutable latest-state rows if downstream point-in-time research depends on their history.

## Data Contracts

- Scope/key semantics vary by product; preserve each loader's explicit season/game/entity scope.
- `game_pk` is an important MLB-source game identifier but must not be assumed to equal another source's canonical game key without conformance/reconciliation.
- probable-pitcher IDs are valuable because they can resolve to canonical players before a game is played; preserve person IDs, not only display names.
- Raw source payload-derived fields remain source-faithful; canonical normalization belongs downstream.
- Missing endpoint availability before a verified coverage boundary is missing measurement, not zero.

## Dependencies

- `statsapi`
- `requests`
- pandas / psycopg
- `mlb_baseball.manifest`
- `mlb_baseball.load` (`load_dataframe`, `append_dataframe`, scoped-replace helpers, season loaded checks)
- `mlb_baseball.ingest` run/item tracking
- `mlb_baseball.net.call_with_retry`
- shared DB/health helpers

## Downstream Consumers

- `conform.py` and canonical identity/game/player/team reconciliation.
- research grains requiring current schedule/game/roster/transaction/probable/live context.
- current/future forecasting features that must know what information was available before game time.
- cross-source validation against Retrosheet/Statcast/Lahman families.

## Known Decisions / Risks

- The module is very large (~130 KB) and should be decomposed behind a stable connector facade rather than rewritten.
- Endpoint-specific coverage was established by direct probing in several places; preserve those findings or re-verify before changing boundaries.
- `transactions` currently requires `force=True` because the third-party client's required-parameter validation mishandles valid alternative parameter sets; do not remove without confirming upstream behavior changed.
- Concurrency exists in selected analytics paths. Treat shared-library monkeypatching, locks, timeouts, and worker behavior as one contract when editing them.
- Official-client/library parity should be evaluated before adding more bespoke endpoint glue, but replacement requires a measured parity spike rather than preference.

## Work Guidance

When changing this module:

1. Identify the exact product/endpoint family being touched.
2. Verify its coverage, grain, scope/update strategy, and rights profile.
3. Inspect downstream conformance/research users.
4. Preserve stable top-level connector behavior while extracting cohesive helpers/modules.
5. Do not combine unrelated endpoint refactors into one change simply because they share this file.
6. Update this sidecar when ownership/coverage/runtime semantics change.

Recommended decomposition direction (not a rewrite mandate): schedule/reference, people/teams, game-detail, analytics, live/probables, and orchestration/shared client layers behind the existing connector facade.

## Verification

Use targeted tests for the product changed. Expected categories include:

- parser/normalization unit tests;
- real-PostgreSQL connector load/idempotency tests with mocked/captured API responses;
- timeout/retry tests for request wrappers;
- schedule historical edge cases;
- scoped-replace vs append-history behavior;
- health/coverage checks;
- conformance tests for downstream identifiers/facts;
- CLI dispatch if user-facing commands changed.

For a new endpoint family, perform a bounded manual parity/coverage probe against the real API before codifying historical claims, then capture deterministic fixtures for CI.

## Child DOX Index

No child files today because this is still a monolithic module. As it is decomposed into a durable `mlb_api/` subpackage, create a child `AGENTS.md` and move endpoint-family context down with the code rather than leaving this sidecar as an ever-growing encyclopedia.
