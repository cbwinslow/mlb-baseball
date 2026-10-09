## Why

Ingestion is done and working. Before ML and feature work starts, the owner wants
one clear direction: what each layer and tool is for, whether `core`/`gold`
contain what models need, which docs and database objects are stale, and how to
reach baseball.computer parity (and beat it) using published research as the
starting feature set. Today the work points several ways at once: Postgres
`gold.game_feature` (1.3 GB, legacy), a DuckDB `feat.*` store (feature-store-v1,
complete), an experimental SQLMesh-on-Postgres setup, ~10 leftover test-template
databases, and unused database roles. This change records the exploration
(2026-10-08), decides the direction, and owns the cleanup.

## What Changes

- Verify, rather than assume, the layer/tool split (Postgres = system of record
  for `raw`/`core`; DuckDB = features and analysis; Python = fitting/simulation;
  SQLMesh = open question, see `design.md`). Record the result as an ADR.
- Audit `core`/`gold` against `raw` using `mlb field-census` on `mlb_test`
  (read-only) and `information_schema`; list true gaps only.
- Build a baseball.computer parity matrix (tables/views/metrics they offer vs
  ours) from their public docs, without copying their SQL (CC BY-NC-SA).
- Turn `docs/research/SABERMETRIC_LITERATURE_INDEX.md` into a ranked
  "published features to implement" backlog with citations.
- Docs pass: fix or archive stale docs found while auditing; one owner per fact.
- Database hygiene (needs owner go-ahead per step): drop unused roles `baseball`,
  `letta`, `letta_user` after checking cross-database grants; keep `cbwinslow`
  and `mlb`; reap leftover `mlb_test_*_tmpl` databases; log in `changelog/`.
- Decide MLflow timing (current lean: defer until a baseline model exists).

No behavior change to ingestion, `conform`, or published data. **No code in this
change beyond audit scripts/docs;** implementation follows in separate changes.

## Capabilities

### New Capabilities
<!-- None: this is a decision/audit/cleanup change. Any resulting requirement
     gets its own change (e.g. a parity or feature-backlog change). -->

### Modified Capabilities
<!-- None. -->

## Impact

- Docs: `docs/DECISIONS.md` (new ADR), `docs/TABLE_CONTRACTS.md`,
  `docs/FEATURE_STORE.md`, `docs/research/`, possibly `openspec/project.md`
  (NOW/NEXT/LATER).
- Database (server-wide, not just `mlb`): role and leftover-test-DB cleanup.
  Production `mlb` (owned by role `mlb`) is read-only for the audit.
- Related changes: `feature-store-v1`, `metric-catalog`, `model-readiness-audit`,
  `stable-ids-incremental-conform`.
