#!/usr/bin/env bash
# Installs the optional PostgreSQL 16 extension packages (ADR-302) and adds the
# two that need it to shared_preload_libraries. Safe to re-run.
#
# Side effects: apt-get install (needs sudo) and, with --preload, an ALTER SYSTEM
# on the cluster named by PGPORT/PGDATABASE (default 5432/mlb). It NEVER restarts
# Postgres: the preload change takes effect at your next restart of the cluster,
# which is shared with the other databases on that port.
#
#   scripts/pg_extensions_install.sh            # packages only
#   scripts/pg_extensions_install.sh --preload  # + shared_preload_libraries
#
# Then apply the CREATE EXTENSION statements: `mlb migrate` (fresh database) or
# `psql -d mlb -f migrations/0116_postgres_extensions.sql` (already-migrated).
set -euo pipefail

PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-mlb}"
PRELOAD_NEEDED=(pg_stat_kcache pg_qualstats pg_search pg_duckdb)

PACKAGES=(
  postgresql-16-similarity postgresql-16-roaringbitmap
  postgresql-16-pg-uuidv7 postgresql-16-pg-ivm postgresql-16-plpgsql-check
  postgresql-16-pgtap postgresql-16-partman postgresql-16-repack
  postgresql-16-pg-stat-kcache postgresql-16-pg-qualstats
  postgresql-16-pg-hint-plan postgresql-16-orafce postgresql-16-hypopg
)

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${PACKAGES[@]}"

if [[ "${1:-}" == "--preload" ]]; then
  current="$(psql -p "$PGPORT" -d "$PGDATABASE" -Atc 'SHOW shared_preload_libraries')"
  new="$current"
  for lib in "${PRELOAD_NEEDED[@]}"; do
    case ",${new}," in *",${lib},"*) ;; *) new="${new:+$new,}$lib" ;; esac
  done
  if [[ "$new" != "$current" ]]; then
    psql -p "$PGPORT" -d "$PGDATABASE" -v ON_ERROR_STOP=1 \
      -c "ALTER SYSTEM SET shared_preload_libraries = '$new'"
    echo "shared_preload_libraries -> $new (restart the cluster to activate)"
  else
    echo "shared_preload_libraries already complete"
  fi
fi
