# 2026-10-08 — PostgreSQL 16 extension toolbox

- Installed via apt (PGDG): mobilitydb, similarity, roaringbitmap, pg-uuidv7, pg-ivm,
  plpgsql-check, pgtap, partman, repack, pg-stat-kcache, pg-qualstats,
  pg-wait-sampling, pg-hint-plan, pgaudit, orafce, hypopg.
- Added migration 0116, `scripts/pg_extensions_install.sh`, doctor check, ADR-302.
- shared_preload_libraries change (pg_stat_kcache, pg_qualstats) needs a restart of the
  shared PG16 cluster (mlb, govdata, promscale, langfuse); pending owner go-ahead.
