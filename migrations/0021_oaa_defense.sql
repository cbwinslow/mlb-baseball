-- Prior-season team defensive value via Statcast Outs Above Average
-- (ADR-040, docs/RESEARCH.md item 8). Same lagged-season shape as
-- home_war_prior/away_war_prior (ADR-038) -- raw.statcast_oaa is a
-- season aggregate, so a team's current-season number used mid-season
-- would leak every game played after the one being predicted.

ALTER TABLE gold.game_feature ADD COLUMN home_oaa_prior numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_oaa_prior numeric;
