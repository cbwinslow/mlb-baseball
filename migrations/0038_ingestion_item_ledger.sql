-- Durable checkpointing below connector-run level. A historical API run can
-- contain thousands of independent games: each must be recorded as loaded,
-- unavailable from the source, or failed, rather than leaving an ambiguous
-- half-finished connector run after an interruption.
CREATE TABLE meta.ingestion_item (
    source text NOT NULL,
    dataset text NOT NULL,
    item_key text NOT NULL,
    status text NOT NULL CHECK (status IN ('loaded', 'unavailable', 'failed')),
    attempts integer NOT NULL DEFAULT 1 CHECK (attempts > 0),
    source_url text,
    artifact_path text,
    artifact_sha256 text,
    bytes bigint CHECK (bytes >= 0),
    http_status integer,
    rows integer CHECK (rows >= 0),
    parser_version text,
    schema_fingerprint text,
    error text,
    run_id bigint REFERENCES meta.ingestion_run (id),
    retrieved_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, dataset, item_key)
);

CREATE INDEX ingestion_item_work_idx
    ON meta.ingestion_item (source, dataset, status, updated_at);
