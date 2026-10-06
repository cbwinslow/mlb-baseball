-- Raw layer profile (openspec/changes/full-source-ingestion, task 0.12; ADR-295).
-- What does each raw table hold right now: exact rows, season range, and when it was
-- loaded. Data-date ranges are NOT here: raw columns are text and the date column
-- differs per table, so they need an explicit per-table declaration (see mlb coverage).
--
--   meta.raw_profile              one row per raw table, as of profiled_at
--   meta.refresh_raw_profile()    recompute every raw table (or one), returns tables written

CREATE TABLE IF NOT EXISTS meta.raw_profile (
    table_name text PRIMARY KEY,
    row_count bigint NOT NULL,
    first_season text,
    last_season text,
    first_loaded_at timestamptz,
    last_loaded_at timestamptz,
    profiled_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE meta.raw_profile IS
    'Exact row count, _season range and _loaded_at range per raw table; refreshed by meta.refresh_raw_profile(). Stale between refreshes: check profiled_at.';

CREATE OR REPLACE FUNCTION meta.refresh_raw_profile(only_table text DEFAULT NULL)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    t record;
    n bigint;
    s_min text;
    s_max text;
    l_min timestamptz;
    l_max timestamptz;
    has_season boolean;
    has_loaded boolean;
    written integer := 0;
BEGIN
    FOR t IN
        SELECT c.relname AS name
        FROM pg_class c
        JOIN pg_namespace ns ON ns.oid = c.relnamespace
        WHERE ns.nspname = 'raw' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
          AND (only_table IS NULL OR c.relname = only_table)
        ORDER BY c.relname
    LOOP
        SELECT bool_or(a.attname = '_season'), bool_or(a.attname = '_loaded_at')
          INTO has_season, has_loaded
          FROM pg_attribute a
         WHERE a.attrelid = format('raw.%I', t.name)::regclass
           AND a.attnum > 0 AND NOT a.attisdropped;
        s_min := NULL; s_max := NULL; l_min := NULL; l_max := NULL;
        EXECUTE format('SELECT count(*) FROM raw.%I', t.name) INTO n;
        IF n > 0 AND has_season THEN
            EXECUTE format('SELECT min(_season), max(_season) FROM raw.%I', t.name)
                INTO s_min, s_max;
        END IF;
        IF n > 0 AND has_loaded THEN
            EXECUTE format('SELECT min(_loaded_at), max(_loaded_at) FROM raw.%I', t.name)
                INTO l_min, l_max;
        END IF;
        INSERT INTO meta.raw_profile AS p
            (table_name, row_count, first_season, last_season,
             first_loaded_at, last_loaded_at, profiled_at)
        VALUES (t.name, n, s_min, s_max, l_min, l_max, now())
        ON CONFLICT (table_name) DO UPDATE SET
            row_count = EXCLUDED.row_count,
            first_season = EXCLUDED.first_season,
            last_season = EXCLUDED.last_season,
            first_loaded_at = EXCLUDED.first_loaded_at,
            last_loaded_at = EXCLUDED.last_loaded_at,
            profiled_at = EXCLUDED.profiled_at;
        written := written + 1;
    END LOOP;
    IF only_table IS NULL THEN
        DELETE FROM meta.raw_profile p
         WHERE NOT EXISTS (
            SELECT 1 FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
             WHERE ns.nspname = 'raw' AND c.relname = p.table_name
               AND c.relkind IN ('r', 'p') AND NOT c.relispartition);
    END IF;
    RETURN written;
END;
$$;
COMMENT ON FUNCTION meta.refresh_raw_profile(text) IS
    'Recompute meta.raw_profile for every raw table (or only_table). Exact count(*) per table: slow on the large ones. Returns the number of tables written.';
