-- Rebuild gold.batting_season from gold.batting_game.
--
-- Relation 3 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Truncate-and-replace, transactional, idempotent. Optional %(season)s bind
-- scopes the rebuild to one season; NULL rebuilds every season.
--
-- Two row kinds, both grouped straight off gold.batting_game (never rolled
-- up from each other, so a game a traded player split across two clubs is
-- counted once in each):
--   * is_combined = false: one per (player, season, team) -- the stint line.
--   * is_combined = true:  one per (player, season), team_id NULL -- the
--     full-season line. For a one-team player it equals the single stint.
--
-- Counting stats are plain sums. Rate stats are computed from THIS grain's
-- summed components -- a season AVG is total H / total AB, never the mean of
-- game AVGs. Every rate is NULL when its denominator is 0 (MLB glossary /
-- FanGraphs definitions; ISO = SLG - AVG = (TB - H) / AB).
--
-- SB, CS and the SB success rate are absent: gold.batting_game does not
-- carry steals (baserunning, deferred to gold.baserunning_game).
--
-- The caller (report._build_backbone_relation) TRUNCATEs gold.batting_season
-- first, in the same transaction.

WITH scoped AS (
    SELECT *
    FROM gold.batting_game
    WHERE (%(season)s::integer IS NULL OR season = %(season)s::integer)
),
stint AS (
    SELECT
        player_id, season, team_id, false AS is_combined,
        count(DISTINCT game_id) AS g,
        sum(pa) AS pa, sum(ab) AS ab, sum(r) AS r, sum(h) AS h,
        sum(b1) AS b1, sum(b2) AS b2, sum(b3) AS b3, sum(hr) AS hr,
        sum(tb) AS tb, sum(rbi) AS rbi, sum(bb) AS bb, sum(ibb) AS ibb,
        sum(hbp) AS hbp, sum(sf) AS sf, sum(sh) AS sh, sum(so) AS so,
        sum(gidp) AS gidp
    FROM scoped
    GROUP BY player_id, season, team_id
),
combined AS (
    SELECT
        player_id, season, NULL::bigint AS team_id, true AS is_combined,
        count(DISTINCT game_id) AS g,
        sum(pa) AS pa, sum(ab) AS ab, sum(r) AS r, sum(h) AS h,
        sum(b1) AS b1, sum(b2) AS b2, sum(b3) AS b3, sum(hr) AS hr,
        sum(tb) AS tb, sum(rbi) AS rbi, sum(bb) AS bb, sum(ibb) AS ibb,
        sum(hbp) AS hbp, sum(sf) AS sf, sum(sh) AS sh, sum(so) AS so,
        sum(gidp) AS gidp
    FROM scoped
    GROUP BY player_id, season
),
allrows AS (
    SELECT * FROM stint
    UNION ALL
    SELECT * FROM combined
)
INSERT INTO gold.batting_season (
    player_id, season, team_id, is_combined, g,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, gidp,
    avg, obp, slg, ops, iso, babip, bb_pct, k_pct
)
SELECT
    player_id, season, team_id, is_combined, g,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, gidp,
    CASE WHEN ab > 0 THEN h::numeric / ab END,
    CASE WHEN (ab + bb + hbp + sf) > 0
         THEN (h + bb + hbp)::numeric / (ab + bb + hbp + sf) END,
    CASE WHEN ab > 0 THEN tb::numeric / ab END,
    CASE WHEN ab > 0   -- ab>0 already implies (ab+bb+hbp+sf)>0
         THEN tb::numeric / ab + (h + bb + hbp)::numeric / (ab + bb + hbp + sf) END,
    CASE WHEN ab > 0 THEN (tb - h)::numeric / ab END,
    CASE WHEN (ab - so - hr + sf) > 0
         THEN (h - hr)::numeric / (ab - so - hr + sf) END,
    CASE WHEN pa > 0 THEN bb::numeric / pa END,
    CASE WHEN pa > 0 THEN so::numeric / pa END
FROM allrows;
