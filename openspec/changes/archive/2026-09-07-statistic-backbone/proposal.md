## Why

The grain-complete statistic backbone is **built** — `gold.batting_game`,
`gold.pitching_game`, and the season / team / career roll-ups (migrations
0094–0098, `sql/*_build.sql`, integration tests, 12.9M rows in production) —
but its contract lives only in a superpowers design doc and ADR-278's
scattered "Relation N" addenda. Two v1 milestone items need it written down as
a real spec: `openspec/specs/statistic-backbone/spec.md` (the NEXT block), and
the still-open "Relation 6" decision — how the new event-derived season tables
relate to the existing Baseball-Reference-sourced `gold.player_season`. This
change closes both. No code changes: it documents what exists and records one
decision.

## What Changes

- **New capability spec `openspec/specs/statistic-backbone/spec.md`** — the
  behavioural contract for the grain ladder as a queryable warehouse:
  - The grain set: a statistic relation at `(batter, game)`, `(pitcher, game)`,
    `(player, season, team)` + one combined full-season row, `(team, season)`,
    and `(player)` career; batting and pitching; a two-way player gets a row in
    both.
  - Source fidelity: built from `raw.retrosheet_event` (1910–2025) with a
    `raw.mlb_playbyplay` builder for 2026+, matching the tied-out team-stat
    builders' event-flag handling (`bat_event_fl` / `ab_fl` / `sf_fl` /
    `rbi_ct` …). Not from `core.play`, which lacks those flags.
  - Honesty: every counting/rate stat is MLB-glossary-defined; data the source
    does not carry is `NULL` with a documented reason, never guessed
    (`era` absent — no earned-run reconstruction; `SB`/`CS` deferred to a
    future `gold.baserunning_game`; pre-1988 `gidp` undercounts).
  - Roll-up rule: season lines roll off the game tables, career off the
    season `is_combined` rows — never a table off a sibling; rates recomputed
    from summed components, `NULL` on a zero denominator.
  - Determinism: idempotent rebuild (truncate-and-replace, transactional);
    each relation has a hand-calculated fixture, a tie-out test against a real
    published player-season within a stated tolerance, and an `mlb doctor`
    check.
  - Rights: every backbone relation is `local_research` in the `mlb export`
    allow-list (builders join `core` dims for surrogate keys, and `public_safe`
    permits Retrosheet-only lineage); a `retro_id`-keyed `public_safe` variant
    is recorded as follow-up, not built here.
  - The two season lines are **parallel and distinct**: `gold.player_season` /
    `gold.team_season` are the Baseball-Reference / Lahman "official" line
    (2008+, carries `era` and BRef-only fields); `gold.batting_season` /
    `gold.pitching_season` are the event-computed line (1910+, team-aware,
    `ra9` not `era`). They are documented as separate sources for separate
    purposes and are never wired together as a two-writer.
- **ADR-281 in `docs/DECISIONS.md`** — records the Relation 6 decision above
  (keep both, parallel + documented; do not make `player_season` a view),
  closing ADR-278's open "Relation 6".
- **ADR-278 updated** — its "Relation 6 … still open" paragraph points to
  ADR-281 as resolved.

Out of scope (separate later changes): expanding the Baseball-Reference
tie-out beyond the current two cases; the MkDocs docs site; Stage 2 (advanced
metrics at the new grains); the `public_safe` retro-id-keyed variant; WAR.

## Capabilities

### New Capabilities

- `statistic-backbone`: the grain-complete classical statistic warehouse —
  what relations exist, at what grain, from what source, with what null and
  rights policy, and how each is validated.

### Modified Capabilities

_None._ (`delivery` already covers exporting these tables; this capability is
the warehouse contract itself, a separate concern.)

## Impact

- `openspec/specs/statistic-backbone/spec.md` — new.
- `docs/DECISIONS.md` — ADR-281 added; ADR-278's Relation 6 paragraph updated.
- `docs/DATA_DICTIONARY.md` / `docs/TABLE_CONTRACTS.md` — a pointer to the spec
  if they do not already describe every backbone column/grain (verify during
  apply; update only what is stale).
- No source code, no SQL, no migrations, no dependencies.
