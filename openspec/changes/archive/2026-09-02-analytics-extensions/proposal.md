# Change: analytics-extensions

## Why

Rebuilt from the abandoned `postgres-analytics-extensions` branch (stale:
its migration was numbered 0066 — now taken — and its `AGENTS.md` edits
predate the restructure). The core idea is worth keeping: make a few
contrib extensions **available** so the fuzzy-name-crosswalk and
research-query work that ADR-279 flagged as "gated for later" isn't
blocked on a schema change when it starts.

## What changes

- **New migration `0099_analytics_extensions.sql`** — `CREATE EXTENSION`
  for `pg_trgm`, `unaccent`, `btree_gist`, `tablefunc`. No indexes, no
  table changes — indexes ship with the query that needs them.
- **`pgvector` is deliberately NOT enabled** — ADR-279 gates it on a named
  similarity-search consumer; add `CREATE EXTENSION vector` in that
  consumer's migration.
- **`mlb doctor`** gains an `analytics extensions` check (`_analytics_extensions_enabled`).
- **Tests:** `tests/integration/test_analytics_extensions.py` (functional
  check per extension) + a `test_doctor.py` case.
- **ADR-280** records the decision.

Dropped from the old branch: the 4 trigram GIN indexes (YAGNI — add with
the crosswalk query), the `vector` extension, and the stale root-doc edits.

## Impact

- One migration (`CREATE EXTENSION IF NOT EXISTS` — safe, idempotent,
  instant). The Postgres image already ships the contrib package.
- `mlb doctor` output gains one line.
- No new Python dependency. No behavior change to any pipeline.
- Prod: applied on the next `mlb migrate` (owner-run).
