## Context

Observed 2026-10-08 (read-only):

- Postgres `mlb`: `raw` 150 tables / 5,049 cols (~907M rows); `core` 327 / 6,150
  (~31M); `gold` 24 / 1,043 (~7M); `meta` 19 / 222. Biggest gold objects are
  `game_feature` (1.3 GB, 289 cols) and `game_feature_snapshot` (1.3 GB), both
  legacy per `docs/TABLE_CONTRACTS.md`.
- ADR-287: features/models live in DuckDB `feat.*`; `mlb build` is the only
  crossing point at `core`. feature-store-v1 slice 1 is done (32/32 tasks);
  `~/.mlb/mlb.duckdb` (2.9 GB) holds `feat.game` (221K rows), `feat.player_form`
  (4.4M), `feat.pitcher_form` (5.9M).
- SQLMesh: 18 models in `transforms/`, gateway pointed at throwaway Postgres
  database `mlb_spike`; ADR-271 keeps both named `.sql` files and SQLMesh, one
  writer per table.
- baseball.computer (public README): DuckDB + **SQLMesh** + Parquet (45 external
  sources), Rust Retrosheet parser, distributed as a DuckLake 1.0 catalog on R2.
  Model groups: staging (box_score, event, game, biodata, baseballdatabank),
  intermediate (event_level, game_level, player_game_level, player_season_level,
  season_level, expectancy, park_factors, states, machine_learning, bio,
  data_quality), metrics (offense/pitching/fielding at career, player-season-by-
  league and team-season grain; standings), synthetic_box_score. Its docs site
  still says dbt; the README says SQLMesh. License CC BY-NC-SA: study, never copy.
- Roles: `baseball`, `letta`, `letta_user`, `postgres_exporter` own nothing in
  `mlb` and have no sessions. `cbwinslow` owns 11 databases (incl. `mlb_test`,
  ~10 `mlb_test_*_tmpl`, and `mlflow`). Production `mlb` is owned by role `mlb`.

## Goals / Non-Goals

**Goals:** one written direction per layer/tool; evidence-based core/gold gap
list; parity matrix; ranked literature-backed feature backlog; stale-doc and
stale-object cleanup; reproducible for outside users.

**Non-Goals:** new ingestion sources; building models; rewriting `conform`;
dropping or renaming `mlb`/`cbwinslow` roles; any production write without
explicit per-step owner approval.

## Decisions

Status key: PROPOSED (owner agreed in conversation, needs ADR) / OPEN (to be
decided from evidence gathered in tasks).

1. **PROPOSED - Postgres stays the system of record for raw/core.** Constraints,
   transactions and cross-source identity reconciliation need it (ADR-287).
2. **PROPOSED - DuckDB for features/analysis; Python for fitting, simulation,
   sequential state; outputs saved to DuckDB/Parquet plus `meta.*` run records.**
   Already built for features; keep.
3. **OPEN - SQLMesh.** It is engine-agnostic, not DuckDB-specific. Evidence now
   points one way: baseball.computer (the benchmark) runs SQLMesh on DuckDB.
   Options: (a) SQLMesh on Postgres for gold only (today); (b) SQLMesh on DuckDB
   for gold + `feat.*`; (c) plain versioned SQL files only. Decide after a small
   spike (task 3.x): can a SQLMesh model read Postgres `core` through DuckDB and
   build a `feat.*` relation with parity to the current builder? Lean: (b) if
   the spike passes, because it unifies tooling and matches benchmark practice.
4. **OPEN - where gold statistics are materialized (Postgres vs DuckDB/Parquet).**
   Measure one representative gold query on each before deciding. "Postgres is
   slow" is a hypothesis until measured.
5. **PROPOSED - MLflow deferred** until a baseline model exists; then use local
   file store (no server). The `mlflow` database already on the server is not
   assumed to be in use. `meta.*` evaluation tables already exist; do not
   duplicate them without need.
6. **PROPOSED - parity target = capability parity, not code parity.** Build the
   matrix from public docs; implement from published formulas; add what they
   lack (PIT feature store, market data, cited formulas, commercial license).
7. **PROPOSED - external research first.** Prefer peer-reviewed/community
   published features (Tango, FanGraphs, Statcast, academic) as the starting
   backlog; each must carry citation, grain, null policy and PIT rule before
   admission (existing admission process in `docs/research/feature_admission_sources.md`).
8. **PROPOSED - Field census is derived from live sources, not typed lists.**
   The current classifier (`mlb_baseball/field_census.py`) is a hand-typed list of
   ~40 (table, column) pairs; everything else defaults to `needs_research`, so
   "0 unconformed candidates" (2026-10-08 run) is unproven. Replace with:
   (a) facts from Postgres catalogs (`pg_attribute`, `information_schema`,
   `pg_stats`, `pg_class`, `pg_stat_user_tables`; view dependencies from
   `pg_depend`/`pg_rewrite`), as one permanent read-only profile view over
   raw/core/gold/meta; (b) lineage from a maintained SQL parser (SQLMesh
   column-level lineage / sqlglot) reading the repo's SQL at census time;
   (c) `pg_stat_statements` only as a runtime cross-check; (d) anything without
   lineage is reported "unknown", never guessed. Known limit: Postgres records no
   lineage for tables filled by `INSERT ... SELECT`, and Python-moved data has no
   SQL to parse. Alternatives rejected: extending the typed list (goes stale);
   installing a new extension (none provides column lineage).
10. **PROPOSED - Metrics-first order.** Choose target metrics first, then trace the
   inputs each needs, then change core/gold only where a metric needs a field.
   The field census reports what exists; it does not decide what to add. Core
   stores one canonical value per fact; cross-source redundancy stays in `raw`
   and comparison results go to a `meta` validation table, not duplicate core
   columns. Redundancy exists to be compared, so every core build needs a
   roll-up tie-out (atomic events summed to game/season vs Lahman, Baseball-
   Reference, etc.). Validation-ladder doc + source-by-grain matrix are owed.
11. **PROPOSED - Vocabulary.** Metric = the named recipe (formula, inputs,
   constants, citation), e.g. wOBA. Stat = the number a metric produces for a
   player/team/period, hindsight allowed, e.g. 2023 wOBA. Feature = a stat
   evaluated as of a cutoff using only what was knowable then, shaped as a model
   input (four clocks, `docs/FEATURE_STORE.md`). Gold holds stats; `feat.*` holds
   features. `gold.game_feature` is a legacy feature table and overlaps `feat.game`;
   it is a retirement candidate once `feat.*` reaches parity. Whether gold stats
   stay in Postgres or move to DuckDB/Parquet is decision 4.
12. **PROPOSED - Conform decomposition.** Set-based builds become small named `.sql`
   steps (run-twice tested); pure reusable logic may become `IMMUTABLE` SQL
   functions; procedural matching (game_pk backfill passes, market snapshot
   matching) stays in Python for now; SQLMesh judged in the spike against the
   ADR-297 upsert/stable-id requirement. Audit: keep `meta.query_stat_snapshot`
   (pg_stat_statements is in-memory, capped at 10,000, already at 9,765); add
   per-step `meta` run records; set `pg_stat_statements.track=all` and
   `track_functions=pl`; review `conform._timed` for redundancy.
13. **Hard-to-reverse choices (3, 4) get an ADR in `docs/DECISIONS.md` in the
   same change; operational cleanup gets a dated `changelog/` entry.**

## Risks / Trade-offs

- SQLMesh spike could reveal DuckDB-reads-Postgres performance limits; fall back
  to (a) or (c) and record why.
- Role drop could break an app using another database on the shared server;
  mitigate by checking grants in every database first and dropping only with
  owner approval.
- Parity matrix depends on a docs site that is partly stale/JS-rendered; use the
  GitHub model tree as ground truth.
- Scope creep: this change decides and cleans; implementation of parity metrics
  and new features is split into follow-up changes.

## Open Questions

- Does the owner want the public DuckLake-style distribution (as baseball.computer
  does) or keep Hugging Face Parquet? (affects task 3 spike scope)
- Which Postgres objects besides `gold.game_feature*` are safe to retire?
