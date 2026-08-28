-- Entering four-seam VAA (degrees) for listed starters (WIRE of VAA-01).
ALTER TABLE gold.game_feature ADD COLUMN IF NOT EXISTS home_starter_ff_vaa numeric;
ALTER TABLE gold.game_feature ADD COLUMN IF NOT EXISTS away_starter_ff_vaa numeric;
