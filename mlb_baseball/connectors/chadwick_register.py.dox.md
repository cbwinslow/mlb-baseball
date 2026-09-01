# `chadwick_register.py` DOX

## Purpose

Own ingestion of the Chadwick Bureau Register: the project's broad source-ID crosswalk and person/name/link/country reference snapshot used to reconcile baseball identities across Retrosheet, MLB, Baseball-Reference, and other sources.

## Ownership

Implementation: `chadwick_register.py`.

Primary raw outputs:

- `raw.register_people`
- `raw.register_names`
- `raw.register_links`
- `raw.register_countries`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

- Source: Chadwick Bureau Register CSVs under `https://raw.githubusercontent.com/chadwickbureau/register/master/data`.
- People records are sharded across 16 hex-named CSV files (`people-0.csv` … `people-f.csv`).
- Names, links, and countries are single CSV files.
- This connector treats the upstream repository state as a **point-in-time reference snapshot**, not an event stream.
- Repository source-rights/profile metadata remains authoritative for permitted use/redistribution.

## Snapshot / Transaction Contract

`bootstrap()` and `update()` intentionally perform the same operation:

1. truncate all four register raw tables;
2. load every people shard;
3. load names, links, and countries;
4. commit the coherent snapshot as one transaction.

This all-or-nothing behavior is important. A partially refreshed identity crosswalk must not become visible merely because one shard/network call failed after earlier tables were truncated/loaded.

Do not convert this into per-shard committed incremental state unless a versioned/source-snapshot design preserves coherent identity consistency.

## Raw Schema / COPY Contract

- The source CSV header is used as the COPY column list because the raw register tables intentionally mirror upstream column names/order.
- That header is trusted only because the connector controls the fixed upstream filenames/URL and the corresponding raw schema is project-migrated; this is not a generic API for arbitrary user-supplied table/header names.
- If the upstream Register adds/removes/renames columns, update/verify migrations and downstream identity code before accepting the new schema.
- Do not silently discard a new upstream identity column simply to keep an old load working.

## Identity Contract

- `raw.register_people` is identity evidence, not the canonical project `core.player` table.
- Cross-source IDs should be preserved exactly enough for conformance to reason about them; do not normalize one source's ID into another source's namespace inside this connector.
- Name/link/country products are supporting reference evidence and should remain source-faithful.
- Missing source IDs are not proof that two records are different; identity resolution belongs downstream and may combine multiple evidence sources.

## Network / Failure Contract

- Every source fetch uses a finite HTTP timeout.
- Current implementation does not use the generic DataFrame loader; it streams CSV text directly into PostgreSQL COPY for a compact, source-shaped snapshot path.
- Network/schema/COPY failure before commit should roll back the refresh rather than leave mixed old/new register state.
- If this connector later adopts shared retry/backoff, preserve whole-snapshot transaction semantics.

## Dependencies

- `requests`
- psycopg COPY
- run tracking, DB, health helpers
- database migrations defining the raw register schema

## Downstream Consumers

- `conform.py` treats `raw.register_people` as a hard prerequisite for canonical player construction.
- Player/source-ID crosswalks throughout research/conformance depend on Register identity columns.
- Other source connectors should not independently reinvent identity crosswalks already represented here.

## Known Quirks / Decisions

- People are split across sixteen upstream shards; all shards together are one logical snapshot.
- Bootstrap/update identity is intentional because the source is a snapshot.
- The source CSV header drives COPY column selection, so migration/schema drift must be coordinated rather than hidden.

## Work Guidance

- Before changing source URL/files, inspect the actual Chadwick Register repository layout.
- Keep raw IDs/source names source-faithful.
- Preserve coherent all-table snapshot semantics.
- Do not build a generic plugin/identity abstraction in this connector; canonical reconciliation belongs in conformance/identity layers.
- If using a pinned commit/release later for reproducibility, document how freshness updates are intentionally performed.

## Verification

For changes, verify:

- all 16 people shards are enumerated and loaded;
- CSV header extraction preserves order/names and matches migrated raw columns;
- a mid-refresh failure rolls back rather than publishing partial state;
- repeated bootstrap/update produces a stable full snapshot without duplicates;
- `raw.register_people` remains usable by canonical player conformance;
- health detects empty/missing identity data and records connector run status.

## Child DOX Index

No child DOX files. This is a leaf connector contract.