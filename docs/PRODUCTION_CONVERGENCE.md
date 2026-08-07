# Production convergence audit and runbook

Audited: 2026-08-06. This record is based on read-only queries against the
existing `mlb` database. No migration, ingestion, conformance, truncate, or
other production write was performed during this audit.

## Readiness evidence

The audit connection explicitly reported `current_database = mlb` and
`transaction_read_only = on`.

| Area | Observed state | Decision |
|---|---|---|
| Migration state | `mlb` has migrations `0001`–`0028`; current source also includes `0031_model_provenance.sql` and `0032_feature_snapshot_evaluation.sql` | Do not run `mlb predict`/model workflow again until a reviewed migration is approved and applied. |
| Core/raw scale | Estimated `core` rows: 199.8M; `raw` rows: 190.1M; `core.game`: 227,084 | Treat `mlb` as the production research database; do all refactor verification in `mlb_test_codex`. |
| Latest successful core run | `core` bootstrap succeeded 2026-08-06 07:03 UTC, recording 30,385,890 rows | Existing conformance output is retained; do not rebuild it as part of recovery. |
| `mlb_api` freshness | Repeated updates failed from 15:30–16:15 UTC; the externally scheduled 16:20 UTC update then succeeded with 56,289 rows | The agent did not invoke ingestion. Record the scheduler recovery, then retain the narrow-run verification plan for any future manual operation. |
| Failure cause | `raw.mlb_live_game: append identity columns missing from batch: ['captured_at']` | Fixed by retaining `captured_at` in `LIVE_GAME_COLUMNS`; the later successful scheduler run and production column inspection confirm the live table now includes it. |
| Model workflow | Latest `model` bootstrap failed because `meta.model` does not exist | This is expected while `0031` is unapplied. Do not retry model work before migration verification. |
| Feature availability | `gold.game_feature` had 0 rows at audit time | Do not claim a current production feature/prediction result; rebuilding requires a separately approved ordered run. |
| Locks | 0 PostgreSQL advisory locks at audit time | Ingestion advisory locking remains required. |

The audit queried `public.schema_migrations`, `pg_class`, `meta.ingestion_run`,
`information_schema`, `gold.game_feature`, and `pg_locks` only. Exact command
output is available in the agent transcript; this document intentionally
records the decisions rather than treating transient counts as a static data
catalog.

## Production recovery execution — 2026-08-06

This section records the subsequently owner-approved, narrowly scoped recovery
sequence. No broad connector bootstrap, reset, or ad-hoc production ingestion
was run.

### Final preflight and rollback boundaries

- Read-only preflight confirmed database `mlb`, read-only mode, zero advisory
  locks, migrations through `0028_ingestion_run_backfill_mode.sql`, and both
  pending migrations (`0031_model_provenance.sql`,
  `0032_feature_snapshot_evaluation.sql`). The feature table was empty and the
  latest prediction predated this recovery.
- `0031` creates `meta.model` and `meta.model_run` and adds nullable provenance
  columns/indexes to `gold.prediction`; `0032` creates
  `meta.feature_snapshot` and `meta.model_evaluation`. These are additive
  migration effects. Their rollback boundary is a separately reviewed manual
  schema rollback; no automatic reversal was attempted.
- `mlb conform` is one transaction protected by a PostgreSQL advisory lock.
  A failed run rolls back its core/gold rebuild, records the failure in
  `meta.ingestion_run`, and releases the lock. It is therefore the recovery
  boundary for that phase. `mlb predict` was expressly gated on a non-empty,
  healthy feature table.

### Executed gates and evidence

1. `DATABASE_URL=postgresql:///mlb uv run mlb migrate` applied
   `0031_model_provenance.sql` and `0032_feature_snapshot_evaluation.sql`.
   A read-only verification found both migration-ledger rows, all four
   `meta` provenance relations, all five intended nullable
   `gold.prediction` provenance columns, and zero advisory locks.
2. The first `mlb conform` attempt stopped with
   `duplicate key value violates unique constraint "game_retro_game_id_key"`
   for `MLB824694`. Evidence showed the raw Wrigley Field venue ID was mapped
   to both a current Chicago park and a historical Los Angeles park, fanning a
   single scheduled game out in the venue join. The failed transaction was
   rolled back; its `meta.ingestion_run` row is retained.
3. The join was corrected to select one era-valid venue mapping, covered by a
   focused integration test against the existing `mlb_test_codex`, and committed
   as `80ea428` (`Resolve current-season venue fan-out`).
4. The retry completed successfully at `2026-08-06 17:34:09 UTC`, recording
   30,385,925 rows: 152 teams, 25,543 players, 260 venues, 227,086 games,
   16,485,900 plays, 13,428,264 pitches, 32,910 market rows, and 184,157 WAR
   rows. The lock was released.
5. The required read-only feature gate then found `gold.game_feature = 0`
   (zero labeled rows, no build timestamps or seasons). Per the approved stop
   condition, **`mlb predict` was not run**. No prediction/provenance success
   claim is made. The database had zero advisory locks at the stop point.

The recovery is therefore intentionally incomplete at the feature-build gate.
The next recovery objective must diagnose and explicitly authorize the missing
`gold.game_feature` build before prediction can safely resume. The resulting
separate feature-stage operational sequence is documented in
[`FEATURE_BUILD_RUNBOOK.md`](FEATURE_BUILD_RUNBOOK.md).

## Local verification evidence

- `uv run ruff check` passed.
- `uv run pytest -q tests/unit` passed: `210 passed in 5.07s`.
- `TEST_DATABASE_URL=postgresql:///mlb_test_codex uv run pytest -q
  tests/integration/test_mlb_api_load.py -k capture_live` passed:
  `3 passed, 21 deselected in 4.40s`.
- `uv run mlb --help` passed. The public library import exposes its documented
  API and its focused unit suite passed: `4 passed in 3.62s`.
- A final read-only production query reported `mlb`,
  `transaction_read_only = on`, migration `0028_ingestion_run_backfill_mode.sql`,
  and zero advisory locks. The latest externally scheduled `mlb_api` run was
  successful at 2026-08-06 16:20 UTC; `raw.mlb_live_game` contains
  `captured_at`.

## Required production run plan

This plan is deliberately **not executed** by this repository. It requires an
explicit owner approval for each write phase.

### Phase 0 — release and preflight (read-only)

1. Commit/review the live-snapshot fix and public API work.
2. Install that exact revision in the production checkout; verify with
   `git rev-parse HEAD` and either `uv run mlb --help` or the deployed
   checkout's explicit `.venv/bin/mlb --help` (do not assume a global `mlb`
   executable is on `PATH`).
3. Open a `READ ONLY` connection to `mlb`; verify no active advisory locks,
   record the latest `meta.ingestion_run` per source, and confirm migrations
   are still `0001`–`0028`.
4. Review a backup/restore path and available disk space. Do not treat a test
   database as a production backup.

### Phase 1 — migration approval (write, separately approved)

1. Apply the pending migrations only after reviewing their SQL and testing the
   same release against `mlb_test_codex`.
2. Run `mlb migrate` once, serially, against `mlb`.
3. Verify the migration ledger and required relations (`meta.model`,
   `meta.model_run`, `meta.feature_snapshot`, `meta.model_evaluation`) with
   read-only queries. Stop on any discrepancy.

### Phase 2 — narrowly scoped API recovery (write, separately approved)

1. Run only `mlb ingest mlb_api --mode update`; do not run all connectors.
2. Verify the new `raw.mlb_live_game.captured_at` column/value and a successful
   `meta.ingestion_run` row. Confirm no overlapping advisory lock was bypassed.
3. If it fails, stop. Preserve the failure row and diagnose against the exact
   deployed revision; do not retry in a loop.

### Phase 3 — ordered research rebuild (write, separately approved)

1. Run the scheduled connector update only after Phase 2 is healthy.
2. Run `mlb conform` serially after ingestion completes; it is a large rebuild
   and must not overlap ingestion or another conformance run.
3. Verify core counts/health checks with read-only queries.
4. Run `mlb predict` only after Phase 1 made the model-provenance relations
   available and a non-empty `gold.game_feature` build has been reviewed.

No SQLMesh model is part of this production plan. Python remains the writer
for production raw/core/gold relations.
