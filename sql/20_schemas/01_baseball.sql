-- 20_schemas/01_baseball.sql
-- Create the dedicated baseball schema that all application tables live in.
-- Using a separate schema keeps baseball data isolated from public and
-- allows future multi-schema setups (e.g. staging vs production).

CREATE SCHEMA IF NOT EXISTS baseball;

-- Grant usage to the application role if it exists (idempotent).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'baseball_app') THEN
        GRANT USAGE ON SCHEMA baseball TO baseball_app;
        ALTER DEFAULT PRIVILEGES IN SCHEMA baseball
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO baseball_app;
    END IF;
END
$$;
