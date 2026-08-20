-- Diagnostic health-check query for team prior rate statistics (ADR-061/062/063).
-- Both sides checked (issue #9 item 3): home and away go through the same
-- formula but two different join legs, so an away-only join bug is a real,
-- if unlikely, failure mode a home-only check can't surface. The final
-- home_pa/away_pa checks are a sanity guard against data corruption --
-- plate-appearance counts are never negative -- not an expected business
-- rule with edge cases to reason about. Bounds are named params, not
-- literals, so the enforced SQL bound and team_rate.py's reported Check
-- message can never drift apart (issue #32 follow-up finding).
--
-- Deliberately has no dependency on raw.retrosheet_event/retrosheet_gameinfo
-- (unlike team_rate_coverage_health_check.sql, its sibling) so it's always
-- safe to run even before those tables exist -- see team_rate.py::health_check.
SELECT
    count(*) FILTER (
        WHERE home_obp IS NOT NULL AND (home_obp < %(rate_min)s OR home_obp > %(rate_max)s)
    ),
    count(*) FILTER (
        WHERE home_slg IS NOT NULL AND (home_slg < %(slg_min)s OR home_slg > %(slg_max)s)
    ),
    count(*) FILTER (
        WHERE home_iso IS NOT NULL AND (home_iso < %(iso_min)s OR home_iso > %(iso_max)s)
    ),
    count(*) FILTER (
        WHERE home_babip IS NOT NULL AND (home_babip < %(rate_min)s OR home_babip > %(rate_max)s)
    ),
    count(*) FILTER (
        WHERE home_bb_pct IS NOT NULL AND (home_bb_pct < %(rate_min)s OR home_bb_pct > %(rate_max)s)
    ),
    count(*) FILTER (
        WHERE home_k_pct IS NOT NULL AND (home_k_pct < %(rate_min)s OR home_k_pct > %(rate_max)s)
    ),
    count(*) FILTER (
        WHERE home_runs_for_avg IS NOT NULL
        AND (home_runs_for_avg < %(runs_min)s OR home_runs_for_avg > %(runs_max)s)
    ),
    count(*) FILTER (
        WHERE home_runs_allowed_avg IS NOT NULL
        AND (home_runs_allowed_avg < %(runs_min)s OR home_runs_allowed_avg > %(runs_max)s)
    ),
    count(*) FILTER (
        WHERE home_obp IS NOT NULL AND (home_pa IS NULL OR home_pa < %(min_pa)s)
    ),
    count(*) FILTER (
        WHERE home_pa IS NOT NULL AND home_pa < 0
    ),
    count(*) FILTER (
        WHERE away_obp IS NOT NULL AND (away_obp < %(rate_min)s OR away_obp > %(rate_max)s)
    ),
    count(*) FILTER (
        WHERE away_slg IS NOT NULL AND (away_slg < %(slg_min)s OR away_slg > %(slg_max)s)
    ),
    count(*) FILTER (
        WHERE away_iso IS NOT NULL AND (away_iso < %(iso_min)s OR away_iso > %(iso_max)s)
    ),
    count(*) FILTER (
        WHERE away_babip IS NOT NULL AND (away_babip < %(rate_min)s OR away_babip > %(rate_max)s)
    ),
    count(*) FILTER (
        WHERE away_bb_pct IS NOT NULL AND (away_bb_pct < %(rate_min)s OR away_bb_pct > %(rate_max)s)
    ),
    count(*) FILTER (
        WHERE away_k_pct IS NOT NULL AND (away_k_pct < %(rate_min)s OR away_k_pct > %(rate_max)s)
    ),
    count(*) FILTER (
        WHERE away_runs_for_avg IS NOT NULL
        AND (away_runs_for_avg < %(runs_min)s OR away_runs_for_avg > %(runs_max)s)
    ),
    count(*) FILTER (
        WHERE away_runs_allowed_avg IS NOT NULL
        AND (away_runs_allowed_avg < %(runs_min)s OR away_runs_allowed_avg > %(runs_max)s)
    ),
    count(*) FILTER (
        WHERE away_obp IS NOT NULL AND (away_pa IS NULL OR away_pa < %(min_pa)s)
    ),
    count(*) FILTER (
        WHERE away_pa IS NOT NULL AND away_pa < 0
    )
FROM gold.game_feature;
