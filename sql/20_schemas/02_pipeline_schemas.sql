-- 20_schemas/02_pipeline_schemas.sql
-- Create the raw, staging, and core pipeline schemas.
--   raw     : verbatim source data exactly as received from upstream APIs
--   staging : normalized/typed intermediary before merging into core
--   core    : canonical, deduplicated production tables

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
