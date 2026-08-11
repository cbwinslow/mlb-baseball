-- load_dataframe() creates the canonical raw scope indexes with a double
-- underscore before the source column name (for example,
-- mlb_schedule__season_idx). Older releases also left same-definition indexes
-- under legacy names. They add write, vacuum, and storage cost without helping
-- the planner. Remove only an exact, non-unique, non-primary duplicate and
-- keep the current-loader name when it exists.
DO $$
DECLARE
    duplicate record;
BEGIN
    FOR duplicate IN
        WITH index_definition AS (
            SELECT x.indrelid, n.nspname AS schema_name, i.relname AS index_name,
                   x.indisunique, x.indisprimary, x.indkey::text,
                   x.indclass::text, x.indcollation::text, x.indoption::text,
                   coalesce(pg_get_expr(x.indexprs, x.indrelid), '') AS expressions,
                   coalesce(pg_get_expr(x.indpred, x.indrelid), '') AS predicate
            FROM pg_index x
            JOIN pg_class t ON t.oid = x.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_class i ON i.oid = x.indexrelid
            WHERE n.nspname = 'raw' AND x.indisvalid
              AND NOT x.indisunique AND NOT x.indisprimary
        ), ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY indrelid, indisunique, indisprimary, indkey,
                             indclass, indcollation, indoption, expressions, predicate
                ORDER BY CASE
                    WHEN index_name LIKE '%__%' THEN 0
                    WHEN index_name LIKE '%_season_idx' THEN 2
                    ELSE 1
                END, index_name
            ) AS rank
            FROM index_definition
        )
        SELECT schema_name, index_name FROM ranked WHERE rank > 1
    LOOP
        EXECUTE format('DROP INDEX %I.%I', duplicate.schema_name, duplicate.index_name);
    END LOOP;
END $$;
