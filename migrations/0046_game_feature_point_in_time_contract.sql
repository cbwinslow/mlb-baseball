-- The first reproducible MLB-game feature relation needs an explicit pregame
-- cutoff and its declared doubleheader order. Existing wider enrichment
-- columns remain for backwards compatibility; this adds the audited base
-- family only.

ALTER TABLE gold.game_feature
    ADD COLUMN IF NOT EXISTS game_number integer,
    ADD COLUMN IF NOT EXISTS feature_cutoff_at timestamptz,
    ADD COLUMN IF NOT EXISTS home_wins integer,
    ADD COLUMN IF NOT EXISTS home_losses integer,
    ADD COLUMN IF NOT EXISTS away_wins integer,
    ADD COLUMN IF NOT EXISTS away_losses integer,
    ADD COLUMN IF NOT EXISTS home_runs_for integer,
    ADD COLUMN IF NOT EXISTS home_runs_allowed integer,
    ADD COLUMN IF NOT EXISTS away_runs_for integer,
    ADD COLUMN IF NOT EXISTS away_runs_allowed integer,
    ADD COLUMN IF NOT EXISTS home_field boolean;
