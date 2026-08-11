-- load_dataframe() owns the canonical scope index name with the source
-- column preserved: mlb_schedule__season_idx. Older runs also left
-- mlb_schedule_season_idx on the same single _season key. Keep the canonical
-- index and remove the duplicate only when both definitions are exactly the
-- ordinary, non-partial single-column form.
DO $$
DECLARE
    schedule_oid oid;
    season_attnum smallint;
BEGIN
    SELECT c.oid, a.attnum
    INTO schedule_oid, season_attnum
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = '_season'
    WHERE n.nspname = 'raw' AND c.relname = 'mlb_schedule'
      AND a.attnum > 0 AND NOT a.attisdropped;

    IF schedule_oid IS NULL OR season_attnum IS NULL THEN
        RETURN;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_index legacy
        JOIN pg_class legacy_index ON legacy_index.oid = legacy.indexrelid
        JOIN pg_index canonical ON canonical.indrelid = schedule_oid
        JOIN pg_class canonical_index ON canonical_index.oid = canonical.indexrelid
        WHERE legacy.indrelid = schedule_oid
          AND legacy_index.relnamespace = 'raw'::regnamespace
          AND legacy_index.relname = 'mlb_schedule_season_idx'
          AND canonical_index.relnamespace = 'raw'::regnamespace
          AND canonical_index.relname = 'mlb_schedule__season_idx'
          AND legacy.indpred IS NULL AND legacy.indexprs IS NULL
          AND canonical.indpred IS NULL AND canonical.indexprs IS NULL
          -- int2vector uses a zero-based internal lower bound, so compare
          -- its one-key textual representation instead of a normal SQL
          -- array (which would be equal in contents but not bounds).
          AND legacy.indkey::text = season_attnum::text
          AND canonical.indkey::text = season_attnum::text
    ) THEN
        DROP INDEX raw.mlb_schedule_season_idx;
    END IF;
END $$;
