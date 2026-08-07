# Plan 02 — Named SQL, conformance decomposition, and ingestion hardening

## Objective

Replace unreadable embedded transformation SQL with tested, lineage-aware named
objects while preserving the working connector and identity-resolution strengths.

## Work packages

### 02A — SQL ownership inventory

Catalog every SQL statement in Python by owner, grain, dependencies, mutation,
parameters, and procedural/set-based nature. Classify it as migration DDL,
SQLMesh model/audit/test, named operational `.sql` resource, or justified small
inline statement. Identify duplicated formulas and establish canonical owners.

### 02B — SQLMesh production foundation

Promote the existing spike into a pinned, documented SQLMesh project. Establish
dev/prod environments, external models, naming, state storage, plans, audits,
unit tests, backfills/restatements, CI commands, and rollback. Tie out venue,
park, and wOBA models exactly before adding new models. Do not add dbt.

### 02C — Decompose conformance

Split Python orchestration, identity, games, events, markets, and query loading.
Move stable set-based pieces into SQLMesh incrementally, with old/new full-table
and sampled tie-outs. Retain multi-pass/order-dependent identity logic in Python.
Delete old embedded SQL only after parity and performance gates pass.

### 02D — Harden connectors

Add atomic downloads, content/provenance manifests, archive safety, schema
fingerprints, bounded retry/rate behavior, advisory locks, explicit conflict keys,
partial-failure semantics, and drift alerts. Build shared classes only where
three real connectors demonstrate the same lifecycle; keep source parsing
source-specific. Evaluate dlt only through a new-source spike, not a rewrite.

### 02E — Table contract cleanup

Document grain/key/time/lineage/update contracts. Keep raw/core/gold/meta names.
Prefer canonical facts plus narrow `gold` statistic/feature families over wide
sparse tables. Add constraints and indexes from measured queries. Introduce
`serve` only in Plan 05. Rename misleading metrics (for example FIP labeled ERA)
through explicit migrations and compatibility periods, not surprise breakage.

### 02F — ClickHouse decision benchmark

Benchmark representative pitch scans, rolling features, experiment extracts, and
site queries after PostgreSQL/SQLMesh optimization. Record data size, concurrency,
latency, cost, replication complexity, and correctness. Adopt a ClickHouse
analytical replica only if a stated SLO materially fails and the benefit exceeds
operational cost; never replace PostgreSQL by enthusiasm alone.

### 02G — Release and package integrity

Make the reusable library work from an installed wheel, not only a source
checkout: package migrations and named SQL resources, verify clean-install
migration/CLI behavior, and split heavyweight modeling dependencies into
explicit extras where feasible. Keep command modes semantically accurate
(`features`, `predict`, migration) so the run ledger is an operational record,
not a legacy naming artifact.

## Acceptance gate

- No large new business SQL is embedded in Python; extracted formulas have one
  canonical definition and dependency lineage.
- SQLMesh plan/audit/test/restatement workflows are reproducible from docs.
- Refactored outputs tie out exactly or have reviewed, explained differences.
- Connector reruns, failures, overlap, and schema drift have real Postgres tests.
- A recorded ClickHouse decision contains benchmarks, even if the decision is no.
