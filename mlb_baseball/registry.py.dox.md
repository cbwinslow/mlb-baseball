# `registry.py` DOX

## Purpose

Own the explicit, importable registry of supported ingestion connectors. This is the single shared answer to "which connectors exist?" for CLI orchestration, health/doctor checks, and the supported programmatic ingestion API.

## Ownership

- Imports the supported connector modules.
- Exposes `CONNECTORS`, mapping stable CLI/API source names to connector modules.

This module deliberately exists outside `cli.py` so non-CLI consumers such as `doctor.py` and `public.py` can use the same registry without importing the giant CLI module or creating circular dependencies.

## Contract

Each registered connector should satisfy the repository connector contract expected by its consumers:

- `bootstrap()`
- `update()`
- `health_check()`

Optional capabilities such as historical market `backfill_history()` are discovered explicitly by callers and are not part of the universal minimum contract.

The registry is intentionally explicit. Do not replace it with filesystem magic/entry-point discovery unless a measured extensibility requirement appears that the explicit mapping cannot serve.

## Naming

Registry keys are user-facing source identifiers used by CLI/API/profile/health code. Changing a key is therefore a compatibility change, not a private refactor.

When adding/renaming/removing a key, review:

- CLI `mlb ingest <source>` behavior and tests;
- source-profile/rights configuration;
- `doctor` / health checks;
- public API `ingest_source()`;
- docs/data-source catalog/examples;
- connector-group concurrency mapping in `cli.py` when the source shares an upstream host with another connector.

## Dependency Direction

- Connector modules may depend on shared DB/load/net/health infrastructure.
- `registry.py` should remain a thin composition point and must not contain connector behavior.
- Shared modules should not import the registry unless they genuinely need "all connectors"; avoid creating a central import cycle.

## Work Guidance

- Add a connector here only after the connector's source/rights/health/test contract exists.
- Do not register prototypes merely so they become discoverable.
- Keep ordering stable where user-facing orchestration/output relies on it; Python dict insertion order makes mapping order observable.
- For a new connector, classify its external upstream host in the CLI concurrency groups based on actual network calls rather than the module name.

## Verification

For registry changes:

- registry/CLI dispatch tests;
- doctor health enumeration tests;
- source-profile gating tests;
- `public.ingest_source()` unknown/known-source tests;
- connector contract tests for the newly registered module.

## Child DOX Index

No child DOX files.
