-- core.market.observed_at: the captured_at of the raw snapshot that
-- implied_probability was resolved from (issue #107). Lets
-- market_*_prediction_insert.sql stamp a truthful pre-game generated_at on
-- the kalshi-v1 / polymarket-v1 comparison lines instead of defaulting to
-- now() (which, running post-game, made every decided-game row fail the
-- evaluation's `generated_at < game_start` filter). NULL exactly when
-- implied_probability is NULL.
ALTER TABLE core.market ADD COLUMN IF NOT EXISTS observed_at timestamptz;
