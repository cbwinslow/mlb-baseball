# Data audit runbook

`mlb doctor` checks whether the system and connectors are operating. `mlb
audit` is the separate, read-only check for whether the important game-level
data contracts are safe for research and model work.

## Commands

```bash
uv run mlb audit
uv run mlb audit --scope database
uv run mlb audit --scope statcast
```

- `game` is the default. It checks required schedule IDs, schedule-history
  duplicates, canonical MLB game-key uniqueness, doubleheaders, pitch/play
  foreign-key coverage, expected upcoming-game nulls, and prediction identity.
- `database` adds PostgreSQL planner-statistics context (row/dead-row estimates
  and last-analyzed time). Those estimates guide maintenance; they do not prove
  data correctness.
- `statcast` adds the intentionally heavier exact scan of every raw Statcast
  pitch against distinct raw schedule keys, grouped by season. Use it after a
  Statcast load and before changing conformance logic.

All modes begin a read-only transaction. They never repair, migrate, ingest,
truncate, or rebuild data.

## Reading results

- `PASS`: the stated invariant held.
- `WARN`: an honest, retained gap needs review but was not silently discarded.
- `FAIL`: a required field, identity, or foreign-key contract is broken; do not
  run features/models until it is understood.
- `SKIP`: the needed table or layer is not populated yet. This is expected on a
  clean clone but means the corresponding research layer is not ready.

Not every null is a failure. An upcoming feature row has no completed
`core.game` yet; a Statcast pitch may have no resolved canonical game. The
audit reports these separately from a missing required source key or an orphan
foreign key.

## Current Statcast conclusion

The 2026-08-10 production `mlb audit --scope statcast` run found all
13,384,464 raw Statcast pitches had a source `game_pk`, and all had a matching
raw schedule key. Therefore the previously observed sparse pitch-to-core-game
join is not an API-download or raw-schedule coverage problem. It is a
conformance/crosswalk problem.

Migration `0041_core_pitch_source_game_key.sql` preserves the Statcast
`source_game_pk` on every conformed pitch. After the next test-database
conform run, use `mlb audit` to measure unresolved `core.pitch.game_id` rows
and retain their source keys for exact classification. Do not infer a game
from a weak name/date match merely to improve the percentage.

## Safe production sequence

1. Run `mlb doctor` and `mlb audit --scope statcast` against production; both
   are read-only.
2. Apply/verify the same migrations and conformance workflow in `mlb_test`.
3. Run `mlb audit` in `mlb_test`; resolve every `FAIL` and document every
   `WARN` before requesting owner approval for production conformance.
4. Only after explicit approval, run the production migration/conform sequence,
   then repeat `mlb audit` and retain its output with the run record.
