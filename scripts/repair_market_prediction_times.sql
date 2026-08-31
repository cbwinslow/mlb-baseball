-- One-time repair for issue #107. Run once against PRODUCTION `mlb` AFTER
-- migration 0093 is applied AND `mlb conform` has run at least once with the
-- new code (so `core.market.observed_at` is populated), and BEFORE the next
-- `mlb predict`:
--
--   psql "postgresql:///mlb" -f scripts/repair_market_prediction_times.sql
--
-- Deletes kalshi-v1 / polymarket-v1 rows in gold.prediction whose
-- generated_at is at or after first pitch -- the stale rows _record_decided()
-- wrote with generated_at = now() while running post-game. They are
-- unrecoverable noise: 0 pass evaluation._selected_predictions' pre-game
-- filter. The next `mlb predict` re-inserts them correctly from
-- core.market.observed_at (via the NOT EXISTS idempotency guard).
-- gold.prediction holds regenerable model output, not raw/core source data.
--
-- DRY RUN FIRST -- run this SELECT by hand and eyeball the count before
-- running the file:
--
--   -- confirm observed_at is populated first:
--   SELECT count(*) FROM core.market WHERE observed_at IS NOT NULL;  -- must be > 0
--
--   WITH schedule AS (
--       SELECT game_id, min(NULLIF(game_datetime,'')::timestamptz) AS game_start
--       FROM raw.mlb_schedule
--       WHERE game_id IS NOT NULL AND NULLIF(game_datetime,'') IS NOT NULL
--       GROUP BY game_id HAVING count(DISTINCT NULLIF(game_datetime,'')) = 1)
--   SELECT count(*) FROM gold.prediction p JOIN schedule s ON s.game_id = p.mlb_game_pk
--   WHERE p.model_version IN ('kalshi-v1','polymarket-v1') AND p.generated_at >= s.game_start;

\set ON_ERROR_STOP on

WITH schedule AS (
    SELECT game_id,
           min(NULLIF(game_datetime, '')::timestamptz) AS game_start
    FROM raw.mlb_schedule
    WHERE game_id IS NOT NULL AND NULLIF(game_datetime, '') IS NOT NULL
    GROUP BY game_id
    HAVING count(DISTINCT NULLIF(game_datetime, '')) = 1
)
DELETE FROM gold.prediction p
USING schedule s
WHERE s.game_id = p.mlb_game_pk
  AND p.model_version IN ('kalshi-v1', 'polymarket-v1')
  AND p.generated_at >= s.game_start;
