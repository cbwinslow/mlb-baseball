# Docs map

31 files, no obvious reading order until now. This page says what each one
is *for*, so you can go straight to the right one instead of grepping.

Some entries below are **dated snapshots** — a one-time audit or decision
record, not a living doc that gets updated as the project changes. Treat
their content as true as of their stated date, not as current state; check
`plans/PROGRESS.md` for what's actually happened since.

## Start here

- [`NORTH_STAR.md`](NORTH_STAR.md) — the vision, the three build phases, the
  budget rule ($0/month), and what makes this project different from
  baseball.computer. Read this first.
- [`ROADMAP.md`](ROADMAP.md) — what's actually built vs. planned, phase by
  phase. The living answer to "where are we."
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the raw/core/gold layered schema,
  why it's shaped that way.

## Data: what we have, where it's from, what you can do with it

- [`DATA_SOURCES.md`](DATA_SOURCES.md) — every data source in scope, cost,
  access method. If a source isn't listed here, it's not in scope yet.
- [`SOURCE_RIGHTS.md`](SOURCE_RIGHTS.md) — licensing/rights per source. Check
  this before redistributing or publishing anything derived from the data.
- [`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) — source-attributed research
  register: what a source says, what we verified locally, what decision it
  supports.
- [`TABLE_CONTRACTS.md`](TABLE_CONTRACTS.md) — for each table: its grain,
  identity, event/cutoff time, lineage. Read before writing a new query
  against a table you haven't used before.
- [`GAME_INSTANCE_IDENTITY.md`](GAME_INSTANCE_IDENTITY.md) — how a single
  MLB game is identified across sources (doubleheaders, `game_pk`, etc.) —
  the single most load-bearing identity decision in the whole schema.
- [`RAW_CORE_GOLD_FIELD_CENSUS.md`](RAW_CORE_GOLD_FIELD_CENSUS.md) — field-
  level lineage from raw through core to gold.

## Modeling and features

- [`RESEARCH.md`](RESEARCH.md) — techniques and models under consideration,
  the leakage failure modes this domain is prone to, and the honest accuracy
  ceiling.
- [`FEATURE_REGISTRY.md`](FEATURE_REGISTRY.md) — the registered feature
  families; a new one must be registered here, not silently bolted onto
  `gold.game_feature`.
- [`FEATURE_ADMISSION_QUEUE.md`](FEATURE_ADMISSION_QUEUE.md) — features
  proposed but not yet admitted, and why.
- [`EXPERIMENT_RUNBOOK.md`](EXPERIMENT_RUNBOOK.md) — how to actually run the
  experiment lab (snapshot/run/compare), what each model family expects.

## Running things (operational runbooks)

- [`BOOTSTRAP_RUNBOOK.md`](BOOTSTRAP_RUNBOOK.md) — first-time setup of a new
  database from scratch.
- [`AUDIT_RUNBOOK.md`](AUDIT_RUNBOOK.md) — how to run and interpret
  `mlb audit`/`mlb doctor`.
- [`FEATURE_BUILD_RUNBOOK.md`](FEATURE_BUILD_RUNBOOK.md) — how the
  production feature build actually runs.
- [`RESEARCH_QUERY_RUNBOOK.md`](RESEARCH_QUERY_RUNBOOK.md) — recipes for
  common read-only research queries.
- [`DBA_LEAST_PRIVILEGE_RUNBOOK.md`](DBA_LEAST_PRIVILEGE_RUNBOOK.md) —
  database role/permission setup.
- [`CONFORMANCE_REHEARSAL.md`](CONFORMANCE_REHEARSAL.md) — **dated
  snapshot.** A rehearsal run of the core conformance step against a sample.
- [`PRODUCTION_CONVERGENCE.md`](PRODUCTION_CONVERGENCE.md) — **dated
  snapshot, 2026-08-06.** A read-only audit of production state at that
  time.
- [`INGESTION_BULK_LOAD_ASSESSMENT.md`](INGESTION_BULK_LOAD_ASSESSMENT.md) —
  **dated decision record.** Why the bulk-load pattern for MLB API analytics
  data is shaped the way it is.

## Decisions and why things are the way they are

- [`DECISIONS.md`](DECISIONS.md) — **the ADR log.** Every non-trivial
  decision, newest first. 1,594 lines — search it, don't read it front to
  back. If you're about to re-litigate a choice, check here first.
- [`CLICKHOUSE_DECISION.md`](CLICKHOUSE_DECISION.md) — **dated decision
  record, 2026-08-06.** Why this project stayed on PostgreSQL instead of
  adding ClickHouse, with the real benchmark numbers and the specific
  conditions that would justify revisiting it.
- [`SQLMESH_OPERATIONS.md`](SQLMESH_OPERATIONS.md) — current state of the
  SQLMesh spike (gated, disposable practice database, never promoted to
  production).
- [`POLICY_REVIEW_2026-08.md`](POLICY_REVIEW_2026-08.md) — **dated review.**
  A challenge-and-response on some of this project's own conventions (e.g.
  SQL-as-Python-strings).
- [`PLAN_02_ACCEPTANCE.md`](PLAN_02_ACCEPTANCE.md) — **dated evidence
  record, last audited 2026-08-06.** Not a cutover approval.
- [`PROJECT_REVIEW.md`](PROJECT_REVIEW.md) — a large end-to-end review of
  the research/prediction/website plan, including the detailed comparison
  against baseball.computer and oddstrader.

## Working with this repo

- [`GITHUB_GOVERNANCE_RUNBOOK.md`](GITHUB_GOVERNANCE_RUNBOOK.md) — how PRs,
  issues, and access work (fork-based contributions welcome, no direct
  write access granted).
- [`SQL_OWNERSHIP.md`](SQL_OWNERSHIP.md) — where new SQL is allowed to live,
  so a second embedded-SQL-in-Python pile doesn't grow alongside the
  reviewed `mlb_baseball/sql/*.sql` files.

## Reference

- [`TOOLS.md`](TOOLS.md) — libraries and tools in use, and why.
- [`PUBLIC_API.md`](PUBLIC_API.md) — the small, deliberate set of Python
  imports this project actually supports for outside use.

## Outside `docs/`

- [`../CLAUDE.md`](../CLAUDE.md) / [`../AGENTS.md`](../AGENTS.md) — operating
  rules for anyone (human or AI) working in this repo. Read before making
  changes, not after.
- [`../plans/PROGRESS.md`](../plans/PROGRESS.md) — the evidence log of what
  was actually done, in order. The living record `ROADMAP.md` and this map
  don't replace.
- [`../plans/*.md`](../plans/) — the active plan sequence (numbered), the
  actual work queue.
