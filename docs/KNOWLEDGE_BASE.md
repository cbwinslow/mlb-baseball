# Research and data knowledge base

This is the project’s source-attributed decision register.  It is not a copy
of other projects' documentation.  Each entry records what a source says, what
we verified locally, the decision it supports, and the next check.  Detailed
model research remains in [`RESEARCH.md`](RESEARCH.md); table-level contracts
remain in [`TABLE_CONTRACTS.md`](TABLE_CONTRACTS.md).

## How to add an entry

Record: question, source URL and version/access date, reuse rights, source
claim, local evidence, decision/status, known limits, and the code, test, or
contract affected.  Prefer official source documentation; use community posts
only as leads to verify.  Never copy another project's SQL, prose, assets, or
design into this repository.

## Identity and scheduling

### MLB Stats API `game_pk`

- **Question:** Can one MLB `game_pk` represent two distinct games, especially
  in a doubleheader or a suspended/resumed game?
- **Sources:** MLB GUMBO field guide, accessed 2026-08-10; it describes `pk`
  and `gamePk` as the unique MLB game number.  [baseballr's
  `mlb_game_pks` documentation](https://billpetti.github.io/baseballr/reference/mlb_game_pks.html),
  accessed 2026-08-10, calls `game_pk` the unique game identifier and exposes
  `gameNumber`/`doubleHeader` as separate fields.
- **Local evidence:** `raw.mlb_schedule` has 239,364 observations but 238,142
  distinct `game_id` values.  It has no null `game_id`s.  Repeats are schedule
  history: `68185` has postponed rows plus one final makeup; live-feed game
  `824912` has original date 2026-06-16 and resume date 2026-06-17 under one
  game key.  A historical repeated-final case (`123347`, 1944) is open for
  source reconciliation.
- **Decision:** `game_pk` is the MLB game business key.  Store schedule
  changes as observations, not separate canonical games.  Use Retrosheet's
  own game ID when the record is Retrosheet-native or not safely crosswalked.
- **Status:** Adopted in documentation; production core/gold remains empty,
  and the implementation must be revised/tested in `mlb_test` first.

### Retrosheet game IDs

- **Question:** What key should identify a Retrosheet game without a verified
  MLB crosswalk?
- **Source:** [Retrosheet event-file documentation](https://www.retrosheet.org/eventfile.htm),
  accessed 2026-08-10.  Its 12-character game ID encodes the home team, date,
  and doubleheader number.
- **Decision:** Keep `retro_game_id` as a provider-native key.  It is useful
  for reconciliation but must not be parsed into a replacement for MLB's
  `game_pk`.

## Comparable open projects

### baseballr

- **What it is:** An R package for data acquisition and baseball calculations,
  not a published relational PostgreSQL database model.  Its useful role here
  is API field semantics and calculation cross-checks.
- **Use in this project:** Cross-check API fields, identifiers, and published
  metric definitions. The repeatable game-identity check is
  `baseballr::mlb_game_pks(date, level_ids = 1)`: compare its `game_pk`,
  `gameGuid`, `officialDate`, `gameNumber`, and `doubleHeader` fields against
  a same-date official Stats API schedule response or an archived project
  fixture. It is a reference check, not a bootstrap dependency and not a
  replacement for source-faithful raw landing.
- **Source:** [baseballr repository](https://github.com/BillPetti/baseballr),
  accessed 2026-08-10.

### baseball.computer

- **What it is:** An open historical database built from Retrosheet/Lahman.
  Its repository builds a DuckDB database with SQLMesh models, external-model
  metadata, and model/column documentation.
- **Use in this project:** Borrow the *practice* of documented models,
  declared sources, tests/audits, and lineage.  Our PostgreSQL raw/core/gold/
  meta design and additional Stats API/Statcast scope remain independent.
- **Source:** [baseball.computer repository](https://github.com/droher/baseball.computer),
  accessed 2026-08-10.

## Database quality rules

- `information_schema` is the portable inventory of columns, constraints, and
  nullability.  PostgreSQL's `pg_stats.null_frac` is a fast estimate after
  `ANALYZE`, not proof; exact counts are required before adding a constraint.
- Use exact, targeted checks for keys, foreign-key coverage, allowed values,
  dates, and model input coverage.  Use planner and I/O statistics to prioritize
  performance work, not to certify correctness.
- PostgreSQL references: [information schema](https://www.postgresql.org/docs/current/information-schema.html),
  [`pg_stats`](https://www.postgresql.org/docs/current/view-pg-stats.html), and
  [cumulative statistics](https://www.postgresql.org/docs/current/monitoring-stats.html).
