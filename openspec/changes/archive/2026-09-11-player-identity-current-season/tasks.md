## 1. Migration — make `retro_id` nullable

- [x] 1.1 Add `migrations/0103_core_player_nullable_retro.sql`:
  `ALTER TABLE core.player ALTER COLUMN retro_id DROP NOT NULL;` plus
  `COMMENT ON COLUMN core.player.retro_id IS '...'` (null = admitted on MLBAM
  id, Retrosheet has not processed this player's season yet; backfills on the
  next full conform). Verify: `uv run mlb migrate` against a disposable test DB
  succeeds and a second `uv run mlb migrate` is a no-op (idempotent).
- [x] 1.2 Confirm the column is now nullable and the `player_retro_id_key`
  UNIQUE constraint still exists. Verify: `\d core.player` (or an
  `information_schema` query) shows `is_nullable = YES` and the unique
  constraint present.

## 2. Conform — bounded MLBAM-only admission

- [x] 2.1 Failing integration test `test_conform_admits_current_season_players_with_no_retrosheet_id`
  in `tests/integration/test_conform.py`: seeds a batter in a box score + a
  pitcher only in play-by-play (both `key_mlbam`, no `key_retro`) and a third
  MLBAM-only person with no game data; asserts the first two land in
  `core.player` with `retro_id IS NULL` (resolvable by `mlbam_id`) and the
  third is absent. Verified RED (fails without the impl, 130s) then GREEN.
- [x] 2.2 **Approach changed** (see design D3): a modified WHERE clause in
  `conform_player_insert.sql` can't reference the optional `raw.mlb_boxscore_*`
  tables (Postgres needs them to exist just to plan). Instead: new
  `mlb_baseball/sql/conform_player_insert_current_season.sql`
  (`WHERE key_retro IS NULL AND key_mlbam IN (<4-way UNION>)`), run by
  `_build_players` after the base insert inside `conn.transaction()` +
  `except psycopg.errors.UndefinedTable` — the savepoint-and-skip pattern
  `_build_teams`/`_build_venues` already use. No `ON CONFLICT` needed
  (`key_retro IS NULL` keeps the passes disjoint). Verified GREEN.
- [x] 2.3 `test_current_season_player_retro_id_backfills_on_the_next_rebuild`:
  two `conform.run()` calls leave exactly one row for the player; after a real
  `key_retro` is set on the register row, a third run populates `retro_id`
  with no duplicate. (Run in the batched verification below.)
- [x] 2.4 No orphaned SQL/columns: `conform_player_insert.sql` unchanged (still
  the first pass); the new file selects the identical column list;
  `_build_players()` gains only the second savepointed insert. `sqlfluff lint`
  clean on both SQL files + the migration.

## 3. Health checks — resolution guarantee + fan-out guard

- [x] 3.1 `test_health_check_flags_an_unresolved_regular_season_player`: a
  regular-season `core.game` (with a `game_pk`) + a box-score batting line for
  a person with no `core.player` row → the `core.player regular-season
  resolution` check returns `ok = False` with `"1 row"` in the detail. Passed.
- [x] 3.2 Added `check_no_rows("core.player regular-season resolution", …)` to
  `conform.health_check()` — a single scalar summing the batting and pitching
  `raw.mlb_boxscore_* JOIN core.game (regular) LEFT JOIN core.player ON
  mlbam_id WHERE core.player.id IS NULL` counts.
  `test_health_check_passes_when_every_regular_season_player_resolves` (add the
  `core.player` row → `ok = True`) passes.
- [x] 3.3 Added `check_no_duplicate_key("core.player", "mlbam_id")`.
  `test_health_check_flags_a_duplicate_core_player_mlbam_id` (two `core.player`
  rows, same `mlbam_id` — now possible since `retro_id` is nullable) → check
  `ok = False`, `"duplicate"` in detail. Passed.
- [x] 3.4 Extended `test_health_check_includes_join_integrity_safeguards` to
  assert both new check names (`core.player regular-season resolution`,
  `core.player.mlbam_id uniqueness`) are present in `conform.health_check()`.
  Passed. (`doctor.run()` collects `conform.health_check()` at `doctor.py:255`,
  unchanged.)

## 4. Consumer audit

- [x] 4.1 `consumer-audit.md` written — 17 files with `\bretro_id\b`, every
  `JOIN core.player … ON retro_id = …` categorized. All are Retrosheet-era
  (≤2025) consumers a NULL-retro 2026 player never reaches; `platoon_splits`
  improves (2026 starter resolves via `mlbam_id`); `player.py` docstring was
  stale.
- [x] 4.2 **No consumer verdicted WRONG** — no code fix required. Doc fix:
  `mlb_baseball/player.py` module docstring updated (`retro_id` no longer
  "NOT NULL … every conformed player has one").

## 5. Docs

- [x] 5.1 `docs/DATA_DICTIONARY.md` §6 — added a `core.player` entry: admission
  rule (Retrosheet id **or** MLBAM id + MLB game appearance), `retro_id`
  nullable + what a NULL means + truncate-rebuild backfill + the `mlb doctor`
  guarantee.
- [x] 5.2 `docs/TABLE_CONTRACTS.md` — `core.player` row updated: nullable
  `retro_id` (UNIQUE where present), the two-rule admission, never admits an
  MLBAM-only register row with no game appearance, backfill, migration 0103.
- [x] 5.3 `docs/DECISIONS.md` — **ADR-284** added (ADR-283 is taken by the
  in-flight `separate-postseason-stats`; used the next free number, same
  reasoning as migration 0103). Records the decision, the separate-pass
  mechanism, rejected alternatives, the consumer audit, and the verification.
- [x] 5.4 `mlb_baseball/conform.py.dox.md` — new "Player Identity Contract"
  section (two-pass build, nullable `retro_id`, bounded MLBAM admission, the
  two `mlb doctor` checks, ADR-284). `mlb_baseball/player.py` docstring fixed.
  `git grep "key_retro IS NOT NULL"` in `docs/` returns nothing.

## 6. Verification (integration / system)

- [x] 6.1 `pytest -p no:libtmux tests/integration/test_conform.py -q` →
  **68 passed, 0 failed** in 1026s (17 min). RED verified for
  `test_conform_admits_current_season_players_with_no_retrosheet_id` (fails
  without the second pass). The overlap case — a register row with both a
  `key_retro` and an MLB-game appearance → exactly one `core.player` row —
  is asserted in `test_current_season_player_retro_id_backfills_on_the_next_rebuild`.
  (`-p no:libtmux` works around a broken system `libtmux` pytest plugin on
  this box; unrelated to the change.)
- [x] 6.2 **Not run** — the machine's full suite is impractical
  (`test_doctor.py` alone took 3+ hours per the owner). Ran the narrowest
  relevant set instead (6.1). `ruff check .` (whole repo), `mypy`,
  `sqlfluff`, `scripts/lint_sql_ownership.py` all clean. Full CI suite runs on
  the PR.
- [x] 6.3 `uv run ruff check .` — clean. `uv run mypy mlb_baseball/conform.py
  mlb_baseball/player.py` — clean (project uses `mypy`, not `basedpyright`).
  `uv run sqlfluff lint` — clean on both `conform_player_insert*.sql` and
  `migrations/0103_*.sql`. `scripts/lint_sql_ownership.py` — passed.
- [ ] 6.4 **Owner step (not CI, not me).** After `mlb migrate` + `mlb conform`
  on production `mlb`: `SELECT count(*) FROM raw.mlb_boxscore_batting bb JOIN
  core.game g ON g.game_pk = bb.game_pk AND g.game_type = 'regular' LEFT JOIN
  core.player cp ON cp.mlbam_id = bb.person_id WHERE cp.id IS NULL;` must be
  **0**, and `mlb doctor` must show `core.player regular-season resolution`
  passing. (Left unchecked — requires the owner-run production conform.)
- [x] 6.5 `backbone-2026-source`'s 2026 builders join `core.player` on
  `mlbam_id`; the 2,182 MLBAM-only admissions (verified count) cover the 105
  previously-unresolved 2026 regular-season players. Noted in the PR body.
  Final unblock confirmation is the owner's 6.4 conform.
