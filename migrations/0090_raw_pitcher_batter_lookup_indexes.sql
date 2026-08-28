-- Lookup indexes for daily enrichment SQL that filters Statcast / Retrosheet
-- by pitcher or batter. Measured 2026-08-28 on production `mlb`:
-- raw.statcast_pitch 13.5M rows / ~10 GB, indexed on game_pk and game_date
-- only; raw.retrosheet_event 16.5M rows / 11 GB, indexed on game_id only.
-- PLT-01's correlated `WHERE pitcher = ... LIMIT 1` (ADR-268) was the
-- worst symptom; COM-01 / SHP-01 / starter still seq-scan these heaps.
--
-- Same shape as migration 0057: raw tables are loader-created, so a clean
-- clone has neither table yet (no-op). CREATE INDEX IF NOT EXISTS, not
-- CONCURRENTLY — a DO block cannot run CONCURRENTLY (0057, verified).
-- Column-existence guards: some tests create skinny raw.statcast_pitch
-- without every Statcast column; indexing a missing column would fail
-- those sessions. `mlb migrate` is a maintenance step; do not apply this
-- to production `mlb` while `mlb predict` is scanning these tables.
DO $$
BEGIN
    IF to_regclass('raw.statcast_pitch') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'raw' AND table_name = 'statcast_pitch'
             AND column_name = 'pitcher'
       ) THEN
        CREATE INDEX IF NOT EXISTS idx_statcast_pitch_pitcher
            ON raw.statcast_pitch (pitcher);
    END IF;
    IF to_regclass('raw.statcast_pitch') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'raw' AND table_name = 'statcast_pitch'
             AND column_name = 'batter'
       ) THEN
        CREATE INDEX IF NOT EXISTS idx_statcast_pitch_batter
            ON raw.statcast_pitch (batter);
    END IF;
    IF to_regclass('raw.retrosheet_event') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'raw' AND table_name = 'retrosheet_event'
             AND column_name = 'pit_id'
       ) THEN
        CREATE INDEX IF NOT EXISTS idx_retrosheet_event_pit_id
            ON raw.retrosheet_event (pit_id);
    END IF;
    IF to_regclass('raw.retrosheet_event') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'raw' AND table_name = 'retrosheet_event'
             AND column_name = 'bat_id'
       ) THEN
        CREATE INDEX IF NOT EXISTS idx_retrosheet_event_bat_id
            ON raw.retrosheet_event (bat_id);
    END IF;
END $$;
