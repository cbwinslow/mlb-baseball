-- core.play/core.pitch (migration 0011) declared one partition per
-- season from 1871-2035 -- a 9-year buffer past any real data (2026 is
-- the current max season in core.game). Empty future partitions still
-- count toward the per-relation cost of every TRUNCATE against these
-- tables (confirmed: 166 partitions each before this migration), so
-- they're pure overhead with zero benefit today.
--
-- Drops only genuinely empty partitions (2028-2035) -- never touches
-- 1871-2026's real, populated data. Keeps 2027 as a one-season buffer
-- so a stray next-season row during rollover doesn't need this
-- migration re-run first. Safe even without that buffer: the DEFAULT
-- partition (core.play_default/core.pitch_default) already catches any
-- row for a season without its own dedicated partition -- correctness
-- doesn't depend on the exact declared range, only performance does.
DO $$
DECLARE
    yr INT;
BEGIN
    FOR yr IN 2028..2035 LOOP
        EXECUTE format('DROP TABLE IF EXISTS core.play_%s', yr);
        EXECUTE format('DROP TABLE IF EXISTS core.pitch_%s', yr);
    END LOOP;
END $$;
