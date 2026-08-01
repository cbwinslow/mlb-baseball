-- Prior-season team baserunning speed via Statcast Sprint Speed
-- (ADR-041, docs/RESEARCH.md). Same lagged-season shape as
-- home_war_prior/home_oaa_prior -- raw.statcast_sprint_speed is a
-- season aggregate, so a team's current-season number used mid-season
-- would leak every game played after the one being predicted.

ALTER TABLE gold.game_feature ADD COLUMN home_speed_prior numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_speed_prior numeric;
