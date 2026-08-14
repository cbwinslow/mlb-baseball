-- Prior team BABIP (OFF-04, ADR-063). (H - HR) / (AB - K - HR + SF)
-- entering-value point-in-time rate computed from Retrosheet events.

ALTER TABLE gold.game_feature ADD COLUMN home_babip numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_babip numeric;
