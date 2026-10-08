# 2026-10-08 — PostgreSQL 16 extension toolbox

- Installed via apt (PGDG): mobilitydb, similarity, roaringbitmap, pg-uuidv7, pg-ivm,
  plpgsql-check, pgtap, partman, repack, pg-stat-kcache, pg-qualstats,
  pg-wait-sampling, pg-hint-plan, pgaudit, orafce, hypopg.
- Added migration 0116, `scripts/pg_extensions_install.sh`, doctor check, ADR-302.
- Preload list set and PG16 restarted 2026-10-08; kcache, qualstats, pg_search enabled; pg_duckdb conflicts with timescaledb_toolkit.
