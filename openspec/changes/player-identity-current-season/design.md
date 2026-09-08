## Context

See proposal.md — Why. Current state that shapes the approach:

- `mlb_baseball/sql/conform_player_insert.sql` is a single
  `INSERT INTO core.player SELECT ... FROM raw.register_people WHERE key_retro
  IS NOT NULL`.
- `conform._build_players()` just runs that file and returns `cur.rowcount`.
  `core.player` is emptied by `run()`'s one consolidated
  `TRUNCATE core.play, core.pitch, ... core.player, ...` before the build
  functions run — so player conform is **truncate-and-rebuild every time**,
  not incremental.
- `core.player`: `retro_id text NOT NULL`, `UNIQUE (retro_id)`
  (`player_retro_id_key`); `mlbam_id text` with a plain index
  (`player_mlbam_id_idx`), **no unique constraint**.
- Verified against production `mlb` (2026-09-07): `raw.register_people` has
  520,934 rows / 129,732 with `key_mlbam` / 25,543 with `key_retro`; 0
  duplicate non-null `key_mlbam`; the 2,182 MLBAM-only + in-game-data rows all
  have a `key_uuid`.
- `raw.mlb_boxscore_*.person_id` and `raw.mlb_playbyplay.batter_id` /
  `pitcher_id` are integer; `core.player.mlbam_id` is text.
- `mlb doctor` collects `conform.health_check()` (`doctor.py:255`). `health.py`
  already provides `check_no_rows(label, sql)` — passes only when `sql`
  returns 0.

## Goals / Non-Goals

**Goals:**
- Admit current-season MLBAM-only players without weakening the identity model
  for the 25,543 Retrosheet-era players.
- Keep the admitted set bounded and explainable.
- `retro_id` backfills automatically once Retrosheet catches up — no manual
  reconciliation step.
- `mlb doctor` proves the resolution guarantee.

**Non-Goals:**
- Changing `core.player`'s primary anchor (still `id`; `retro_id` stays a
  unique alternate key where present). Re-keying on `chadwick_uuid` / `mlbam_id`
  is a much larger blast radius and is not needed.
- Making `conform._build_players()` incremental.
- Adding a `mlbam_id` unique **constraint** in this change (a health check is
  enough; a DB constraint is a separate migration with its own backfill/verify).
- Resolving postseason / spring-training game participants — the product's
  coverage is the regular season; the health check is scoped there.

## Decisions

### D1: Drop `NOT NULL` on `retro_id`; do not mint a placeholder

New migration `0103_core_player_nullable_retro.sql`:
`ALTER TABLE core.player ALTER COLUMN retro_id DROP NOT NULL;` plus a
`COMMENT ON COLUMN core.player.retro_id` explaining a null. The `UNIQUE`
constraint stays — Postgres permits multiple nulls in a unique column.

- **Alternative — synthetic `retro_id`** (e.g. `mlbNNNNNN`): rejected.
  `retro_id` is a source-faithful Retrosheet key; a fake value pollutes it,
  risks colliding with a real future id, and needs a cleanup pass when the
  real id lands. A null is honest and self-correcting.
- **Alternative — re-anchor `core.player` on `chadwick_uuid`**: rejected as
  out of scope. ~25 files join on `retro_id`; that migration is a project of
  its own with no current forcing function.
- Industry practice agrees: pybaseball / baseballr return `key_retro = NaN`
  for recent debuts and consumers handle the null.

### D2: Bounded admission — MLBAM id AND appears in MLB game data

Admit a register row when it has `key_mlbam` **and** that id appears in
`raw.mlb_boxscore_batting` / `_pitching` / `raw.mlb_playbyplay` (batter or
pitcher). No casts needed — `key_mlbam`, `person_id`, `batter_id`, `pitcher_id`
and `core.player.mlbam_id` are all `text`.

- Adds **2,182** players (25,543 → ~27,725). Includes spring-training-only
  names — accepted: they are real people with a real MLBAM identity, they
  carry no regular-season stats so the `gold` relations ignore them, and the
  set is bounded and stable. The owner-authored task file made this call.
- **Alternative — admit every `key_mlbam IS NOT NULL` row** (~104k more):
  rejected, pulls in every minor-leaguer and foreign-league player.
- **Alternative — filter the game-data subquery to `game_type IN ('regular',
  …)`**: rejected as complexity for no benefit.

### D3: A separate second-pass INSERT, not a modified WHERE clause

The task file said "change the WHERE clause in `conform_player_insert.sql`".
That does not work: `raw.mlb_boxscore_*` / `raw.mlb_playbyplay` are **optional**
raw tables (a fresh clone that has not run the `mlb_api` connector does not have
them), and Postgres needs a referenced table to exist just to *plan* the query
— so a single-file `… OR key_mlbam IN (SELECT … FROM raw.mlb_boxscore_batting)`
would make those tables a hard prerequisite for admitting *any* player.

Instead: a second SQL resource, `conform_player_insert_current_season.sql`
(`WHERE key_retro IS NULL AND key_mlbam IN (<4-way UNION>)`), run by
`_build_players()` after the first insert inside `conn.transaction()` and
wrapped in `except psycopg.errors.UndefinedTable` — the exact savepoint-and-skip
pattern `_build_teams` (`raw.retrosheet_team0`) and `_build_venues`
(`raw.mlb_venue`) already use. `key_retro IS NULL` keeps the two passes
disjoint, so no row is inserted twice and no `ON CONFLICT` is needed.

Backfill is automatic: `_build_players()` runs inside `run()`'s central
`TRUNCATE`, so every `mlb conform` rebuilds `core.player` from scratch. Once
Retrosheet assigns a `key_retro`, the first pass picks the player up (now with
a non-null `retro_id`) and the second pass skips them.

- **All-or-nothing on the three MLB tables** (any missing → whole second pass
  skipped) matches how `raw.mlb_win_prob` etc. are already treated, and matches
  production: the `mlb_api` connector creates `raw.mlb_playbyplay` +
  `raw.mlb_boxscore_batting` + `raw.mlb_boxscore_pitching` together per game
  (`connectors/mlb_api.py` `_load_playbyplay_for_game` then
  `_load_boxscore_for_game`).

### D4: Health check via `check_no_rows` in `conform.health_check()`

`check_no_rows("core.player regular-season resolution", <sql>)` where `<sql>` is
a single scalar — the sum of two subqueries (batting + pitching), each
`raw.mlb_boxscore_* JOIN core.game (game_type='regular') LEFT JOIN core.player
ON mlbam_id WHERE core.player.id IS NULL`. `check_no_rows` reads one value and
fails on any non-zero; it also catches `UndefinedTable` and returns a FAIL when
`raw.mlb_boxscore_*` is absent (fresh clone) — consistent with the existing
coverage checks.

A second check, `check_no_duplicate_key("core.player", "mlbam_id")`, guards the
fan-out risk below (`mlbam_id` has an index but no UNIQUE constraint, and
current-season players are now keyed on it).

- **Alternative — `check_join_coverage`**: it compares total counts, but not
  every box-score row *should* resolve (only regular-season), so the "expected"
  side would need the same join filter and it reduces to the same query with
  more moving parts.

### D5: Consumer audit is a task deliverable, recorded in the change

`grep -rl 'retro_id' mlb_baseball/` → ~25 files. Categorize each:
Retrosheet-era builder (`*_retrosheet_*.sql`, 1910–2025 game builders) that
only sees `g.season <= 2025` → a null-retro 2026 player never reaches it,
dropping it is correct. Flag any consumer that would be **wrong** (not merely
empty) with a null `retro_id`. Findings go in `design.md` (appended) or a
`consumer-audit.md` in the change folder before implementation is marked done.

## Risks / Trade-offs

- **A consumer inner-joins `core.player` on `retro_id` and silently drops 2026
  players** → D5 audit checks every one. Known-safe: `backbone-2026-source`'s
  2026 builders join on `mlbam_id`; every `*_retrosheet_*` builder is scoped
  to `season <= 2025` where all players have a `retro_id`.
- **`mlbam_id` has no unique constraint; a bad register could fan out
  `core.player`** → verified 0 duplicate `key_mlbam` in production today.
  `check_no_duplicate_key("core.player", "mlbam_id")` added to
  `conform.health_check()` as the guard (cheap, matches the existing
  `core.game.game_pk` pattern).
- **Rollback after `mlb conform` has run** → once null-retro rows exist,
  re-adding `NOT NULL` fails until they are deleted. The migration is
  effectively forward-only in production; document that in the migration and
  the rollback note. On a scratch DB it rolls back cleanly (no null rows yet).
- **Spring-training names in `core.player`** → ~2,182, bounded, carry no
  regular-season stats; `gold` relations filter to `game_type = 'regular'` so
  they never surface as phantom stat lines.

## Migration Plan

1. `migrations/0103_core_player_nullable_retro.sql` — `ALTER COLUMN retro_id
   DROP NOT NULL` + `COMMENT ON COLUMN`. One change, reversible on a clean DB.
   (Independent of the in-flight `0100`–`0102` — those are `gold.*` tables —
   so filename-order application is safe regardless of merge order.)
2. `mlb migrate` on a scratch DB; re-run to confirm idempotent. **Done** —
   `mlb_scratch_pi`, applies clean + no-op on re-run; `retro_id` `is_nullable
   = YES`, `player_retro_id_key` intact.
3. Ship `conform_player_insert_current_season.sql`, the `_build_players` second
   pass, and the two `conform.health_check()` checks.
4. Owner runs `mlb migrate` + `mlb conform` against production `mlb`; then the
   verification query must return 0 and `mlb doctor` must pass the new checks.
5. Rollback: revert the code + migration; the DB column stays nullable
   (harmless — nothing requires `NOT NULL`). Only re-apply `NOT NULL` if
   deliberately abandoning the feature, after deleting null-retro rows.

## Open Questions

None that block. A `mlbam_id` unique **constraint** (vs. the health check
shipped here) and re-anchoring identity on `chadwick_uuid` are both larger
follow-ups with no current forcing function.
