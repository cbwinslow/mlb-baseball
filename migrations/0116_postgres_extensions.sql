-- Owner-requested toolbox of PostgreSQL extensions (ADR-302; roadmap in
-- artifacts/postgres_extensions_recommendations_and_roadmap.md).
--
-- Every extension is OPTIONAL at the server level: it is created only if the
-- server has its package (pg_available_extensions), otherwise it is skipped
-- with a NOTICE. This keeps a fresh machine / CI's stock postgres:16 image
-- migratable. Install the packages with scripts/pg_extensions_install.sh, then
-- apply this file again by hand (it is idempotent):
--   psql -d <db> -f migrations/0116_postgres_extensions.sql
-- `mlb doctor` reports which are present.
--
-- Extensions that need shared_preload_libraries (pg_stat_kcache, pg_qualstats)
-- are created only when actually preloaded; creating them without the preload
-- either errors or records nothing.

DO $$
DECLARE
    ext record;
BEGIN
    FOR ext IN
        SELECT * FROM (VALUES
            -- name,                schema,    needs_preload
            ('fuzzystrmatch',       NULL,      false),
            ('pg_similarity',       NULL,      false),
            ('roaringbitmap',       NULL,      false),
            ('pg_uuidv7',           NULL,      false),
            ('pg_ivm',              NULL,      false),
            ('plpgsql_check',       NULL,      false),
            ('pgtap',               NULL,      false),
            ('pg_partman',          'partman', false),
            ('pg_repack',           NULL,      false),
            ('pg_buffercache',      NULL,      false),
            ('timescaledb_toolkit', NULL,      false),
            ('jsonb_plpython3u',    NULL,      false),
            ('hstore_plpython3u',   NULL,      false),
            ('hypopg',              NULL,      false),
            ('pg_hint_plan',        NULL,      false),
            ('orafce',              NULL,      false),
            ('pg_duckdb',           NULL,      true),
            ('pg_stat_kcache',      NULL,      true),
            ('pg_qualstats',        NULL,      true),
            ('vectorscale',         NULL,      false),
            ('pg_graphql',          NULL,      false),
            ('pg_column_tetris',    NULL,      false),
            ('multicorn',           NULL,      false),
            ('pg_search',           NULL,      true)
        ) AS t(name, schema_name, needs_preload)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = ext.name) THEN
            RAISE NOTICE 'extension % not installed on this server; skipped', ext.name;
            CONTINUE;
        END IF;
        IF ext.needs_preload
           AND current_setting('shared_preload_libraries') NOT LIKE '%' || ext.name || '%' THEN
            RAISE NOTICE 'extension % not in shared_preload_libraries; skipped', ext.name;
            CONTINUE;
        END IF;
        BEGIN
            IF ext.schema_name IS NOT NULL THEN
                EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', ext.schema_name);
                EXECUTE format('CREATE EXTENSION IF NOT EXISTS %I SCHEMA %I CASCADE',
                               ext.name, ext.schema_name);
            ELSE
                EXECUTE format('CREATE EXTENSION IF NOT EXISTS %I CASCADE', ext.name);
            END IF;
        EXCEPTION WHEN duplicate_function OR duplicate_object THEN
            -- e.g. pg_duckdb vs timescaledb_toolkit both define approx_count_distinct
            RAISE NOTICE 'extension % conflicts with an installed object (%); skipped',
                         ext.name, SQLERRM;
        END;
    END LOOP;
END
$$;
