-- Phase 2 (ADR-032): one row per (game, model_version, generated_at) --
-- deliberately history-preserving, not upserted-in-place, so re-running a
-- model closer to game time doesn't erase how its prediction looked
-- earlier -- that history is the whole point of tracking calibration.
-- actual_home_win stays NULL until the game is final; a separate step
-- backfills it (see mlb_baseball/model).

CREATE TABLE gold.prediction (
    game_id bigint NOT NULL REFERENCES core.game (id),
    model_version text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    home_win_prob numeric NOT NULL,
    actual_home_win boolean,
    PRIMARY KEY (game_id, model_version, generated_at)
);

CREATE INDEX prediction_game_idx ON gold.prediction (game_id);
CREATE INDEX prediction_model_idx ON gold.prediction (model_version);
