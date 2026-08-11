# Production feature-build runbook

This is a reviewed operational sequence, not authorization to write to
production. It separates reusable research features from model predictions.
Run it only from the released revision containing migrations `0033`–`0035` and the
`mlb features` command.

## Scope and boundaries

## Identity migration preflight and cutover

This procedure is separate from a feature build. It has **not** been applied
to production.

1. Use a read-only connection to record prediction/feature row counts, NULL
   `game_instance_key` counts, available disk/WAL headroom, and active locks.
2. Run `mlb migrate`. Migration 0034 prepares nullable columns; 0035 stops at
   its NOT NULL gate until identities have been backfilled.
3. As the database owner, repeat bounded batches until both remaining counts
   are zero:

   ```sh
   DATABASE_URL=postgresql:///mlb uv run mlb backfill-game-identities --batch-size 1000
   ```

   Each invocation commits its feature and prediction batches independently.
   It is safe to retry after interruption: only NULL keys are selected, and an
   ambiguous lookup receives an explicit `legacy-prediction:*` key rather than
   a guessed match. Stop if errors, remaining counts do not decline, or WAL/
   disk headroom is unsafe.
4. Validate no NULL feature/prediction keys and no duplicate durable feature
   keys; retain command output. Then rerun `mlb migrate`. The concurrent
   prediction-key index is built before the brief primary-key attachment.
5. There is no automatic schema rollback. On failure preserve the error and
   database state, correct the cause, and retry the idempotent owner command
   or pending migration; do not delete predictions or manually rewrite keys.

- `mlb features` rebuilds and enriches `gold.game_feature` in one transaction.
  It does **not** insert, update, or backfill `gold.prediction`.
- `mlb predict` retains its legacy behavior: it invokes the same feature stage,
  then writes market/model predictions and prediction provenance. Do not use it
  as a feature-health probe.
- Both commands record a `meta.ingestion_run` row under source `model`, acquire
  the source advisory lock and an exclusive workflow advisory lock, and roll
  back their data transaction on failure. Connector ingestion holds a shared
  workflow lock, so it cannot race a derived-table rebuild.
  Their run ledger row and failure details are retained; the lock is released.
- `gold.game_feature` is currently rebuilt in place (`TRUNCATE` then insert),
  not versioned. The recovery boundary is transaction rollback, not a retained
  previous feature-table snapshot. Do not attempt manual row restoration while
  a run is active.
- Existing builds upsert `meta.game_instance` for historical compatibility.
  The authoritative MLB business key is `mlb_game_pk`; do not derive a second
  game from a schedule revision. See `GAME_INSTANCE_IDENTITY.md`.

## Phase 0 — read-only preflight

Use an explicitly read-only connection to `mlb` and record the result.

1. Confirm the target is `mlb`, the release revision is correct, and no
   PostgreSQL advisory ingestion lock is granted.
2. Confirm `0033_ingestion_run_features_mode.sql`,
   `0034_prediction_game_instance.sql`,
   `0035_game_instance_registry.sql`, and
   `0036_prediction_instance_primary_key.sql` are in
   `public.schema_migrations`. If it is absent, stop: apply only the reviewed
   migration in a separately approved migration phase, then re-run preflight.
3. Record the latest `meta.ingestion_run` rows for `core` and `model`, current
   `gold.game_feature` and `gold.prediction` counts, and core-game date range.
4. Confirm the required core tables have data. Do not run a connector
   bootstrap/update, `mlb conform`, or reset as part of this runbook.

## Phase 1 — feature build (approved write)

Run serially:

```sh
DATABASE_URL=postgresql:///mlb uv run mlb features
```

Stop immediately if the command fails or the terminal `meta.ingestion_run`
record is not `success`. Do not continue to prediction. The failed feature
transaction is rolled back; preserve the command output and run-ledger error.

## Phase 2 — read-only feature-health gate

Verify all of the following before prediction:

- `gold.game_feature` is non-empty.
- Its durable `game_instance_key` is unique. `mlb_game_pk` is an MLB lookup
  field and can legitimately repeat for suspended/resumed games.
- completed regular-season rows have a non-null outcome where `core.game` has
  a final score, while upcoming rows remain explicitly unlabeled.
- season/date coverage is plausible relative to `core.game` and the current
  schedule; `_built_at` is from this run.
- the latest `model/features` ingestion run is successful, and zero advisory
  locks remain.

Any failed check is a stop condition. Do not run `mlb predict`; preserve the
read-only query output and diagnose against the released code/test fixture.

## Phase 3 — prediction (separately approved write)

Only after Phase 2 is healthy, run:

```sh
DATABASE_URL=postgresql:///mlb uv run mlb predict
```

This command intentionally refreshes the same in-place feature stage before
writing predictions, preserving its prior backward-compatible behavior. Stop
on a non-successful model run; do not retry in a loop or invoke any broad
ingestion command.

## Phase 4 — read-only prediction/provenance gate

Verify:

- a successful terminal `meta.ingestion_run` row for `model/bootstrap`;
- expected new `gold.prediction` rows with non-null `model_id`, `model_run_id`,
  `data_cutoff`, and `feature_snapshot_id` where the model supports them;
- matching `meta.model`, `meta.model_run`, and `meta.feature_snapshot` records;
- plausible prediction timestamps/coverage and no duplicate prediction identity
  at the applicable model/game grain; and
- zero granted advisory locks.

If this gate fails, stop and retain the evidence. Transaction rollback protects
the failed prediction write; schema rollback or manual destructive cleanup is
outside this runbook and requires separate review.
