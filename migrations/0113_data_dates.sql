-- Data-date ranges for the raw profile (openspec/changes/full-source-ingestion, task 0.12).
-- Raw dates are text in several formats and the date column differs per table, so the
-- column is declared per table by the caller (the coverage registry), not guessed here.
--
--   meta.data_date(text)                    one text value -> date (NULL when not a date)
--   meta.data_date_range(table, column)     first date, last date, count of non-date values
--   meta.refresh_raw_profile(table, jsonb)  now also stores the declared column's range
--
-- Accepted forms: 2008-03-27[...], 2008/03/27, 20080327, 20080327.0, epoch seconds.
-- Range is taken on the text itself (one format per column, so text order is date order)
-- and only the two ends are converted; a value outside the forms counts as non-date.

CREATE OR REPLACE FUNCTION meta.data_date(v text)
RETURNS date
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    d date;
BEGIN
    IF v ~ '^\d{4}-\d{2}-\d{2}' THEN
        d := to_date(substr(v, 1, 10), 'YYYY-MM-DD');
    ELSIF v ~ '^\d{4}/\d{2}/\d{2}' THEN
        d := to_date(substr(v, 1, 10), 'YYYY/MM/DD');
    ELSIF v ~ '^\d{8}(\.0)?$' THEN
        d := to_date(substr(v, 1, 8), 'YYYYMMDD');
    ELSIF v ~ '^\d{9,10}(\.\d+)?$' THEN
        d := (to_timestamp(v::double precision) AT TIME ZONE 'UTC')::date;
    END IF;
    IF d < DATE '1800-01-01' OR d > DATE '2100-01-01' THEN
        RETURN NULL;
    END IF;
    RETURN d;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$;
COMMENT ON FUNCTION meta.data_date(text) IS
    'Parse the raw date text forms (ISO, yyyy/mm/dd, yyyymmdd[.0], epoch seconds) to a date; NULL when it is none of them or out of 1800-2100.';

CREATE OR REPLACE FUNCTION meta.data_date_range(tbl regclass, col text)
RETURNS TABLE (first_date date, last_date date, not_date bigint)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    forms constant text :=
        '^(\d{4}-\d{2}-\d{2}|\d{4}/\d{2}/\d{2}|\d{8}(\.0)?|\d{9,10}(\.\d+)?)';
    lo text;
    hi text;
    bad bigint;
BEGIN
    EXECUTE format(
        'SELECT min(%1$I) FILTER (WHERE %1$I ~ $1), max(%1$I) FILTER (WHERE %1$I ~ $1),
                count(*) FILTER (WHERE %1$I IS NOT NULL AND %1$I !~ $1)
           FROM %2$s', col, tbl)
        INTO lo, hi, bad USING forms;
    first_date := meta.data_date(lo);
    last_date := meta.data_date(hi);
    not_date := bad;
    RETURN NEXT;
END;
$$;
COMMENT ON FUNCTION meta.data_date_range(regclass, text) IS
    'First and last date in a text date column, and how many non-null values are not a recognised date form. Reads the whole column.';

ALTER TABLE meta.raw_profile
    ADD COLUMN IF NOT EXISTS date_column text,
    ADD COLUMN IF NOT EXISTS first_data_date date,
    ADD COLUMN IF NOT EXISTS last_data_date date,
    ADD COLUMN IF NOT EXISTS date_not_parsed bigint;

DROP FUNCTION IF EXISTS meta.refresh_raw_profile(text);

CREATE OR REPLACE FUNCTION meta.refresh_raw_profile(
    only_table text DEFAULT NULL,
    date_columns jsonb DEFAULT '{}'::jsonb
)
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
    has_dcol boolean;
    d_first date;
    d_last date;
    d_bad bigint;
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
        SELECT bool_or(a.attname = '_season'), bool_or(a.attname = '_loaded_at'),
               bool_or(a.attname = date_columns ->> t.name)
          INTO has_season, has_loaded, has_dcol
          FROM pg_attribute a
         WHERE a.attrelid = format('raw.%I', t.name)::regclass
           AND a.attnum > 0 AND NOT a.attisdropped;
        s_min := NULL; s_max := NULL; l_min := NULL; l_max := NULL;
        d_first := NULL; d_last := NULL; d_bad := NULL;
        EXECUTE format('SELECT count(*) FROM raw.%I', t.name) INTO n;
        IF n > 0 AND has_season THEN
            EXECUTE format('SELECT min(_season), max(_season) FROM raw.%I', t.name)
                INTO s_min, s_max;
        END IF;
        IF n > 0 AND has_loaded THEN
            EXECUTE format('SELECT min(_loaded_at), max(_loaded_at) FROM raw.%I', t.name)
                INTO l_min, l_max;
        END IF;
        IF n > 0 AND has_dcol THEN
            SELECT r.first_date, r.last_date, r.not_date INTO d_first, d_last, d_bad
              FROM meta.data_date_range(format('raw.%I', t.name)::regclass,
                                        date_columns ->> t.name) r;
        END IF;
        INSERT INTO meta.raw_profile AS p
            (table_name, row_count, first_season, last_season, first_loaded_at, last_loaded_at,
             date_column, first_data_date, last_data_date, date_not_parsed, profiled_at)
        VALUES (t.name, n, s_min, s_max, l_min, l_max,
                CASE WHEN has_dcol THEN date_columns ->> t.name END, d_first, d_last, d_bad, now())
        ON CONFLICT (table_name) DO UPDATE SET
            row_count = EXCLUDED.row_count,
            first_season = EXCLUDED.first_season,
            last_season = EXCLUDED.last_season,
            first_loaded_at = EXCLUDED.first_loaded_at,
            last_loaded_at = EXCLUDED.last_loaded_at,
            date_column = EXCLUDED.date_column,
            first_data_date = EXCLUDED.first_data_date,
            last_data_date = EXCLUDED.last_data_date,
            date_not_parsed = EXCLUDED.date_not_parsed,
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
COMMENT ON FUNCTION meta.refresh_raw_profile(text, jsonb) IS
    'Recompute meta.raw_profile for every raw table (or only_table). date_columns maps table name to its declared data-date column. Exact count(*) per table: slow on the large ones. Returns the number of tables written.';
