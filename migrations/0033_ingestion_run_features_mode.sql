-- Makes the separately invocable gold-feature rebuild auditable without
-- mislabeling it as a connector/bootstrap operation.  ``mlb features`` is a
-- transactional feature-engineering stage, distinct from ingestion update,
-- historical backfill, and the legacy all-in-one model bootstrap/predict run.

ALTER TABLE meta.ingestion_run DROP CONSTRAINT ingestion_run_mode_check;
ALTER TABLE meta.ingestion_run ADD CONSTRAINT ingestion_run_mode_check
    CHECK (mode IN ('bootstrap', 'update', 'backfill', 'features'));
