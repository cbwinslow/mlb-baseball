-- Run-total (over/under) prediction, ADR-054. Deliberately NOT gold.prediction's
-- shape reused: gold.prediction stores a probability (a classification target,
-- win/loss); this is a regression target (expected combined runs), so it stores
-- a point estimate plus the naive baseline used to judge it, not a probability.
--
-- History-preserving, same precedent as gold.prediction (migration 0014):
-- generated_at is part of the PK on purpose, so re-running mlb_baseball.model.
-- total.predict() for a still-upcoming game before it's played adds a new row
-- rather than overwriting the last one -- that history is what lets prediction
-- calibration be tracked over time as game day approaches.
--
-- baseline_total is stored alongside predicted_total, not just used transiently
-- during train()'s own evaluation -- keeping it on every row lets "did the
-- model actually beat the naive park-trailing-average baseline on this game"
-- be answered later without recomputing the baseline from scratch.
--
-- actual_total stays NULL until the game is final, same as gold.prediction.
-- actual_home_win -- a separate backfill step (total.backfill_outcomes) fills
-- it in from core.game once the game lands there.

CREATE TABLE gold.total_prediction (
    mlb_game_pk text NOT NULL,
    model_version text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    predicted_total numeric NOT NULL,
    baseline_total numeric NOT NULL,
    actual_total integer,
    PRIMARY KEY (mlb_game_pk, model_version, generated_at)
);

CREATE INDEX total_prediction_game_idx ON gold.total_prediction (mlb_game_pk);
CREATE INDEX total_prediction_model_idx ON gold.total_prediction (model_version);
