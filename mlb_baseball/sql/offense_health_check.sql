-- Plausible range checks for team wOBA and wRC+, both sides (issue #9 item 3:
-- only home_* was checked here for a long time -- home and away go through
-- the same formula but two different join legs, so an away-only join bug
-- (e.g. a mismatched team_id) is a real, if unlikely, failure mode this
-- didn't previously surface at all).
SELECT
    count(*) FILTER (
        WHERE home_woba IS NOT NULL AND (home_woba < 0.02 OR home_woba > 0.70)
    ),
    count(*) FILTER (
        WHERE home_wrc_plus IS NOT NULL AND (home_wrc_plus < 20 OR home_wrc_plus > 250)
    ),
    count(*) FILTER (
        WHERE away_woba IS NOT NULL AND (away_woba < 0.02 OR away_woba > 0.70)
    ),
    count(*) FILTER (
        WHERE away_wrc_plus IS NOT NULL AND (away_wrc_plus < 20 OR away_wrc_plus > 250)
    )
FROM gold.game_feature;
