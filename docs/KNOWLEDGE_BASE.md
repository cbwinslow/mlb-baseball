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
- **Status:** Adopted and conformed in production on 2026-08-12. Further
  coverage changes remain test-database-first and require a separate
  production-safe recommendation.

### Retrosheet game IDs

- **Question:** What key should identify a Retrosheet game without a verified
  MLB crosswalk?
- **Source:** [Retrosheet event-file documentation](https://www.retrosheet.org/eventfile.htm),
  accessed 2026-08-10.  Its 12-character game ID encodes the home team, date,
  and doubleheader number.
- **Decision:** Keep `retro_game_id` as a provider-native key.  It is useful
  for reconciliation but must not be parsed into a replacement for MLB's
  `game_pk`. MLB-only canonical rows retain NULL rather than a manufactured
  Retrosheet-shaped identifier.

### Pregame feature cutoff

- **Question:** What timestamp defines information that may enter the first
  MLB game-prediction feature family?
- **Source:** The retained official MLB schedule payload's `game_datetime`
  field, inspected 2026-08-12; it is available for all 239,364 retained
  schedule observations in the production baseline.
- **Local evidence:** A strict `mlb_test` rehearsal retained postponed history
  in `raw.mlb_schedule`, selected one row per `game_pk`, and built 2,468
  regular-season feature rows without duplicate MLB keys. Fixture tests show
  the second game of a doubleheader sees the first game's completed result but
  never its own result.
- **Decision:** `gold.game_feature.feature_cutoff_at` is the schedule's
  declared first-pitch time. Windows use only completed regular games before
  that order; the documented tie-break order is cutoff, game number, then MLB
  key. A missing provider start time means no row in this first MLB-only
  relation rather than a guessed date-only cutoff.
- **Known limit:** This is a scheduled start cutoff, not a claim that every
  source value was available at that exact time. Weather, lineups, markets,
  and live fields remain outside the first base family.

## Feature-admission evidence

### Provider metrics versus entering-game inputs

- **Question:** Can published WAR, wOBA, wRC+, Statcast leaderboards, or actual
  lineups be copied directly into a pregame game-win model?
- **Sources:** [FanGraphs WAR methodology](https://library.fangraphs.com/misc/war/),
  [linear weights](https://library.fangraphs.com/principles/linear-weights/),
  [FIP definition](https://library.fangraphs.com/pitching/fip/),
  [MLB Statcast glossary](https://www.mlb.com/glossary/statcast), and
  [Retrosheet event-file specification](https://www.retrosheet.org/eventfile.htm),
  accessed 2026-08-12.
- **Local evidence:** The production read-only census found 138 raw relations
  and 3,545 fields. It confirmed 16,465,588 Retrosheet events across 205,890
  games; 13,400,779 Statcast pitches from 2008–2026; 239,364 schedule
  observations with no missing scheduled start time; and only 128 retained
  probable-pitcher observations for 77 games, captured 2026-08-09 through
  2026-08-12. Provider aggregates have materially different coverage: OAA
  begins 2016, sprint speed/framing begin 2015, and Baseball-Reference batting
  begins 2008. These values are evidence of coverage, not evidence that every
  provider value was available before a historical game.
- **Decision:** Treat provider metrics as provider/version-specific descriptive
  or reporting data unless rebuilt from earlier completed events or retained
  with a pregame publication timestamp. Actual Retrosheet lineups/weather and
  final-season WAR/wRC+/wOBA cannot become pregame features by a convenient
  join. The first candidate implementations are project-computable prior-game
  team offense/defense and captured starter/bullpen workload.
- **Implementation status:** Admission queue only; no new feature family is
  approved by this entry. See [feature-admission sources](research/feature_admission_sources.md)
  and [feature-admission queue](FEATURE_ADMISSION_QUEUE.md).

### Retrosheet supplemental team identities

- **Question:** How should historical Negro League and newly assigned
  Retrosheet team codes enter `core.team`?
- **Source:** Retrosheet `TEAM{year}.TXT` records, landed as
  `raw.retrosheet_team0`, accessed 2026-08-12.
- **Decision:** Use the official code, city, nickname, and first/last game
  dates only when the code is absent from Retrosheet's primary TEAMABR
  reference. Do not infer a relationship from a similar display name. The
  MLB numeric team ID is attached only when Retrosheet and the MLB team-history
  source share the exact code.

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
  fixture. `scripts/validate_baseballr_schedule.R` exports only overlapping
  identifiers/schedule fields when a researcher already has R installed. It
  is a reference check, not a bootstrap dependency and not a replacement for
  source-faithful raw landing.
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

## Experiment evaluation

### Chronological probability experiments

- **Question:** How should game-win models be compared without learning from
  later baseball games or rewarding confident but poorly calibrated answers?
- **Sources:** [scikit-learn model-evaluation guide](https://scikit-learn.org/stable/modules/model_evaluation.html),
  accessed 2026-08-12; its documented classification probability metrics are
  log loss and Brier score. The cross-validation guide is supporting general
  background, but this project uses baseball calendar folds rather than a
  generic splitter because games are unevenly spaced and doubleheaders share a
  date.
- **Decision:** Use calendar-year development folds, train only on seasons
  before the test season, retain 2025 as untouched holdout, and use 2026 only
  for forward monitoring. Compare every model on the exact common eligible
  game rows. Log loss and Brier score are primary; accuracy is secondary.
  Persist fixed-bin calibration values, and omit slope/intercept when a fold is
  too small to support them.
- **Implementation:** `meta.experiment_snapshot`, `meta.experiment`,
  `meta.experiment_fold`, `gold.game_feature_snapshot`, and
  `mlb_baseball.model.experiment`.
- **Known limits:** No calibration fitting, hyperparameter search, significance
  claim, champion promotion, market evaluation, or production prediction is
  authorized by this first test-only experiment package.
