# SQLMesh operations and adoption gates

Plan 02B operational contract, 2026-08-06.

## Current state

`transforms/config.yaml` is a **spike-only** gateway to the pre-existing
disposable `mlb_spike` database. It is not a production configuration and is
the only SQLMesh gateway currently allowed to apply models. It contains the
following experimental candidates:

- `core.venue` — natural-key parity candidate only; not eligible to replace
  the referenced-surrogate-ID production relation.
- `gold.park_factor` — correct formula on an eager venue-season shape, but not
  yet the Python writer's completed-and-scheduled consumer-demand shape.
- `gold.team_woba` — correct long game-team calculation; not yet the wide
  `gold.game_feature` projection written by Python.

External-model declarations are catalog-neutral logical names (for example
`core.game` and `raw.retrosheet_event`); the selected gateway supplies the
database/catalog. This is required for the same reviewed model project to be
testable against the existing `mlb_test_codex` database later, without copying
or recreating a second database.

The original `mlb` database is never a SQLMesh target without a separately
reviewed configuration, owner approval, and a migration-specific cutover plan.
No new test database is permitted: any future integration run must reuse the
existing `mlb_test_codex` database and an isolated, explicitly named schema or
candidate relation.

## Reproducible checks

From the repository root:

```bash
uv sync --frozen --extra dev
uv run sqlmesh -p transforms test
uv run sqlmesh -p transforms plan --no-prompts
uv run sqlmesh -p transforms audit --model core.venue --model gold.park_factor --model gold.team_woba
```

`test` runs DuckDB fixtures only. `plan --no-prompts` is review-only and must
be captured before an apply. `audit` points at the spike gateway and is only a
valid verification after a reviewed spike plan has been applied. CI runs the
DuckDB test and SQLMesh parse/plan review commands; it never auto-applies.

## Environment and state requirements before an adoption apply

An adoption configuration must be introduced in the same reviewed change as
its first eligible model. It must specify all of the following explicitly:

1. The checked-in `candidate` gateway using the existing `mlb_test_codex`
   database for integration verification, never a newly created database.
2. A dedicated SQLMesh state schema and candidate output namespace; it must
   not overwrite `core`, `gold`, or `meta` relations during parity testing.
3. External-model declarations generated from the actual tested relation
   schemas and pinned to the gateway/database they describe.
4. A separate production gateway which is absent by default and may be used
   only after the owner approves that named cutover.
5. Model naming that preserves existing natural and surrogate IDs, constraints,
   grants, and dependent relation contracts. A candidate may not inherit the
   live relation name merely because its result rows look similar.

## Per-model promotion gate

Before Python stops writing any relation:

1. Record its grain, identity, cutoff time, dependencies, mutation owner, and
   rollback owner in `TABLE_CONTRACTS.md`.
2. Run DuckDB unit tests, then a full-table and sampled point-in-time tie-out
   against the existing Python output in `mlb_test_codex`.
3. Explain every difference; zero unexplained differences are allowed for a
   replacement writer.
4. Measure query/runtime behavior and verify all SQLMesh audits after a
   reviewed `plan --no-prompts`.
5. Apply only to the named candidate/test namespace. Retain the Python writer
   and prior output until the owner approves the production cutover.
6. For an approved production cutover, preserve the previous relation (or an
   explicitly versioned compatibility object), retain the prior writer for a
   rollback window, and use a restatement/rebuild plan rather than an
   unreviewed manual table change.

## Candidate namespace and executable parity gate

`candidate` is deliberately non-default. A reviewed, explicitly authorized
candidate apply must use `--gateway candidate ... plan02_candidate`.
SQLMesh therefore keeps state in `sqlmesh_plan02_candidate` and materializes
candidate relations under `core__plan02_candidate` / `gold__plan02_candidate`,
never `core`, `gold`, or `meta`. Do not use `--auto-apply` until a reviewed
`plan --no-prompts` identifies only those namespaces.

Before a candidate writer can be considered, run this read-only gate after its
candidate relations exist:

```bash
TEST_DATABASE_URL=postgresql:///mlb_test_codex \
uv run python scripts/verify_sqlmesh_candidate.py \
  --venue core__plan02_candidate.venue \
  --feature gold__plan02_candidate.game_feature
```

It fails unless every candidate venue retains the exact existing `core.venue.id`
for its `retro_park_id`, and every candidate feature row has the same completed
game identity or scheduled-game `mlb_game_pk` anchor plus completed/scheduled
classification as `gold.game_feature`.
This is intentionally stricter than a natural-key/value tie-out: it blocks the
current `core.venue` spike model, which has no surrogate `id`, and it blocks
the current narrow gold candidates, which do not yet produce the required wide
game-feature relation. Python remains the writer until this gate and the
per-model promotion requirements pass.

## Backfill, restatement, and rollback

Every incremental model declares its time grain and start date. A correction
uses a reviewed `sqlmesh plan --restate-model <model> --start <date> --end
<date> --no-prompts` first, then the same bounded range with an explicitly
authorized apply. A rollback reactivates the retained Python writer or
compatibility object, verifies its output against the preserved relation, and
records the reason in `plans/PROGRESS.md`; it does not delete historical data
or state as a shortcut.
