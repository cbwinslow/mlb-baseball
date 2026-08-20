-- Plausible range checks for team wOBA and wRC+, both sides (issue #9 item 3:
-- only home_* was checked here for a long time -- home and away go through
-- the same formula but two different join legs, so an away-only join bug
-- (e.g. a mismatched team_id) is a real, if unlikely, failure mode this
-- didn't previously surface at all). Bounds are named params, not literals,
-- so the enforced SQL bound and offense.py's reported Check message can
-- never drift apart (issue #32 follow-up finding).
--
-- Deliberately has no dependency on raw.retrosheet_event/retrosheet_gameinfo
-- (unlike offense_coverage_health_check.sql, its sibling) so it's always
-- safe to run even before those tables exist -- see offense.py::health_check.
SELECT
    count(*) FILTER (
        WHERE home_woba IS NOT NULL AND (home_woba < %(woba_min)s OR home_woba > %(woba_max)s)
    ),
    count(*) FILTER (
        WHERE home_wrc_plus IS NOT NULL
        AND (home_wrc_plus < %(wrc_min)s OR home_wrc_plus > %(wrc_max)s)
    ),
    count(*) FILTER (
        WHERE away_woba IS NOT NULL AND (away_woba < %(woba_min)s OR away_woba > %(woba_max)s)
    ),
    count(*) FILTER (
        WHERE away_wrc_plus IS NOT NULL
        AND (away_wrc_plus < %(wrc_min)s OR away_wrc_plus > %(wrc_max)s)
    )
FROM gold.game_feature;
