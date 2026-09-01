-- Rebuild gold.batting_career from gold.batting_season.
--
-- Relation 5 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Truncate-and-replace, transactional, idempotent.
--
-- Sums each player's per-season combined rows (is_combined = true, one per
-- player-season) so a traded season is counted once, not once per stint.
-- Counting stats are plain sums; rate stats are recomputed from the
-- career-total components -- a career AVG is total H / total AB -- and are
-- NULL on a zero denominator (same definitions as gold.batting_season;
-- ISO = (TB - H) / AB).
--
-- The caller (report._build_backbone_relation) TRUNCATEs gold.batting_career
-- first, in the same transaction.

WITH agg AS (
    SELECT
        player_id,
        count(*)    AS seasons,
        min(season) AS first_season,
        max(season) AS last_season,
        sum(g) AS g, sum(pa) AS pa, sum(ab) AS ab, sum(r) AS r, sum(h) AS h,
        sum(b1) AS b1, sum(b2) AS b2, sum(b3) AS b3, sum(hr) AS hr,
        sum(tb) AS tb, sum(rbi) AS rbi, sum(bb) AS bb, sum(ibb) AS ibb,
        sum(hbp) AS hbp, sum(sf) AS sf, sum(sh) AS sh, sum(so) AS so,
        sum(gidp) AS gidp
    FROM gold.batting_season
    WHERE is_combined
    GROUP BY player_id
)
INSERT INTO gold.batting_career (
    player_id, seasons, first_season, last_season, g,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, gidp,
    avg, obp, slg, ops, iso, babip, bb_pct, k_pct
)
SELECT
    player_id, seasons, first_season, last_season, g,
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
