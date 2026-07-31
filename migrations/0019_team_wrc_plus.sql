-- wRC+: park- and league-adjusted extension of team wOBA (ADR-037,
-- follow-up to ADR-036/035). League average = 100 by construction.

ALTER TABLE gold.game_feature ADD COLUMN home_wrc_plus numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_wrc_plus numeric;
