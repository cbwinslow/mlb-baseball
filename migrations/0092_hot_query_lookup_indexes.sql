-- Lookup indexes for the two hottest daily-path queries, from
-- `pg_stat_statements` on production `mlb` (2026-08-29, 13-day window):
--
-- 1. `starter_probable_expected.sql` (starter.py health check, run by
--    `mlb doctor` and every `mlb predict`): 84 calls, **290 s mean**,
--    24,354 s total. `EXPLAIN` shows its `EXISTS` subquery as a Nested
--    Loop that seq-scans raw.mlb_schedule (236 k rows) AND raw.mlb_playbyplay
--    (170 k rows) once per candidate starter. raw.mlb_playbyplay is indexed
--    only on game_pk; raw.mlb_schedule join key `game_id` is unindexed.
--    -> idx on mlb_playbyplay (pitcher_id, game_pk) + mlb_schedule (game_id).
--    Both tables are small (70 MB / 133 MB); the indexes are cheap.
--    hypopg `EXPLAIN` of one EXISTS iteration: cost 31,400 (double seq scan)
--    -> 338 (Index Only Scan pbp -> Index Scan ms), ~90x. The EXISTS runs
--    once per candidate starter (~80-160/call).
--
-- 2. `leverage_index_matrix_build` per-season staging: 228 calls,
--    **128 s mean**. `WHERE re._season::integer = $1` seq-scans
--    raw.retrosheet_event (16.5 M rows / 11 GB) every call -- there is no
--    _season index. Expression index on ((_season::integer)), matching the
--    existing retrosheet_event_outs_ct_int_idx = ((outs_ct::integer)).
--    hypopg `EXPLAIN`: Seq Scan cost 1,399,165 (16.5 M rows) -> Bitmap Index
--    Scan cost 143,568 (~82 k rows), ~10x. Also unblocks the 1.1 incremental
--    rewrite (a fast `WHERE _season = <current>` for the other enrichments).
--
-- Same shape as migrations 0057 / 0090: raw tables are loader-created, so a
-- clean clone has neither yet (no-op). CREATE INDEX IF NOT EXISTS, not
-- CONCURRENTLY (a DO block cannot run CONCURRENTLY). Column-existence
-- guards for the skinny raw tables some tests create. `mlb migrate` is a
-- maintenance step; do not apply while `mlb predict` is scanning these
-- tables.
DO $$
BEGIN
    IF to_regclass('raw.mlb_playbyplay') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'raw' AND table_name = 'mlb_playbyplay'
             AND column_name = 'pitcher_id'
       )
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'raw' AND table_name = 'mlb_playbyplay'
             AND column_name = 'game_pk'
       ) THEN
        CREATE INDEX IF NOT EXISTS idx_mlb_playbyplay_pitcher
            ON raw.mlb_playbyplay (pitcher_id, game_pk);
    END IF;

    IF to_regclass('raw.mlb_schedule') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'raw' AND table_name = 'mlb_schedule'
             AND column_name = 'game_id'
       ) THEN
        CREATE INDEX IF NOT EXISTS idx_mlb_schedule_game_id
            ON raw.mlb_schedule (game_id);
    END IF;

    IF to_regclass('raw.retrosheet_event') IS NOT NULL
       AND EXISTS (
           SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'raw' AND table_name = 'retrosheet_event'
             AND column_name = '_season'
       ) THEN
        CREATE INDEX IF NOT EXISTS idx_retrosheet_event_season_int
            ON raw.retrosheet_event (((_season)::integer));
    END IF;
END $$;
