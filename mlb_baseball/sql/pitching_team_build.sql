-- Rebuild gold.pitching_team from gold.pitching_game.
--
-- Relation 4 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Truncate-and-replace, transactional, idempotent. Optional %(season)s bind
-- scopes the rebuild to one season.
--
-- One row per (team, season): plain sums of the game lines, with rate stats
-- computed from this grain's summed components (same definitions as
-- gold.pitching_season -- MLB glossary / FanGraphs, per-9-innings rates
-- multiply by 27 / outs, every rate NULL on a zero denominator; RA9 not
-- ERA).
--
-- The caller (report._build_backbone_relation) TRUNCATEs gold.pitching_team
-- first, in the same transaction.

WITH agg AS (
    SELECT
        team_id, season,
        count(DISTINCT game_id) AS g,
        sum(gs) AS gs, sum(bf) AS bf, sum(outs) AS outs, sum(h) AS h, sum(r) AS r,
        sum(bb) AS bb, sum(ibb) AS ibb, sum(so) AS so, sum(hr) AS hr,
        sum(hbp) AS hbp, sum(wp) AS wp, sum(bk) AS bk,
        sum(w) AS w, sum(l) AS l, sum(sv) AS sv
    FROM gold.pitching_game
    WHERE (%(season)s::integer IS NULL OR season = %(season)s::integer)
    GROUP BY team_id, season
)
INSERT INTO gold.pitching_team (
    team_id, season, g,
    gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv,
    ra9, whip, k9, bb9, hr9, k_bb
)
SELECT
    team_id, season, g,
    gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv,
    CASE WHEN outs > 0 THEN r::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN (h + bb)::numeric * 3 / outs END,
    CASE WHEN outs > 0 THEN so::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN bb::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN hr::numeric * 27 / outs END,
    CASE WHEN bb > 0 THEN so::numeric / bb END
FROM agg;
