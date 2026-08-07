-- Test/development databases that received the first Plan 01F draft have a
-- redundant descending index.  Fresh production installations no longer make
-- it because 0034 was corrected before production rollout.
DROP INDEX IF EXISTS gold.prediction_instance_model_generated_idx;
