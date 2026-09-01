-- Rebuild gold.pitching_career from gold.pitching_season.
--
-- Relation 5 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Truncate-and-replace, transactional, idempotent.
--
-- Sums each player's per-season combined rows (is_combined = true) so a
-- traded season is counted once. Counting stats are plain sums; rate stats
-- recomputed from the career-total components (per-9 rates = component * 27
-- / outs; k_bb = SO / BB; every rate NULL on a zero denominator). RA9 not
-- ERA -- no earned runs at this grain.
--
-- The caller (report._build_backbone_relation) TRUNCATEs
-- gold.pitching_career first, in the same transaction.

WITH agg AS (
    SELECT
        player_id,
        count(*)    AS seasons,
        min(season) AS first_season,
        max(season) AS last_season,
        sum(g) AS g, sum(gs) AS gs, sum(bf) AS bf, sum(outs) AS outs,
        sum(h) AS h, sum(r) AS r, sum(bb) AS bb, sum(ibb) AS ibb,
        sum(so) AS so, sum(hr) AS hr, sum(hbp) AS hbp, sum(wp) AS wp,
        sum(bk) AS bk, sum(w) AS w, sum(l) AS l, sum(sv) AS sv
    FROM gold.pitching_season
    WHERE is_combined
    GROUP BY player_id
)
INSERT INTO gold.pitching_career (
    player_id, seasons, first_season, last_season, g,
    gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv,
    ra9, whip, k9, bb9, hr9, k_bb
)
SELECT
    player_id, seasons, first_season, last_season, g,
    gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv,
    CASE WHEN outs > 0 THEN r::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN (h + bb)::numeric * 3 / outs END,
    CASE WHEN outs > 0 THEN so::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN bb::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN hr::numeric * 27 / outs END,
    CASE WHEN bb > 0 THEN so::numeric / bb END
FROM agg;
