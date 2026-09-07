-- serve.ros_team_standings counted EVERY completed game -- regular season,
-- postseason, spring training, exhibition -- so a playoff team's row showed
-- 200+ games and a wildly inflated win total (2023 TEX: 210 GP / 116 W vs the
-- real 162 / 90). It is "in-season team standings", which by definition is
-- regular season only.
--
-- Part of separate-postseason-stats (ADR-282 / ADR-283): every relation and
-- view that aggregates game-level performance scopes game_type explicitly. A
-- game counts iff its game_type is 'regular' or 'playoff' (the Game 163
-- tiebreaker, which counts as regular season -- baseball.computer's
-- seed_game_types convention).
--
-- Only the `completed` CTE changes; the rest of the view is byte-identical.

CREATE OR REPLACE VIEW serve.ros_team_standings AS
WITH completed AS (
    SELECT
        EXTRACT(YEAR FROM g.game_date)::INTEGER AS season,
        g.home_team_id,
        g.away_team_id,
        g.home_score,
        g.away_score,
        CASE WHEN g.home_score > g.away_score THEN 1 ELSE 0 END AS home_win,
        CASE WHEN g.away_score > g.home_score THEN 1 ELSE 0 END AS away_win
    FROM core.game g
    WHERE g.home_score IS NOT NULL AND g.away_score IS NOT NULL
      AND g.game_type IN ('regular', 'playoff')
),
team_records AS (
    SELECT
        season,
        home_team_id AS team_id,
        home_win AS win,
        away_win AS loss,
        home_score AS runs_for,
        away_score AS runs_against
    FROM completed
    UNION ALL
    SELECT
        season,
        away_team_id AS team_id,
        away_win AS win,
        home_win AS loss,
        away_score AS runs_for,
        home_score AS runs_against
    FROM completed
)
SELECT
    tr.season,
    t.id AS team_id,
    t.retro_team_id AS team_code,
    NULLIF(CONCAT_WS(' ', t.city, t.nickname), '') AS team_name,
    t.league,
    NULL::text AS division,
    COUNT(*)::INTEGER AS games_played,
    SUM(tr.win)::INTEGER AS wins,
    SUM(tr.loss)::INTEGER AS losses,
    ROUND(SUM(tr.win)::NUMERIC / NULLIF(COUNT(*), 0), 3) AS win_pct,
    SUM(tr.runs_for)::INTEGER AS runs_for,
    SUM(tr.runs_against)::INTEGER AS runs_against,
    (SUM(tr.runs_for) - SUM(tr.runs_against))::INTEGER AS run_differential,
    ROUND(
        POWER(SUM(tr.runs_for)::NUMERIC, 1.83) /
        NULLIF(POWER(SUM(tr.runs_for)::NUMERIC, 1.83) + POWER(SUM(tr.runs_against)::NUMERIC, 1.83), 0),
        3
    ) AS pythagorean_win_pct
FROM team_records tr
JOIN core.team t ON t.id = tr.team_id
GROUP BY tr.season, t.id, t.retro_team_id, t.city, t.nickname, t.league;

COMMENT ON VIEW serve.ros_team_standings IS 'In-season (regular-season-only) team standings, run differentials, and Pythagorean win expectations (SERVE-02; game-type scoped per ADR-283).';
