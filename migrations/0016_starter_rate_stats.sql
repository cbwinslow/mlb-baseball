-- Adds per-batter-faced strikeout/walk/home-run rate columns for the
-- starting pitcher on each side, alongside the already-reserved
-- home_starter_era/away_starter_era (repurposed to hold a true,
-- innings-pitched-based FIP -- see ADR-034 and mlb_baseball/model/starter.py).
-- Both a true-FIP composite and the raw K%/BB%/HR% rates are kept: FIP is
-- the familiar single number, the rates are the same underlying signal
-- decomposed for a model to weight independently if that turns out to
-- matter more than the composite.

ALTER TABLE gold.game_feature ADD COLUMN home_starter_k_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_k_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_starter_bb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_bb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_starter_hr_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_hr_pct numeric;
