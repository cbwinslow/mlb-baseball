## Why

The derived research tables keep ending up empty, and each time someone has to
run a long manual rebuild before any feature or model work can start. Evidence
from production `mlb` (read-only, 2026-09-27):

- The 06:00 daily job (`scripts/mlb_daily_update.sh`) runs `update`, `conform`,
  `predict`. `conform` deliberately empties the game-level backbone tables
  (`gold.batting_game`, `gold.pitching_game` and the season, team and career
  roll-ups) because a full core rebuild re-issues every game id. Only
  `mlb report` refills them (about 12 minutes), and the daily job never runs it.
  The last successful `conform` on 2026-09-23 left all of them at 0 rows.
- The daily `conform` has crashed within seconds every day since 2026-09-24:
  it needs `core.team_franchise` (migration 0107, merged 2026-09-23) and the
  daily job never applies migrations. `predict` then runs on stale data.
- `mlb build --only-features` quietly produced 0 rows for `feat.player_form`
  and `feat.pitcher_form` from the empty source instead of failing, so the
  model-readiness check reported "not ready" only after a full build.

## North star

The scheduled pipeline leaves every derived table populated and current without
manual rebuilds, and fails loudly and early when it cannot.

## What Changes

- **Phase 1 (fix now):** the daily job applies pending migrations first, runs
  `report` after `conform`, and ends with a check that the derived tables are
  populated; a failed step is reported, not hidden. The feature build refuses
  to run when its source tables are empty.
- **Phase 2 (measure):** record how long each step takes so the slow parts are
  known from evidence, not guessed.
- **Phase 3 (gated on Phase 2 evidence):** stop rebuilding frozen history every
  night. Seasons that cannot change are left alone and only the current season
  is replaced, with ids kept stable by upserting on `retro_game_id`. Adopted only
  if a full rebuild and an incremental catch-up produce identical rows.

## Finish line

1. Three consecutive scheduled runs on production finish with `migrate`,
   `conform` and `report` all ok and `mlb doctor` reporting the backbone tables
   non-empty.
2. A test proves the feature build fails, with a clear message, when
   `gold.batting_game` or `gold.pitching_game` is empty.
3. Per-step timings for `update`, `conform`, `report` and `predict` are recorded
   in the run log and summarised in this change.
4. A recorded go / no-go for incremental rebuilds. If go: an equality test
   between full rebuild and incremental catch-up passes on a disposable fixture
   and on a read-only comparison against production.

## Stop rule

Anything not on the finish line goes to a later list. Explicitly later: a full
SQLMesh migration of core and gold, PgBouncer, parallelising the enrichment
modules, changing surrogate ids or public table contracts, and any change to
which tables exist. The decision to keep the tables and keep the work in SQL is
already made (design D5).

## Capabilities

### New Capabilities

- `pipeline-freshness`: what the scheduled pipeline must guarantee about
  populated, current derived tables, and how failure is reported.

### Modified Capabilities

<!-- None. `statistic-backbone` rules (idempotent rebuild) still hold. -->

## Impact

- `scripts/mlb_daily_update.sh`, `mlb_baseball/feat.py` (refuse empty source),
  `mlb_baseball/health.py` / `mlb doctor` (populated check), step timing in
  logs, and docs (`docs/ARCHITECTURE.md` "Scheduling").
- Phase 3 would touch `mlb_baseball/conform.py` and `mlb_baseball/report.py`;
  it is a separate approval after Phase 2.
- Blocks the plate-appearance engine (`play-engine`) first dataset build: its
  readiness gate needs populated backbone tables.
- One-time catch-up on production `mlb` (apply migration 0107, run `report`)
  needs an explicit owner yes before it is run.
