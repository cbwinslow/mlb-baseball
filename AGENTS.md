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

## GitHub workflow

All development follows a standardized GitHub workflow to ensure consistency, quality, and traceability.

### Branching strategy
- **`main`**: Production-ready code only. Always deployable.
- **`develop`**: Integration branch for features. Contains latest delivered development changes.
- **`feature/*`**: New features (branch off `develop`, merge back to `develop`)
- **`bugfix/*`**: Bug fixes (branch off `develop`, merge to `develop` and `main`)
- **`release/*`**: Release preparation (branch off `develop`, merge to `main` and `develop`)
- **`hotfix/*`**: Critical production fixes (branch off `main`, merge to `main` and `develop`)
- **`docs/*`**: Documentation changes

### Tagging strategy
- **Version Tags**: Semantic versioning (`v<MAJOR>.<MINOR>.<PATCH>`) on `main` branch after releases
- **Milestone Tags**: Optional tags for significant milestones (e.g., `milestone-raw-ingestion-complete`)
- **Format**: `v<MAJOR>.<MINOR>.<PATCH>` following SemVer

### Issue management
- All work starts as a GitHub issue
- Issues use labels for type (`type: bug`, `type: feature`, etc.), priority (`priority: high/medium/low`), and area (`area: download`, `area: ingest`, etc.)
- Issues are prioritized and added to milestones
- Work begins only when issue is assigned and in progress
- Progress tracked through issue updates, PR links, and checklists
- Issue closed only when associated PR is merged and acceptance criteria met

### Pull request process
1. Create branch from `develop` for features, `main` for hotfixes
2. Naming: `feature/<issue-number>-short-description` or `bugfix/<issue-number>-short-description`
3. Keep PRs small and focused (ideally <400 lines changed)
4. Description must include:
   - Summary of changes
   - Related issue number (Closes #xxx or Fixes #xxx)
   - Testing performed
   - Screenshots if UI changes
   - Any breaking changes or migration notes
5. Checks:
   - All tests must pass
   - Code coverage thresholds met
   - Linting/formatting passes
   - Security scans pass
6. Review:
   - Minimum 1 approving review (2 for complex changes)
   - Address all review comments
   - Use suggested changes feature when appropriate
7. Merging:
   - Use squash and merge for feature branches (keeps history clean)
   - Use merge commit for releases if desired
   - Delete branch after merge

### CI/CD pipeline
- GitHub Actions workflows in `.github/workflows/`
- `ci.yml`: Runs on push and PR to `main` and `develop` (linting, type checking, testing, coverage)
- `release.yml`: Triggered on tag push to `main` (build, test, create GitHub release, publish to PyPI)
- Branch protection rules for `main` and `develop`:
  - Require pull request reviews before merging
  - Require status checks to pass before merging
  - Require linear history
  - Include administrators
  - Require conversation resolution before merging

### Documentation standards
- README.md: Clear project overview, installation, quick start, architecture, API examples, contributing guidelines
- CONTRIBUTING.md: How to report bugs, suggest features, development setup, coding standards, PR process, license
- CHANGELOG.md: Keep updated with notable changes using Keep a Changelog format
- Inline documentation: Follow PEP 257 for docstrings, use type hints where practical, comment complex logic

### Code review guidelines
Reviewers should examine code for:
1. Correctness: Does the code work as intended?
2. Clarity: Is the code easy to understand?
3. Maintainability: Is the code easy to modify and extend?
4. Patterns: Does it follow established project patterns?
5. Tests: Are there adequate tests that pass?
6. Documentation: Is documentation updated if needed?
7. Performance: Are there obvious performance issues?
8. Security: Are there security vulnerabilities?

Review process:
1. Reviewer examines code against guidelines
2. Leaves comments and suggestions
3. Author addresses all feedback
4. Reviewer approves when satisfied
5. Maintainer merges after approval and passing checks

### Release process
Pre-release checklist:
1. All issues in milestone are closed
2. Main branch is stable and tested
3. Documentation is up to date
4. CHANGELOG.md updated
5. Version number determined

Release steps:
1. Create release branch: `git checkout -b release/vX.Y.Z develop`
2. Update version numbers in code (if applicable)
3. Update CHANGELOG.md with release notes
4. Commit changes: `git commit -m "chore: prepare release vX.Y.Z"`
5. Push branch and create PR to main
6. Get required approvals
7. Merge PR to main (creates merge commit)
8. Tag release: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
9. Push tag: `git push origin vX.Y.Z`
10. Merge main back to develop: `git checkout develop && git merge main`
11. Delete release branch
12. GitHub Actions automatically creates GitHub release

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