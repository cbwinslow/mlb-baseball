-- Diagnostic health-check query for team prior stolen-base run value
-- (wSB, BSR-01, ADR-081). Same shape as team_rate_health_check.sql: both
-- sides checked independently (home/away go through the same formula but
-- two different join legs), bounds passed as named params so the
-- enforced SQL bound and bsr.py's reported Check message can never drift
-- apart, and this file has no dependency on raw.retrosheet_event/
-- retrosheet_gameinfo so it's always safe to run before those tables
-- exist -- see mlb_baseball/model/bsr.py::health_check.
--
-- wsb_min/wsb_max are deliberately generous (not derived from any
-- citation) -- a real season-total wSB for even the best base-stealing
-- teams rarely exceeds +/-10 runs, and this checks an *entering*,
-- partial-season value, which can swing further on a small early-season
-- sample under MIN_ATTEMPTS's own gate.
SELECT
    count(*) FILTER (
        WHERE home_wsb IS NOT NULL AND (home_wsb < %(wsb_min)s OR home_wsb > %(wsb_max)s)
    ),
    count(*) FILTER (
        WHERE home_wsb IS NOT NULL
        AND (COALESCE(home_sb, 0) + COALESCE(home_cs, 0)) < %(min_attempts)s
    ),
    count(*) FILTER (WHERE home_sb IS NOT NULL AND home_sb < 0),
    count(*) FILTER (WHERE home_cs IS NOT NULL AND home_cs < 0),
    count(*) FILTER (
        WHERE away_wsb IS NOT NULL AND (away_wsb < %(wsb_min)s OR away_wsb > %(wsb_max)s)
    ),
    count(*) FILTER (
        WHERE away_wsb IS NOT NULL
        AND (COALESCE(away_sb, 0) + COALESCE(away_cs, 0)) < %(min_attempts)s
    ),
    count(*) FILTER (WHERE away_sb IS NOT NULL AND away_sb < 0),
    count(*) FILTER (WHERE away_cs IS NOT NULL AND away_cs < 0)
FROM gold.game_feature;
