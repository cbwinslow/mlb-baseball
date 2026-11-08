-- Retype the Chadwick register tables from all-text to their declared types (ADR-304,
-- openspec change typed-raw-layer 1.2). The declaration is
-- mlb_baseball/ingest_layer/schemas/register.json; this file is generated from it.
--
-- Safe to re-run: a column that is already typed is skipped. An empty source value is NULL
-- (the loaders already stored empty as NULL). A value that does not cast stops the migration and
-- rolls it back; the production data was checked on 2026-10-13 (every value casts, and the typed
-- copy compared equal row by row to production).

DO $retype$
DECLARE
    todo text;
BEGIN
    SELECT string_agg(format('ALTER COLUMN %I TYPE %s USING NULLIF(%I, '''')::%s', declared.col, declared.kind, declared.col, declared.kind), ', ')
      INTO todo
      FROM (VALUES

        ('key_mlbam', 'integer'),
        ('key_fangraphs', 'integer'),
        ('birth_year', 'integer'),
        ('birth_month', 'integer'),
        ('birth_day', 'integer'),
        ('death_year', 'integer'),
        ('death_month', 'integer'),
        ('death_day', 'integer'),
        ('pro_played_first', 'integer'),
        ('pro_played_last', 'integer'),
        ('mlb_played_first', 'integer'),
        ('mlb_played_last', 'integer'),
        ('col_played_first', 'integer'),
        ('col_played_last', 'integer'),
        ('pro_managed_first', 'integer'),
        ('pro_managed_last', 'integer'),
        ('mlb_managed_first', 'integer'),
        ('mlb_managed_last', 'integer'),
        ('col_managed_first', 'integer'),
        ('col_managed_last', 'integer'),
        ('pro_umpired_first', 'integer'),
        ('pro_umpired_last', 'integer'),
        ('mlb_umpired_first', 'integer'),
        ('mlb_umpired_last', 'integer')

      ) AS declared(col, kind)
      JOIN information_schema.columns c
        ON c.table_schema = 'raw' AND c.table_name = 'register_people'
       AND c.column_name = declared.col AND c.data_type = 'text';
    IF todo IS NOT NULL THEN
        EXECUTE 'ALTER TABLE raw.register_people ' || todo;
    END IF;
END
$retype$;

DO $retype$
DECLARE
    todo text;
BEGIN
    SELECT string_agg(format('ALTER COLUMN %I TYPE %s USING NULLIF(%I, '''')::%s', declared.col, declared.kind, declared.col, declared.kind), ', ')
      INTO todo
      FROM (VALUES

        ('birth_year', 'integer'),
        ('birth_month', 'integer'),
        ('birth_day', 'integer'),
        ('altname_date_start', 'integer'),
        ('altname_date_end', 'integer')

      ) AS declared(col, kind)
      JOIN information_schema.columns c
        ON c.table_schema = 'raw' AND c.table_name = 'register_names'
       AND c.column_name = declared.col AND c.data_type = 'text';
    IF todo IS NOT NULL THEN
        EXECUTE 'ALTER TABLE raw.register_names ' || todo;
    END IF;
END
$retype$;
