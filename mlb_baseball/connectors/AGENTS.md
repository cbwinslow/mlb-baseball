# Connector subsystem DOX

## Purpose

This directory owns source-specific acquisition adapters. It is the first **file-documented DOX profile** in this repository: meaningful connector modules should have a same-directory `<module>.py.dox.md` sidecar that captures durable source/runtime contracts not obvious from code alone.

Read `../../AGENTS.md` and `../AGENTS.md` before this file.

## Ownership

Connectors own:

- acquiring source data from the authoritative/permitted endpoint or artifact;
- landing source-faithful raw data/artifacts;
- source-specific parsing and schema drift handling;
- bootstrap/update/backfill behavior;
- run tracking, retries, resumability, and idempotency;
- connector health checks;
- source-specific rights/profile constraints and known upstream quirks.

Connectors do **not** own canonical cross-source identities, research formulas, model features, or presentation logic. Those belong downstream.

## Local Contracts

- Use existing shared infrastructure (`manifest`, `load_dataframe`, `track_run`, health helpers, DB helpers, network helpers) rather than reimplementing it per source.
- Land/download artifacts before parsing when replayability matters. Record provenance/checksum/parser/schema information through existing manifest/run infrastructure.
- Raw tables are source-faithful. Do not silently normalize genuine source inconsistencies merely to simplify downstream queries.
- Each connector must declare or make clear whether data is snapshot, append, or scoped-replace and must have an explicit idempotency/conflict strategy.
- Bootstrap must be resumable at the natural source grain where practical; one failed season/file/page should not unnecessarily destroy already committed historical progress.
- Retries/backoff/rate-limit behavior must be bounded and visible. Never create accidental unbounded loops or aggressive concurrency against public sources.
- Preserve archive/path safety for downloaded archives.
- External SDK/client objects must not become the canonical internal schema. Adapt them into project-owned raw/core contracts.
- Source rights/license/profile rules are correctness constraints. Do not expose or redistribute data outside its permitted profile merely because it is technically available.
- Every connector should expose `bootstrap()`, `update()`, and `health_check()` when those concepts apply to the source. Deviations belong in the module sidecar.
- `health_check()` should use shared health primitives where possible and should detect freshness/coverage/last-run failures that a maintainer can act on.
- Tests that exercise PostgreSQL use the repository's isolated per-pytest-run database contract in `tests/AGENTS.md`; never assume the literal base database `mlb_test` is the database mutated by a test session.

## File-Documented Profile Contract

For each significant direct `*.py` connector module, create `<filename>.dox.md` when the module is actively maintained or contains nontrivial source/runtime knowledge.

A connector sidecar should include, when applicable:

1. **Purpose** — source/product represented and why it exists.
2. **Ownership** — raw tables/artifacts and public connector entry points.
3. **Source Contract** — authoritative URL/API, coverage, source grain, rights/profile reference, update cadence.
4. **Runtime Contracts** — bootstrap/update semantics, transaction/commit boundaries, retries, rate limits, replay/idempotency, schema drift behavior.
5. **Data Contracts** — tables, scope keys, source IDs, important null/quirk semantics.
6. **Dependencies** — shared helpers and external tools/libraries.
7. **Downstream Consumers** — conformance/gold/research surfaces that rely on it.
8. **Known Quirks / Decisions** — only verified durable source facts; link ADRs rather than copying them wholesale.
9. **Verification** — exact unit/integration/health checks tied to the module.
10. **Child DOX Index** — normally none for a leaf connector.

The source file owns implementation. The sidecar owns durable context about how to change that implementation safely. Update both in the same PR when a described contract changes.

Do not invent sidecar facts from filenames. Verify against source code, tests, migrations/table contracts, rights docs, and relevant ADRs before writing them.

## Work Guidance

- Prefer the official maintained client/library when it materially reduces fragile endpoint glue **and** a parity spike proves coverage, behavior, error handling, rights, and performance fit this project.
- Do not replace a proven connector simply for style consistency.
- Historical sources often contain genuine era-dependent sparsity. Missing measurement is not zero; preserve honest nullability.
- Favor explicit sequential ingestion when concurrency has not been proven safe or useful.
- When changing a source schema mapping, inspect downstream conformance and research consumers before merging.
- When adding a source, update `docs/DATA_SOURCES.md`, source-rights metadata, health/coverage surfaces, tests, and DOX together.

## Verification

For a behavior-changing connector edit, normally verify:

- parsing/helper unit tests;
- connector integration test against real PostgreSQL and mocked/captured network data;
- idempotency by executing the load twice and comparing the relevant rows/grain;
- CLI dispatch when the connector has user-facing CLI commands;
- `health_check()` behavior;
- lint/type checks.

Use real network calls only for a deliberate/manual source parity or smoke check; routine CI should remain deterministic.

## Reviewed Sidecar Coverage

Sidecars are added in source-reviewed batches, not generated mechanically merely to reach a file-count target. The current enforced baseline is listed by `scripts/check_dox.py` and includes:

- core/hub connectors: `mlb_api.py`, `retrosheet.py`;
- market sources: `kalshi.py`, `polymarket.py`;
- Baseball Savant: `statcast.py`, `statcast_leaderboard.py`;
- Retrosheet family: `retrosheet_event.py`, `retrosheet_box.py`, `retrosheet_gamelog.py`, `retrosheet_reference.py`, `retrosheet_roster.py`, `retrosheet_schedule.py`, `retrosheet_transaction.py`.

Next sidecar batches should prioritize actively maintained reference/research sources with distinct rights/coverage/runtime contracts (for example Lahman, Chadwick Register, Baseball-Reference, news/injury inputs) and any connector being materially changed. Small trivial adapters do not need a sidecar merely because a neighboring module has one.

When a sidecar is added to the reviewed baseline, add it to `scripts/check_dox.py` so it cannot disappear silently.

## Child DOX Index

No child directory DOX is required yet. If a connector such as MLB Stats API is later decomposed into a durable subpackage, that subpackage should receive its own `AGENTS.md` and index rather than accumulating another monolith here.