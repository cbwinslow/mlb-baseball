-- Rebuild gold.batting_team from gold.batting_game.
--
-- Relation 3 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Truncate-and-replace, transactional, idempotent. Optional %(season)s bind
-- scopes the rebuild to one season.
--
-- One row per (team, season): plain sums of the game lines, with rate stats
-- computed from this grain's summed components (same definitions as
-- gold.batting_season -- MLB glossary / FanGraphs, ISO = (TB - H) / AB,
-- every rate NULL on a zero denominator). SB, CS and the SB success rate
-- are absent (steals are not in gold.batting_game).
--
-- The caller (report._build_backbone_relation) TRUNCATEs gold.batting_team
-- first, in the same transaction.

WITH agg AS (
    SELECT
        team_id, season,
        count(DISTINCT game_id) AS g,
        sum(pa) AS pa, sum(ab) AS ab, sum(r) AS r, sum(h) AS h,
        sum(b1) AS b1, sum(b2) AS b2, sum(b3) AS b3, sum(hr) AS hr,
        sum(tb) AS tb, sum(rbi) AS rbi, sum(bb) AS bb, sum(ibb) AS ibb,
        sum(hbp) AS hbp, sum(sf) AS sf, sum(sh) AS sh, sum(so) AS so,
        sum(gidp) AS gidp
    FROM gold.batting_game
    WHERE (%(season)s::integer IS NULL OR season = %(season)s::integer)
    GROUP BY team_id, season
)
INSERT INTO gold.batting_team (
    team_id, season, g,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, gidp,
    avg, obp, slg, ops, iso, babip, bb_pct, k_pct
)
SELECT
    team_id, season, g,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, gidp,
    CASE WHEN ab > 0 THEN h::numeric / ab END,
    CASE WHEN (ab + bb + hbp + sf) > 0
         THEN (h + bb + hbp)::numeric / (ab + bb + hbp + sf) END,
    CASE WHEN ab > 0 THEN tb::numeric / ab END,
    CASE WHEN ab > 0 AND (ab + bb + hbp + sf) > 0
         THEN tb::numeric / ab + (h + bb + hbp)::numeric / (ab + bb + hbp + sf) END,
    CASE WHEN ab > 0 THEN (tb - h)::numeric / ab END,
    CASE WHEN (ab - so - hr + sf) > 0
         THEN (h - hr)::numeric / (ab - so - hr + sf) END,
    CASE WHEN pa > 0 THEN bb::numeric / pa END,
    CASE WHEN pa > 0 THEN so::numeric / pa END
FROM agg;
