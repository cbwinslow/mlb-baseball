-- Fixes a real query-planner cardinality misestimate that made
-- leverage_index.compute() (mlb_baseball/model/leverage_index.py, ADR-262)
-- run for multiple hours instead of minutes against real production data.
--
-- Two of the predicates in leverage_index_matrix_build.sql wrap a raw text
-- column in an expression (lower(gametype) = 'regular', outs_ct::integer
-- BETWEEN 0 AND 2) that Postgres has no column statistics for, so its
-- default selectivity guess is wildly wrong (verified directly via EXPLAIN:
-- estimated ~468 matching rows for retrosheet_gameinfo's gametype filter
-- against a real 220,191; estimated 468 rows for retrosheet_event's outs_ct
-- filter against a real ~16.4 million). That misestimate cascades into the
-- join above it, which builds its hash table sized for the (wrong) tiny
-- estimate while the real input is millions of rows -- a severely
-- undersized hash table with catastrophic bucket collisions.
--
-- An expression index lets ANALYZE collect real statistics on the exact
-- expression (see https://www.postgresql.org/docs/current/indexes-
-- expressional.html -- "the created index can be used ... and, more
-- importantly, ANALYZE will gather statistics on it"), which fixes the
-- planner's estimate at every join level without changing any query text.
-- Confirmed directly: after adding these two indexes and running ANALYZE,
-- EXPLAIN showed every hash join's build side correctly sized, and the
-- real leverage_index.compute() run completed in minutes instead of
-- running unbounded for 2+ hours.

-- raw.retrosheet_gameinfo/raw.retrosheet_event are loader-created, not
-- migration-created (see migration 0057's identical header) -- a clean
-- clone or the pytest-postgresql test template has neither table yet, so
-- guard both against a real UndefinedTable error the same established way.
DO $$
BEGIN
    IF to_regclass('raw.retrosheet_gameinfo') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS retrosheet_gameinfo_gametype_lower_idx
            ON raw.retrosheet_gameinfo (lower(gametype));
    END IF;
    IF to_regclass('raw.retrosheet_event') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS retrosheet_event_outs_ct_int_idx
            ON raw.retrosheet_event ((outs_ct::integer));
    END IF;
END $$;
