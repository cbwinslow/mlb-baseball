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
- `core.team_franchise`
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
3. build team franchises (`core.team_franchise` + `core.team.franchise_id`) —
   must run after teams, before team aliases (below), since alias
   resolution now depends on it;
4. seed team aliases;
5. build games;
6. backfill MLB `game_pk` using increasingly strong/appropriate evidence;
7. derive canonical MLB team IDs from resolved games;
8. use numeric MLB team identity to resolve remaining game/team-name drift;
9. build completed spring games and standings after team-ID backfills;
10. bulk-build play/pitch facts with index drop/rebuild optimization around large writes;
11. backfill play win probability;
12. build market rows using corrected game/team identities and PIT-safe price snapshots;
13. build WAR bridges;
14. commit once the coherent rebuild is complete.

Do not reorder passes because two functions look independent. Inspect the comments/tests and downstream keys first.

## Player Identity Contract

- `_build_players` runs two passes into `core.player` (truncated centrally by
  `run()`): `conform_player_insert.sql` admits every `raw.register_people` row
  with a Retrosheet id; `conform_player_insert_current_season.sql` then admits
  rows that have an MLBAM id and appear in MLB's own game record
  (`raw.mlb_boxscore_batting` / `_pitching` / `raw.mlb_playbyplay`). The second
  pass is savepointed and skipped whole if those optional tables are absent.
- `core.player.retro_id` is nullable (migration 0103) — NULL for a
  current-season player admitted on their MLBAM id. It is UNIQUE across
  non-NULL values and backfills on the next full conform once Retrosheet
  assigns the real id. `key_retro IS NULL` in the second pass keeps the two
  passes disjoint; there is no upsert.
- Do not admit an MLBAM-only register row that never appears in MLB game data
  (that is every minor-leaguer and foreign-league player). Do not mint a
  synthetic `retro_id`.
- `mlb doctor` enforces `core.player regular-season resolution` (tolerance 0)
  and `core.player.mlbam_id uniqueness`.
- See ADR-284.

## Game Identity Contract

- `core.game.retro_game_id` and MLB `game_pk` are distinct identifiers.
- MLB `game_pk` is backfilled onto canonical games using source evidence; unmatched rows remain NULL rather than receiving guessed IDs.
- Identity resolution is multi-pass because historical display names, relocations/rebrands, doubleheaders, and incomplete source fields make one string join insufficient.
- Numeric MLB team IDs are preferred over current display-name matching once a trustworthy bridge exists.
- Doubleheader/game identity collisions are a known silent-risk class; preserve duplicate/grouped health checks and tests.

## Team Franchise Contract

`core.team` is one row per team-era (`retro_team_id`, `first_year`,
`last_year`); Retrosheet reuses `retro_team_id` across non-contiguous eras
(e.g. `HOU` NL 1962-2012 vs AL 2013-2021, `MIL` AL 1970-1997 vs NL
1998-2021 — real code *reuse*), and reissues a franchise a genuinely new
code on relocation (the Athletics: `OAK` through 2024, `ATH` from 2025 —
real code *change*). `core.team_franchise` links every resolvable era to
its permanent franchise, from data already ingested
(`raw.lahman_teams_franchises` + `raw.lahman_teams.franchid`/`teamidretro`).

- `current_retro_team_id` is the franchise's newest resolved era (greatest
  `first_year`) — the real, current code. Use this **only** for a
  consumer with no season/year context of its own that specifically needs
  "what code does this franchise use right now" (e.g. matching an
  external source's live ticker/alias, as `_build_team_aliases` does).
  **Do not** use it as a general substitute for season-scoped resolution
  below — a franchise can have more than one historical code change
  (confirmed directly: the Athletics alone span `PHA` 1901-1954, `KC1`
  1955-1967, `OAK` 1968-2024, `ATH` 2025, all one franchise), so
  `current_retro_team_id` is only correct for "right now," not for
  resolving a specific past season.
- **A season-scoped consumer resolves each row to its OWN era directly,
  not through any single franchise-wide anchor column.** `core.team`
  already carries one row per era with its own matching `retro_team_id`
  and year range — for the whole history above, not just the most recent
  code. `report.py`'s `gold.team_season` build (and its health-check
  mirror) join via a `LATERAL` that prefers a direct
  `retro_team_id` + year-range match on `core.team`, falling back to any
  `core.team` row sharing the same `franchise_id` (still year-scoped)
  only when a row's own code has no matching `core.team` row yet. An
  earlier version of this fix routed everything through a
  `legacy_retro_team_id` column (the franchise's OLDEST era,
  unconditionally) — reverted after review found it silently
  misattributes or drops every OTHER era's real data for any franchise
  with more than one historical code change, not just the Athletics' most
  recent one (see docs/DECISIONS.md ADR-292's "reverted design" note).
- `mlb_baseball/model/season.py`'s `load_schedule_from_db` does **not**
  go through `core.team_franchise` at all: `ALL_MLB_TEAMS`/`MLB_DIVISIONS`
  is a hand-maintained Python list with no season-awareness of its own
  (modernizing it is separately scoped and deferred), so no query derived
  from this table can know which single code that list happens to
  hardcode. It keeps a narrow, explicit
  `CASE WHEN retro_team_id = 'ATH' THEN 'OAK' ELSE retro_team_id END`
  inline instead — the same shape as the original hand-patched fix this
  change otherwise replaces.
- **Never use `core.team.last_year = 9999` to mean "the current era."**
  It is Retrosheet's own "currently active" sentinel and can lag a real
  code reissue — confirmed directly for the Athletics, whose retired
  `OAK` row is still `last_year = 9999` while `ATH` is the real 2025 code.
  `first_year` does not have this staleness problem.
- `core.team.franchise_id` is nullable; a real, documented subset of rows
  (pre-1969 Negro League team-eras) has no Lahman franchise crosswalk at
  all and stays NULL rather than guessed. `mlb doctor` flags a row only
  when a crosswalk was actually expected (a matching `raw.lahman_teams`
  row exists) and still resolved to NULL — see Health/Reconciliation
  Contract below.

## Team Alias Contract

`_TEAM_ALIAS_SEED` exists only for external sources without a shared stable numeric ID (not as a universal naming dictionary). Entries are evidence-backed aliases/ticker codes seen in real market/MLB source data, including rebrand/relocation cases.

Do not expand it speculatively or use it where an existing numeric crosswalk is available.

Alias targets resolve through `core.team_franchise`'s `current_retro_team_id`
first (so an alias for a relocated franchise attaches to its real current
era's `team_id`), falling back to the seed code's own row when franchise
resolution isn't available (e.g. Lahman not yet ingested) — this table
must keep working without it, per ADR-029.

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
- natural-key duplicates hidden by partition-key constraints;
- a `core.team` row whose franchise link should have resolved (a real
  `raw.lahman_teams` match exists) but didn't.

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
