# conform.py DOX

## Purpose

Own cross-source conformance from already-landed `raw` relations into canonical
`core` identities and facts. This module never fetches network data; it reconciles
source evidence that already exists.

This is a known gravity well. Preserve behavior and the public `conform.run()`
facade while decomposing by responsibility; do not rewrite it wholesale.

## Ownership

Source implementation: `conform.py`.

Major canonical outputs include:

- `core.player`
- `core.team`
- `core.game`
- `core.play`
- `core.pitch`
- `core.market`
- `core.player_war`
- `core.venue`
- `core.standing`
- team aliases / source-ID bridges and related conformed relationships.

Primary regression surface: `tests/integration/test_conform.py`.

## Prerequisite Contracts

Required baseline sources are checked before the run rather than assumed. Current
load-bearing prerequisites include Retrosheet team/game information and the
Chadwick register needed for canonical IDs.

Some richer sources are optional:

- Retrosheet event PBP;
- MLB API current PBP/analytics;
- Statcast pitch data;
- markets/other enrichments.

A fresh database may legitimately lack optional source tables. Builders should
skip an unavailable optional family explicitly rather than turning the entire
conformance run into a failure.

## Identity Doctrine

- Prefer stable source IDs and exact provider-native bridges over names.
- Preserve unresolved/ambiguous matches as `NULL` or absent rows instead of
  guessing.
- Fuzzy/alias logic is evidence for difficult external sources, not a license to
  overwrite canonical identity without support.
- `core.game.game_pk` is a bridge to MLB's numeric game ID; unmatched games remain
  null rather than receiving a fabricated key.
- Doubleheaders, postponed/suspended/resumed games, historical team changes, and
  cross-provider game IDs are load-bearing identity cases. Read
  `docs/GAME_INSTANCE_IDENTITY.md` before changing game reconciliation.
- Retrosheet source IDs remain first-class evidence even when an MLB ID is found.

## Rebuild and Transaction Contracts

The current core build is intentionally a full truncate/rebuild rather than a
chunked incremental merge. Cross-source identity can change when any upstream
source improves, and the current relation sizes make deterministic rebuilds
simpler/safer than partial state.

Preserve builder dependency ordering. Examples:

- team/player identities must exist before facts reference them;
- MLB team-ID backfill must precede standings resolution;
- game identity/game_pk must exist before game-keyed source facts/markets can be
  safely attached;
- aliases must be available before string-only market identities are resolved.

Do not parallelize dependent builder stages merely for speed.

## Market Point-in-Time Contract

`core.market.implied_probability` must represent a qualifying source market
snapshot strictly before the relevant game's real start time. Current/settled
market price can encode the game outcome and would be direct leakage.

When no pregame snapshot exists, use `NULL`; do not fall back to the final price.

Keep contract identity and observation time conceptually distinct. A future
`market_observation` relation may formalize this separation, but this module must
not lose historical snapshot timing in the meantime.

## Source Quirk Doctrine

Many branches/comments here document verified production anomalies, historical
source differences, or provider-specific representation. Treat those comments as
institutional knowledge until the underlying source behavior is re-verified.

Examples include:

- historical Retrosheet casing/sparsity;
- team rebrands/relocations and Kalshi ticker aliases;
- Polymarket/Kalshi nested values landed as Python-repr text;
- game/date/team cross-source joins;
- optional historical coverage boundaries.

Do not remove a special case because it looks inelegant without proving the
source anomaly no longer exists and adding a regression that preserves correctness.

## SQL Ownership

Large deterministic SQL should live in named `mlb_baseball/sql/*.sql` resources
or, after exact tie-out/promotion, SQLMesh. Small procedural/identity statements
may remain in Python where splitting them would reduce clarity.

Do not duplicate conformance formulas/queries in a second new path during
refactoring. Extract behind the same behavior and tests.

## Decomposition Direction

A likely future package shape is:

```text
conform/
  runner.py
  players.py
  teams.py
  games.py
  venues.py
  plays.py
  pitches.py
  markets.py
```

Exact filenames are not binding. The binding constraints are:

- preserve `conform.run()`/health behavior;
- preserve builder ordering and transaction semantics;
- move tests with responsibilities;
- create local DOX children/sidecars as responsibilities become stable;
- no simultaneous behavioral rewrite.

## Verification

Primary regression suite:

```bash
uv run pytest tests/integration/test_conform.py -q
uv run ruff check mlb_baseball/conform.py tests/integration/test_conform.py
uv run mypy mlb_baseball/conform.py
```

Run source-specific/cross-product tie-outs when changing game, market, WAR,
Retrosheet, MLB API, venue, or standings reconciliation. For identity changes,
assert both matched rows and deliberately-unmatched/ambiguous cases.
