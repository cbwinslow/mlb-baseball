# Data audit runbook

`mlb doctor` checks whether the system and connectors are operating. `mlb
audit` is the separate, read-only check for whether the important game-level
data contracts are safe for research and model work.

## Commands

```bash
uv run mlb audit
uv run mlb audit --scope database
uv run mlb audit --scope statcast
uv run mlb schema
```

- `game` is the default. It checks required schedule IDs, schedule-history
  duplicates, canonical MLB game-key uniqueness and source/decade coverage,
  doubleheaders, stable game/play value ranges, team/game foreign-key coverage,
  unresolved pitch-source-key coverage, expected upcoming-game nulls, and
  prediction identity. It reports retained Retrosheet-native identities
  separately from a missing identity or a missing MLB key on an MLB game.
- `database` adds PostgreSQL planner-statistics context: estimated live/dead
  rows, last-analyzed time, cumulative index scans, and landing freshness where
  the raw table exposes `_loaded_at`. It also flags physically duplicate index
  definitions, which add write and maintenance cost without helping queries.
  These estimates guide maintenance; they do not prove data correctness.
- `statcast` adds the intentionally heavier exact scan of every raw Statcast
  pitch against distinct raw schedule keys, grouped by season. Use it after a
  Statcast load and before changing conformance logic.

All modes begin a read-only transaction. They never repair, migrate, ingest,
truncate, or rebuild data.

`mlb schema` is the companion catalogue for database-object review. It reports
the live table/view shape, parent partition, column and nullable-column counts,
and primary/unique/foreign/check constraint plus index counts. Use
`mlb schema --partitions` for the complete physical partition list.

## Reading results

- `PASS`: the stated invariant held.
- `WARN`: an honest, retained gap needs review but was not silently discarded.
- `FAIL`: a required field, identity, or foreign-key contract is broken; do not
  run features/models until it is understood.
- `SKIP`: the needed table or layer is not populated yet. This is expected on a
  clean clone but means the corresponding research layer is not ready.

Not every null is a failure. An upcoming feature row has no completed
`core.game` yet; a Retrosheet-native game can have no MLB key; and a Statcast
pitch may have no resolved canonical game. The audit reports these separately
from a missing required source key, a missing identity, or an orphan foreign
key. A warning is an investigation queue, not permission to silently fill a
value with a weak match.

Retrosheet uses game number `0` for an ordinary single game, so it is valid.
The official play feed can also retain a terminal count of five balls or four
strikes. The controlled-value check allows those documented source values and
looks for values outside that wider domain instead.

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
