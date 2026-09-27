## Context

Observed on production `mlb`, 2026-09-27 (read-only):

- `meta.ingestion_run`: `core` (conform) takes 39–44 minutes, `report` about 12
  minutes, `model` (predict) about 51 minutes. `report` last ran on 2026-09-23
  02:48; a successful daily `core` run at 06:20 the same day emptied the
  backbone after it.
- `logs/mlb_daily_update.log`: `conform` failed on 09-21 and 09-22 (another
  ingestion run held the lock), and on 09-24, 09-25 and 09-26 with
  `relation "core.team_franchise" does not exist` (migration 0107 not applied).
  A failed `conform` rolls back its `TRUNCATE`, so core kept its old rows.
- `conform` re-issues every game id because `core.game.id` is a `bigserial`
  and the table is truncated and refilled; the natural key `retro_game_id` is
  unique. That is why every table that references `core.game` is emptied with
  it (`mlb_baseball/conform.py`, the consolidated `TRUNCATE`).
- The feature build read the empty backbone and reported `feat.player_form: 0
  rows` as success.
- The Aug 28 performance spec (`docs/superpowers/specs/2026-08-28-pipeline-performance-design.md`,
  Phase 3) already names the structural fix (process changed games only, full
  rebuild kept as the tested path). This change reuses that direction and does
  not repeat its research.

## Goals / Non-Goals

**Goals:** stop the recurring empty tables; make failures loud; measure before
optimising; decide incremental on evidence.

**Non-Goals:** the Phase 2/3 items in the Aug 28 spec other than the one
incremental decision below; new tools; changing public table contracts.

## Decisions

**D1. Daily order is `migrate → update → conform → report → predict`.** Reuse the
existing commands and the existing `run_step` shape in
`scripts/mlb_daily_update.sh`; each step stays independently tracked, with two
explicit gates because `run_step` alone records a failure and carries on: a
failed `migrate` stops every later step (they would run against the old
schema) and exits non-zero; `report` runs only when `conform` succeeded
(`report` over an emptied `core` would only rebuild empties). `update` and
`predict` keep their current independent behaviour. `mlb
build` already wraps migrate/conform/report, but it also builds features and
has different failure handling, so the daily job keeps its own steps.

**D2. A populated check ends the run.** The existing `mlb doctor` checks
(`check_table_has_rows` on each backbone relation) are reused; the daily job
runs them last and exits non-zero on any empty relation. No new health
framework.

**D3. The feature build validates its source first.** `mlb_baseball/feat.py`
counts every source relation it reads (`core.game`, `gold.batting_game`,
`gold.pitching_game`) before building and raises with the relation name when
one is empty. `conform` can empty `core.game` too, so it is covered.

**D4. Measure, then decide.** Step timings go into the daily log. Phase 3 is
decided from those numbers plus one read-only profile of where `conform` and
`report` spend their time.

**D5. Stay in SQL.** The work is set-based aggregation over 16.5M play rows
already in PostgreSQL; the DuckDB feature build reads it directly and finished
220,191 game rows in about 8 seconds. Moving rows into Python would add cost
without a measured gain. This is a recorded decision, not an open question.

**D6. If incremental is adopted (Phase 3), the approach is season-level
replace, not a new framework.** Frozen history (seasons that cannot change) is
left alone; the current season's rows are deleted and rebuilt; `core.game`
is upserted on its natural key so ids for frozen seasons never change. The key
is `retro_game_id` when present and `game_pk` when it is not: production has
236,846 games, 11,969 of them with no `retro_game_id` (MLB-only games), none
with neither, and both columns carry a unique index
(`game_retro_game_id_key`, `core_game_game_pk_key`). This is
smaller and safer than migrating everything to SQLMesh, and it can still be
moved into SQLMesh later. It is adopted only if the equality test in the
spec passes. Open questions to answer in Phase 3 before building: which
seasons can actually change (Retrosheet corrections, 2026 partial data), and
what else references `core.game` ids.

## Risks / Trade-offs

- **Migrations run unattended.** A bad migration would run at 06:00. Mitigation:
  migrations already ship with CI and the repo's migration safety rules
  (`migrations/AGENTS.md`); a migration failure stops dependent steps.
- **`report` adds about 12 minutes to the daily run.** Accepted for Phase 1;
  Phase 3 may remove it.
- **Incremental can silently drift from a full rebuild.** Mitigation: the
  equality test is a hard gate, and the full rebuild stays available and tested.
- **Overlapping runs.** The existing `flock` on the daily job stays; the
  09-21/09-22 lock failures are recorded, not changed here.

## Migration Plan

1. Land Phase 1 behind tests (disposable Postgres fixtures only).
2. With owner approval, apply pending migrations and run `mlb report` once on
   production `mlb` (target named explicitly).
3. Watch three scheduled runs, then close Phase 1.
4. Review Phase 2 timings; record the Phase 3 go / no-go.
