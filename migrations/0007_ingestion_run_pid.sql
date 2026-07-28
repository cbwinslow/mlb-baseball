-- Adds process-liveness tracking to meta.ingestion_run so a killed-externally
-- process (SIGTERM/SIGKILL, not a caught Python exception) doesn't leave a
-- permanent "running" row that mlb doctor and season_already_loaded-style
-- resumability checks would otherwise trust forever. See docs/DECISIONS.md
-- ADR-022 and ingest.py's reap_stale_runs().
--
-- A real bug found in production, not speculative: killing a background
-- bootstrap process mid-run (done several times this session, including
-- deliberately restarting a stale-code run) left rows stuck at status =
-- 'running' with no automatic recovery — found and manually cleaned up by
-- hand via `DELETE FROM meta.ingestion_run` each time before this fix.

ALTER TABLE meta.ingestion_run ADD COLUMN pid integer;
