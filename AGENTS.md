# AGENTS.md

## Purpose

This repository is the canonical home for the `baseball` project: a comprehensive baseball data, modeling, simulation, and prediction platform centered on historical and live ingestion, PostgreSQL-backed analytics, and agent-accessible prediction workflows.

All contributors — human and AI — must follow the rules in this document.

---

## Canonical namespace

- The only canonical Python package and CLI namespace is `baseball`.
- Do not introduce or revive alternate top-level namespaces such as `mlb_predict`, `mlbpredict`, or similar variants.
- If older code, docs, tests, or examples reference an old namespace, migrate them toward `baseball`.

Examples:
- Good: `baseball download retrosheet seasons`
- Bad: `mlb_predict download retrosheet seasons`

---

## Architectural principles

The project must be organized around clear subsystem boundaries.

Top-level responsibilities include:

- `bootstrap`
- `db`
- `download`
- `ingest`
- `bridge`
- `schedule`
- `live`
- `features`
- `models`
- `simulate`
- `predict`
- `kb`
- `qdrant`
- `agents`
- `monitor`
- `test`
- `docs`

Do not create new top-level command groups casually. Prefer improving existing boundaries before adding more nouns.

---

## Command ownership rules

### `download`
Owns retrieval of raw files and API payloads from external sources.

It should:
- Download raw source files
- Fetch API payloads
- Save source metadata and retrieval metadata

It should not:
- Insert normalized records into core tables
- Resolve cross-source identities
- Train models

### `ingest`
Owns loading downloaded source material into database raw and staging layers.

It should:
- Parse raw downloads
- Insert source-native records into raw/staging tables
- Track ingestion batches

It should not:
- Perform broad cross-source harmonization
- Train models
- Execute downstream prediction logic

### `bridge`
Owns cross-source identity and relationship resolution.

It should:
- Map MLBAM, Retrosheet, Lahman, and other source IDs to canonical IDs
- Maintain crosswalk tables
- Resolve team, player, park, and game identity conflicts

It should not:
- Download source data
- Retrain models
- Replace ingestion logic

### `db`
Owns schema bootstrap, validation, views, mviews, metadata, and maintenance.

It should:
- Bootstrap SQL layers
- Validate schema and metadata state
- Refresh materialized views
- Report object status

It should not:
- Fetch source data
- Replace source-specific ingestion workflows

### `schedule`
Owns schedule synchronization and UTC scheduling plans.

It should:
- Sync schedules from authoritative sources
- Normalize times to UTC
- Produce polling/cron plans

It should not:
- Poll live pitch-by-pitch endpoints directly

### `live`
Owns live polling, incremental ingestion, reconciliation, and deduplication.

It should:
- Poll live endpoints during games
- Ingest deltas
- Reconcile game state
- Deduplicate events

It should not:
- Perform bulk historical loads

### `features`
Owns feature derivation and feature-store refreshes.

### `models`
Owns model training, evaluation, registration, and comparison.

### `simulate`
Owns scenario engines such as Markov and Monte Carlo simulations.

### `predict`
Owns inference using registered models and feature pipelines.

It should not:
- Rebuild full training pipelines unless explicitly requested

### `kb`
Owns the project knowledge base, including research documents, notes, and methodology references.

### `qdrant`
Owns vector indexing, embedding workflows, and semantic retrieval.

### `agents`
Owns agent tool wiring for LangChain, LlamaIndex, MCP, and related orchestration layers.

### `monitor`
Owns health checks, freshness checks, anomaly checks, lag checks, and operational reporting.

### `test`
Owns repository test entrypoints and validation orchestration.

### `docs`
Owns generated and curated documentation artifacts.

---

## SQL policy

- Do not execute raw ad hoc SQL strings from Python application logic.
- SQL must live in tracked `.sql` files under the repository SQL directory structure.
- Python may orchestrate SQL execution, pass parameters, manage transactions, and validate outputs, but SQL definitions themselves belong in SQL files.
- Database objects such as schemas, tables, views, materialized views, functions, triggers, validations, indexes, and seed metadata should be defined through versioned SQL scripts.

Preferred pattern:
- `sql/10_extensions/...`
- `sql/20_schemas/...`
- `sql/30_tables_raw/...`
- `sql/40_tables_staging/...`
- `sql/50_tables_core/...`
- `sql/60_tables_analytics/...`
- `sql/70_constraints_indexes/...`
- `sql/80_views_mviews/...`
- `sql/90_functions_triggers/...`
- `sql/100_validation/...`
- `sql/110_monitoring/...`
- `sql/120_metadata/...`

---

## Source adapter policy

Every first-class data source should have a stable adapter boundary under `baseball.sources`.

Examples:
- `baseball.sources.retrosheet`
- `baseball.sources.mlbstatsapi`
- `baseball.sources.baseballsavant`
- `baseball.sources.fangraphs`
- `baseball.sources.lahman`
- `baseball.sources.baseballreference`
- `baseball.sources.odds.draftkings`
- `baseball.sources.odds.polymarket`

Implementation details behind an adapter may vary:
- direct HTTP/API requests
- file downloads
- third-party packages such as `pybaseball`
- local parsers
- source-specific normalization helpers

The rest of the application must depend on the stable adapter interface, not on the implementation detail.

Do not design the architecture around `pybaseball` or any other third-party package. Those packages may be used as helpers, not as the core boundary.

---

## Package layout expectations

The repository should converge toward a layout like:

```text
baseball/
  cli/
  core/
  db/
  services/
  sources/
  normalize/
  bridge/
  live/
  scheduling/
  features/
  models/
  simulate/
  predict/
  kb/
  embeddings/
  agents/
  monitoring/
  testing/

sql/
docs/
tests/
```

The CLI and any future MCP layer should call shared service code rather than duplicating business logic.

---

## Documentation requirements

Any meaningful new subsystem should include documentation.

Minimum expectations:
- architecture notes for new subsystems
- CLI usage examples for new command groups
- data-flow explanation for source adapters
- schema or bootstrap notes for database changes
- testing notes for non-trivial workflows

Prefer Markdown in `docs/`.

---

## Testing requirements

New work should include tests appropriate to its scope.

Expected test types include:
- unit tests
- CLI tests
- integration tests
- SQL/bootstrap validation tests
- source adapter contract tests
- regression tests for prediction logic
- live replay tests where applicable

Do not merge major architectural work without tests.

---

## Rules for AI coding agents

AI agents working in this repository must:

- use `baseball` as the canonical namespace
- avoid introducing alternate command trees
- keep SQL in SQL files, not embedded Python strings
- preserve clear separation between `download`, `ingest`, `bridge`, `db`, `live`, `models`, and `predict`
- prefer additive, reviewable changes over broad destructive rewrites
- update docs when adding or changing architecture
- add or update tests alongside code changes
- avoid hidden side effects and magic behavior
- keep code explicit, typed where practical, and operationally observable

AI agents must not:
- create ad hoc parallel architectures
- bury business logic in notebooks or one-off scripts
- add raw SQL blobs into Python modules
- silently rename canonical commands
- assume a source library fully replaces source-specific adapters

---

## First implementation priorities

The preferred early build order is:

1. Project packaging baseline (`pyproject.toml`, package skeleton, CLI entrypoint)
2. Canonical `baseball` CLI root
3. Database bootstrap framework over tracked SQL files
4. Core source adapters:
   - Retrosheet
   - MLB Stats API
   - Lahman
   - Baseball Savant
5. Download / ingest / bridge separation
6. Live schedule + polling bootstrap
7. Feature store and model registry
8. Prediction and simulation interfaces
9. Knowledge base, embeddings, and agent tooling

---

## Decision defaults

Unless explicitly overridden:

- Python version target: 3.12
- CLI framework: Typer
- Postgres driver: psycopg
- Lint/format baseline: Ruff
- Type checking baseline: Pyright
- Test framework: pytest
- Docs stack: Markdown first, with MkDocs Material acceptable
- Vector store: Qdrant
- Database target: PostgreSQL 16

---

## Change management

When making structural changes:

1. Update the relevant docs first or alongside the code.
2. Keep command names stable unless there is a strong reason to change them.
3. Prefer migration paths over abrupt breakage.
4. Keep old names as temporary shims only when necessary.
5. Remove deprecated paths once the canonical path is in place and documented.

---

## Summary rule

If a proposed change makes the project less canonical, less reviewable, less SQL-driven, less testable, or less aligned with the `baseball` namespace, do not do it.