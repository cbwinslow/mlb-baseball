## Why

`core.player` structurally excludes any player without a Retrosheet id: the
conform insert filters `WHERE key_retro IS NOT NULL` and `core.player.retro_id`
is `NOT NULL UNIQUE`. Retrosheet assigns ids months after a season ends, so
every current-season debut and call-up is missing. Verified against production
`mlb` (2026-09-07): 105 distinct players in 2026 regular-season box scores
(3,385 batting player-games, ~8.4%) do not resolve to `core.player` — e.g.
Kazuma Okamoto, Ryan Ward, Trei Cruz. All 105 are in `raw.register_people`
with a `key_mlbam` and none have a `key_retro`. This blocks
`backbone-2026-source` (paused at task 3/14), whose 2026 game builders join
`core.player` on `mlbam_id`.

## What Changes

- **`core.player.retro_id` becomes nullable** (new migration). The `UNIQUE`
  constraint stays — Postgres allows multiple NULLs. **BREAKING** for any
  consumer that assumes `retro_id` is always present (audit below shows none
  are broken, only Retrosheet-era builders that legitimately see no null-retro
  rows).
- **`conform_player_insert.sql` admits a bounded MLBAM-only set.** Keeps
  `key_retro IS NOT NULL`, and additionally admits register rows that have a
  `key_mlbam` **and** appear in MLB game data (`raw.mlb_boxscore_batting` /
  `_pitching` / `raw.mlb_playbyplay`). Verified: this adds 2,182 players (incl.
  spring-training-only), not the ~104k of admitting every MLBAM-keyed register
  row. `_build_players` is truncate-and-rebuild, so a later real `key_retro`
  is picked up on the next full conform — no `ON CONFLICT` needed.
- **New `mlb doctor` check** (in `conform.health_check()`): every player in a
  regular-season `core.game` box score resolves to `core.player`. Tolerance 0
  once this lands (currently ~3,385 batting rows unresolved).
- **Consumer audit** of the ~25 `mlb_baseball/**` files referencing `retro_id`,
  recorded in the change: confirm each `JOIN core.player ON retro_id = …` is a
  Retrosheet-era builder where a null-retro 2026 player never appears (correct
  to drop), and flag any consumer that would produce a *wrong* (not merely
  empty) result.
- **Docs**: `DATA_DICTIONARY.md` and `TABLE_CONTRACTS.md` `core.player`
  contract (retro_id nullable; what NULL means; backfills later); a new ADR in
  `docs/DECISIONS.md`.

## Capabilities

### New Capabilities
- `player-identity`: how a person becomes a row in `core.player` — which source
  keys admit a player, when `retro_id` may be null and what that means, the
  bounded MLBAM-only admission for current-season players, and the resolution
  guarantee that `mlb doctor` enforces (every regular-season game participant
  resolves).

### Modified Capabilities
<!-- none — no existing spec covers player identity; statistic-backbone's
     2026 builders consume core.player but do not define its admission rules -->

## Impact

- **Schema:** one new migration — `ALTER TABLE core.player ALTER COLUMN
  retro_id DROP NOT NULL` plus a column comment. Additive/loosening only; no
  column removed, no type changed. Next free number is `0103` (`0102` is taken
  by the paused `backbone-2026-source`).
- **Code:** `mlb_baseball/sql/conform_player_insert.sql` (WHERE clause),
  `mlb_baseball/conform.py` `health_check()` (one new check). `_build_players`
  itself is unchanged.
- **Data:** `core.player` grows 25,543 → ~27,725 on the next `mlb conform`
  (owner-run against production). New rows carry `retro_id = NULL` until
  Retrosheet processes the season.
- **Consumers:** ~25 files reference `retro_id`; the audit confirms which are
  safe. `backbone-2026-source`'s 2026 builders (join on `mlbam_id`) are
  unblocked.
- **Docs:** `docs/DATA_DICTIONARY.md`, `docs/TABLE_CONTRACTS.md`,
  `docs/DECISIONS.md`, `openspec/specs/player-identity/spec.md` (new).
- **No new dependency.** `raw.register_people` and `raw.mlb_boxscore_*` /
  `raw.mlb_playbyplay` are already ingested.
