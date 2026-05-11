# 10 — PostgreSQL Extensions

SQL scripts in this directory install required PostgreSQL extensions.
They must run **first**, before any schema or table creation.

## Scripts (to be added in Phase 2)

| File | Purpose |
|---|---|
| `01_uuid_ossp.sql` | UUID generation functions |
| `02_pg_trgm.sql` | Trigram indexes for fuzzy text search |
| `03_btree_gin.sql` | GIN indexes for composite types |
| `04_pg_stat_statements.sql` | Query performance monitoring |

## Status

⚠️ **Pending** — tracked in [Phase 2 milestone](https://github.com/cbwinslow/mlb-baseball/milestones).
The database bootstraps via SQLAlchemy ORM (`baseball db init`) until these scripts are implemented.
