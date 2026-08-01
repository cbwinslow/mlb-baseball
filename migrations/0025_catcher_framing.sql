-- Prior-season team catcher-framing value via Statcast (ADR-045,
-- docs/RESEARCH.md). Same lagged-season shape as home_war_prior/
-- home_oaa_prior -- raw.statcast_framing is a season aggregate, so a
-- team's current-season number used mid-season would leak every game
-- played after the one being predicted.

ALTER TABLE gold.game_feature ADD COLUMN home_framing_prior numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_framing_prior numeric;
