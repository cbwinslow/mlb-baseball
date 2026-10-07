# Design

## Context

- `mlb coverage` already compares expectations with the database and prints the `mlb ingest` fix (`mlb_baseball/coverage/`). `mlb source-check` already sends HEAD requests for downloaded files. `mlb field-census` maps raw-to-gold fields. `mlb_baseball/nightly.py` runs the daily steps and now ends with `coverage --unexplained --fail-on-gap`.
- Connectors are idempotent and resumable; the ledger `meta.ingestion_item` records `loaded`, `unavailable`, `failed`. Retrosheet and FanGraphs loaders have schema-drift policies; other sources have none.
- MLB publishes no schema. The community OpenAPI file (190 paths, 490 schemas) is an unverified checklist (`full-source-ingestion` 0.3).
- `cli.py` is 4,166 lines with many subcommands, some unrelated to upkeep.

## Goals / Non-Goals

**Goals:** a verified inventory per source; a read-only drift check; a bounded self-repair step; one clear upkeep command surface with dry runs; an agent skill. Every item test-first, spec-first.

**Non-Goals:** new or paid sources; minor leagues and Negro League labelling (`full-source-ingestion`, `negro-league-scope`); a new orchestrator (Dagster, Kestra, Airflow); rewriting connectors; model or website work.

## Decisions

1. **Snapshots are small and local.** One sample response or file header per dataset, stored under `downloads/schema_snapshots/<source>/`, compared by field name and JSON type. Rejected: storing full responses (large, and `full-source-ingestion` owns saved responses).
2. **Drift check is separate from loading.** It never writes to `raw`. Findings go to a `meta` table and the nightly log. Rejected: failing connector loads on drift (hides the cause and blocks unrelated data).
3. **Safe list is explicit and in code.** A repair is safe only if it is listed, with its per-night cap. Default is report-only. Rejected: inferring safety from the command name.
4. **Reuse before adopting.** Evaluate `dlt` for schema inference and evolution against what `coverage` and the snapshot check already do, and write down why it is or is not adopted (project rule: established solutions first). Same for the community MLB MCP servers: lookup helpers only, never the loader, and none without a licence and rights check.
5. **Orchestrator stays the nightly script.** Two new steps (`schema-watch`, `repair`) join the existing sequence with the same retry and alert behaviour (ADR-016). Revisit an orchestrator only if the script becomes hard to manage, with evidence.
6. **Namespace index is generated.** A command index (name, flags, writes or read-only, cost) is generated from the argparse tree and checked in a test so docs cannot drift from the code.
7. **ADR.** Record the safe-repair and drift-check decisions in `docs/DECISIONS.md` (task 6.1).

## Risks / Trade-offs

- A source may rate-limit or block probes. Mitigation: one request per dataset, nightly, shared retry code, `unchecked` instead of failing.
- Auto-repair could hide a real fault. Mitigation: caps, logging, suspend after three failures, report-only default.
- Snapshot of a sample may miss fields that appear only in some seasons. Mitigation: sample one old and one new season per dataset where the year range matters; record the limit in the source page.
- Task 1.x touches many docs; keep to links, one owner per fact.
