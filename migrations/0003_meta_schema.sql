-- Tracks every connector run (bootstrap or update) for observability and maintenance:
-- other users bootstrapping this database, or anyone running scheduled updates, can
-- see what ran, when, and whether it worked. See docs/ARCHITECTURE.md "Connector contract".
--
-- Schema is `meta`, not `control` — the legacy database (still being backed up as this
-- migration is written) already has a `control.ingestion_run` table with a different
-- shape. Using a distinct name avoids both the naming collision and any risk of a
-- DROP/ALTER blocking behind pg_dump's lock on the live table.

CREATE SCHEMA IF NOT EXISTS meta;

CREATE TABLE meta.ingestion_run (
    id bigserial PRIMARY KEY,
    source text NOT NULL,
    mode text NOT NULL CHECK (mode IN ('bootstrap', 'update')),
    status text NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    rows integer,
    error text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz
);

CREATE INDEX ON meta.ingestion_run (source, started_at DESC);
