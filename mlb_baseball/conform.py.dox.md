# `conform.py` DOX

## Purpose

Own the current cross-source **raw -> core conformance/reconciliation pipeline**. This module never fetches network data. It turns already-landed source-faithful raw tables into canonical teams, players, games, venues, standings, plays, pitches, markets, WAR bridges, and related identity links.

This is a legacy gravity-well module with valuable evidence-driven logic. Preserve its behavior/facade while decomposing it incrementally; do not rewrite it wholesale.

## Ownership

Implementation: `conform.py`.

Primary outputs currently include:

- `core.team`
- `core.player`
- `core.venue`
- `core.team_alias`
- `core.game`
- `core.standing`
- `core.play`
- `core.pitch`
- `core.market`
- `core.player_war`
- selected backfilled/enriched columns in these canonical relations.

User entry point: `mlb conform` / `conform.run()`.

Health entry point: `conform.health_check()`.

## Core Architectural Contract

- `conform.py` is a transform/reconciliation layer, **not a connector**.
- It must not touch external network sources.
- Raw remains source-faithful. Conformance may normalize/reconcile source meaning into canonical core fields while preserving uncertainty as NULL rather than guessing.
- Cross-source identity resolution is evidence-driven and order-sensitive in several places. Do not turn it into unordered generic joins without proving parity.
- Stable set-based SQL should move into named package SQL resources / SQLMesh when appropriate, but procedural/evidence-order reconciliation may remain Python.

## Rebuild Strategy

Current `run()` performs a full truncate-and-rebuild of the relevant core/gold dependency closure rather than incremental core reconciliation.

That strategy is deliberate today because:

- cross-source joins do not have a simple isolated changed-chunk boundary at current scale;
- a full rebuild avoids partial-overwrite classes of bugs;
- dependent FK tables must be truncated in one coherent statement;
- consolidated truncation avoids repeatedly walking/fsyncing the large season-partition graph for `core.play` / `core.pitch`.

Do not casually reintroduce per-builder `TRUNCATE ... CASCADE` calls. A measured production/test investigation showed repeated partition fsync costs and FK-closure behavior were materially expensive.

An incremental redesign is allowed only as a deliberate program with exact parity, dependency invalidation rules, and measured benefit.

## Prerequisite Contract

Hard prerequisites checked before rebuilding:

- `raw.retrosheet_team`
- `raw.register_people`
- `raw.retrosheet_gameinfo`

The error message must tell the operator which ingest command is missing.

Many enrichments are intentionally optional and must fail visibly-but-gracefully when their source table is absent, including families such as Retrosheet event detail, MLB play-by-play, Statcast pitches, venue enrichment, standings, markets, and WAR depending on current implementation.

Do not convert an optional enrichment into a hard prerequisite without a product/data-contract decision.

## Build/Ordering Contracts

The order inside `run()` is part of correctness. Important current dependencies include:

1. build teams and players;
2. build venues before games so game rows can resolve canonical venue IDs;
3. seed team aliases;
4. build games;
5. backfill MLB `game_pk` using increasingly strong/appropriate evidence;
6. derive canonical MLB team IDs from resolved games;
7. use numeric MLB team identity to resolve remaining game/team-name drift;
8. build completed spring games and standings after team-ID backfills;
9. bulk-build play/pitch facts with index drop/rebuild optimization around large writes;
10. backfill play win probability;
11. build market rows using corrected game/team identities and PIT-safe price snapshots;
12. build WAR bridges;
13. commit once the coherent rebuild is complete.

Do not reorder passes because two functions look independent. Inspect the comments/tests and downstream keys first.

## Game Identity Contract

- `core.game.retro_game_id` and MLB `game_pk` are distinct identifiers.
- MLB `game_pk` is backfilled onto canonical games using source evidence; unmatched rows remain NULL rather than receiving guessed IDs.
- Identity resolution is multi-pass because historical display names, relocations/rebrands, doubleheaders, and incomplete source fields make one string join insufficient.
- Numeric MLB team IDs are preferred over current display-name matching once a trustworthy bridge exists.
- Doubleheader/game identity collisions are a known silent-risk class; preserve duplicate/grouped health checks and tests.

## Team Alias Contract

`_TEAM_ALIAS_SEED` exists only for external sources without a shared stable numeric ID (not as a universal naming dictionary). Entries are evidence-backed aliases/ticker codes seen in real market/MLB source data, including rebrand/relocation cases.

Do not expand it speculatively or use it where an existing numeric crosswalk is available.

## Market / Point-in-Time Contract

`core.market` is a high-risk leakage boundary.

- Polymarket/Kalshi source metadata may require Python parsing because current raw rows store some nested structures as repr-like text rather than native JSON.
- Market identity resolution combines source event/ticker team/date information with canonical game/team aliases.
- `implied_probability` must resolve from the latest captured market snapshot **strictly before the actual game start**, not from current/settled price.
- If no qualifying pregame observation exists, use NULL rather than a post-outcome/guessed probability.
- Preserve/record the observation timestamp that resolved the price when the schema supports it.

Any change here requires dedicated PIT/leakage regression tests.

## Venue and Standing Contracts

- `core.venue` uses Retrosheet park ID as the primary bridge to canonical games; MLB venue metadata is best-effort enrichment by verified matching and may remain NULL.
- Do not fuzzy-fill uncertain venue identity merely to increase coverage.
- `core.standing` resolves canonical teams through MLB team IDs and therefore must run after those backfills.
- MLB standings fields contain real source marker quirks such as `-` meaning different things in different columns. Preserve column-specific parsing/null rules rather than a generic "dash = zero" conversion.

## Play/Pitch Contracts

- Retrosheet, MLB API, and Statcast sources can contribute different grains/details.
- Optional source absence should not break a core rebuild if the source is not a hard prerequisite.
- Partitioning affects uniqueness constraints: health checks must preserve natural-key uniqueness independently of the physical partition key where PostgreSQL constraints cannot express that directly.
- Join coverage is a correctness signal. Silent row loss from inner/non-unique joins has caused real bugs and must remain monitored.

## Health / Reconciliation Contract

`health_check()` is not cosmetic. It protects against classes of silent conformance failure including:

- missing/empty core outputs;
- stale/failed conform runs;
- duplicate `game_pk` / grouped doubleheader identity problems;
- Retrosheet/MLB/Statcast/WAR join coverage loss;
- team-season win/count reconciliation against independent Lahman facts;
- natural-key duplicates hidden by partition-key constraints.

When adding a new high-value conformed source/output, add an actionable health/tie-out check where possible.

## SQL Ownership

This module already uses `mlb_baseball.sql.read_sql()` for substantial set-based statements. Continue moving stable sizeable SQL out of Python strings into named SQL resources or SQLMesh according to `docs/SQL_OWNERSHIP.md`.

Do not split a formula/identity rule between Python and SQL without a clear canonical owner and parity coverage.

## Decomposition Guidance

Recommended future extraction boundaries, while keeping `conform.run()` stable:

- orchestration / dependency ordering;
- team/player identity;
- game identity/backfills;
- venue/standing enrichment;
- play/pitch conformance;
- market identity/PIT snapshot resolution;
- WAR/stat bridges;
- conformance health/tie-outs.

Move one concern at a time with behavior-preserving tests. The sidecar should shrink and route to child DOX as real subpackages/modules become durable.

## Work Guidance

Before editing:

1. identify the exact output relation/pass being changed;
2. inspect its raw source tables and migrations;
3. inspect `tests/integration/test_conform.py` and targeted health tests;
4. determine whether later passes depend on this output;
5. preserve honest NULL behavior and source evidence ordering;
6. check whether an existing named SQL resource owns the set-based logic.

Avoid broad cleanup mixed with a semantic identity change.

## Verification

At minimum for behavior changes:

- targeted `tests/integration/test_conform.py` cases;
- real PostgreSQL fixture, not mocked transaction/join semantics;
- health/tie-out tests for the affected relation;
- duplicate/coverage tests when keys/joins change;
- PIT market tests when market timing changes;
- SQL resource parity/SQLFluff when SQL changes;
- full conformance integration path before claiming behavior preservation.

Performance changes to truncation/index/build order require measured before/after timings on representative partition/data volume.

## Child DOX Index

No child DOX yet. As `conform.py` is decomposed, create local sidecars/child `AGENTS.md` at the new durable boundaries and convert this document into the orchestration/facade map rather than duplicating child detail.
