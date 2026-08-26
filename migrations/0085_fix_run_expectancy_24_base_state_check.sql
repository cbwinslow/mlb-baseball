-- Fixes a real, urgent bug found by a Plan 06 subagent: gold.run_expectancy_24's
-- base_state CHECK constraint (from migration 0068) lists values
-- ('020','003','120','103','023','123') that the code building base_state
-- (a concatenation of '0'/'1' flags per base -- see
-- mlb_baseball/sql/run_expectancy_matrix_build.sql) can never actually
-- produce -- the only real values are '000','100','010','001','110','101',
-- '011','111'. This has silently left gold.run_expectancy_24 completely
-- empty in production (every INSERT from a real base state other than
-- '000'/'100' violates the constraint and the whole build fails).
--
-- Urgent: run_expectancy.compute() is wired into enrich_feature_stage()
-- (mlb predict's daily cron path) and only reached this step for the first
-- time after ADR-260 fixed the earlier bsr.py crash blocking everything
-- ahead of it -- without this fix, the very next scheduled cron run would
-- hit this same CHECK violation and crash the pipeline again, a direct
-- recurrence of the ADR-260 incident with a different root cause.

ALTER TABLE gold.run_expectancy_24 DROP CONSTRAINT run_expectancy_24_base_state_check;
ALTER TABLE gold.run_expectancy_24 ADD CONSTRAINT run_expectancy_24_base_state_check
    CHECK (base_state IN ('000', '100', '010', '001', '110', '101', '011', '111'));
