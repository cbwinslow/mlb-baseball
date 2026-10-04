-- Read-only production schema check (task 2.6, design D6): every column of
-- every raw.retrosheet_* table the tie-out gate compares. Compared against
-- mlb_baseball.tieout_schema_contract.RAW_SCHEMA_CONTRACT in tieout.check_columns.
SELECT table_name, column_name
FROM information_schema.columns
WHERE table_schema = 'raw'
  AND table_name = ANY(%(tables)s)
