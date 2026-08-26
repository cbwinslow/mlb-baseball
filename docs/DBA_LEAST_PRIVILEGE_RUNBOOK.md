# Least-privilege DBA runbook

This is a reviewable, reversible runbook only. Do **not** execute it against
production without the owner's explicit approval, an approved backup/rollback
window, and environment-specific role names.

## Intended roles

| Role | Intended capability | Explicitly excluded |
|---|---|---|
| `mlb_owner` | owns schemas and controlled migrations | routine application login |
| `mlb_ingest` | writes `raw`, selected `meta` run records | `core`, `gold`, `serve` DDL; serving credentials |
| `mlb_transform` | reads `raw`, writes `core`, `gold`, transform metadata | raw DDL; public serving login |
| `mlb_serve` | reads approved `serve` views/tables only | `raw`, `core`, `gold`, `meta`; writes; schema creation |

## Preflight and rollback evidence

1. Capture `\du`, `\dn+`, `\dp`, `\dp+ raw.*`, `\dp+ core.*`, `\dp+ gold.*`,
   and connection/network/TLS settings in the change record.
2. Confirm Astro's database URL resolves to the future `mlb_serve` role, not an
   owner or transform role. Keep Astro restricted to the `serve` schema.
3. Test role capabilities in a staging database with `SET ROLE`; record both
   allowed and denied queries. No production data mutation is required.
4. Store credentials in the deployment secret manager; local `.env` files must
   be owner-readable only (`chmod 600 .env`) and never be committed.

## Proposed SQL (review and parameterize first)

```sql
-- Run as the database owner after substituting approved secret-management
-- provisioning. Password creation/rotation is deliberately outside this file.
CREATE ROLE mlb_ingest NOINHERIT LOGIN;
CREATE ROLE mlb_transform NOINHERIT LOGIN;
CREATE ROLE mlb_serve NOINHERIT LOGIN;

REVOKE ALL ON SCHEMA raw, core, gold, meta, serve FROM PUBLIC;
GRANT USAGE ON SCHEMA raw, meta TO mlb_ingest;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA raw TO mlb_ingest;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA meta TO mlb_ingest;

GRANT USAGE ON SCHEMA raw, core, gold, meta TO mlb_transform;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO mlb_transform;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO mlb_transform;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA gold TO mlb_transform;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA meta TO mlb_transform;

GRANT USAGE ON SCHEMA serve TO mlb_serve;
GRANT SELECT ON ALL TABLES IN SCHEMA serve TO mlb_serve;
ALTER DEFAULT PRIVILEGES FOR ROLE mlb_owner IN SCHEMA serve
  GRANT SELECT ON TABLES TO mlb_serve;
```

Schema `serve` and its read-only marts already exist in production (migration
`0078_serve_layer_views.sql` onward, ADR-102) — the `serve` schema build-out
happened ahead of this runbook's own "Plan 05" framing. What is still
outstanding is the `mlb_serve` role itself: production has not yet had any of
the roles above created or its `pg_hba.conf`/grant model changed. The proposed
roles require a migration-specific grant policy before migrations are run
under anything other than `mlb_owner`.

## Dedicated-test evidence

`tests/integration/test_least_privilege.py` creates a uniquely named,
NOLOGIN serving role plus a disposable serve schema/table/view in
`mlb_test`. It proves via `SET ROLE` that the serving role can select its
approved object but cannot read or create objects in `raw`, `core`, `gold`, or
`meta`, create schemas, or write/drop its serve object. The fixture drops the
temporary schema and role in teardown. This is an executable contract for the
grant shape; it does not apply any role, network, TLS, or credential change to
production.

## Network and transport checklist

- Bind Postgres to private interfaces only; limit `pg_hba.conf` to the
  application host/identity and require TLS for any non-local connection.
- Enforce `sslmode=verify-full` for remote application URLs after certificates
  and CA distribution are tested.
- Test new rules from a separate session before closing the owner session.
- Keep a documented rollback path: restore the prior `pg_hba.conf`, reload
  Postgres, revoke new grants, and invalidate only credentials created for this
  rollout.
