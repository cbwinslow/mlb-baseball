# Package SQL Resources DOX

## Purpose

Own named SQL resources executed by Python for operational/database interactions
that are not DDL migrations and are not yet/promotably SQLMesh models.

## Ownership

- `*.sql` files here are package-owned SQL statements loaded through the package
  SQL helper (`read_sql()` and related callers).
- DDL belongs in `migrations/`.
- Promoted deterministic relational models belong in `transforms/`/SQLMesh.
- Large mutating SQL should not be newly embedded inside Python modules.

## Local Contracts

- Follow `docs/SQL_OWNERSHIP.md` and `docs/SQL_AND_TRANSFORMS_GUIDE.md`.
- Files may use psycopg named placeholders such as `%(name)s`; keep placeholder
  names stable with their Python callers and compatible with the SQLFluff
  placeholder templater configured in `.sqlfluff`.
- Parameterize values. Never interpolate untrusted identifiers/values into SQL
  strings without explicit safe identifier handling.
- Every statement must be understandable in terms of input relations, output or
  mutation target, grain/key assumptions, point-in-time behavior, and transaction
  expectations.
- Do not duplicate a formula already canonically owned by another SQL resource,
  SQLMesh model, or pure stats module. If parity implementations are necessary,
  add tests that prove equality on representative fixtures.
- Mutating statements must be idempotent or have clearly documented replacement/
  append semantics.
- Read-only research queries should prefer stable `gold`/documented relations over
  assembling source-specific raw data ad hoc.
- Rights/profile checks belong in the caller/domain contract where appropriate;
  SQL file presence does not imply a relation may be redistributed.

## Work Guidance

When moving SQL out of Python:

1. preserve transaction and lock semantics exactly;
2. keep the Python wrapper small and typed;
3. add/retain a focused test that catches placeholder/caller mismatches;
4. run SQLFluff and the SQL ownership linter;
5. update SQL guide/DOX if the resource becomes a durable new capability.

If a statement is deterministic set-based research logic with stable inputs and a
clear materialization grain, consider whether it belongs in SQLMesh after parity
tie-out instead of growing this directory indefinitely.

## Verification

```bash
uv run sqlfluff lint mlb_baseball/sql
uv run python scripts/lint_sql_ownership.py
uv run pytest tests/integration -q
```

Run the focused caller test whenever a SQL resource or placeholder changes.
Compilation/lint success is not enough for mutating statements; verify resulting
rows/keys in PostgreSQL.

## Child DOX Index

No child DOX files. Individual SQL sidecars are not required by default because
well-named SQL plus caller/tests generally provides sufficient local context. Add
a sidecar only for unusually complex/load-bearing resources that cannot be made
self-explanatory otherwise.
