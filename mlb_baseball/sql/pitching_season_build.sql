-- Rebuild gold.pitching_season from gold.pitching_game.
--
-- Relation 4 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Truncate-and-replace, transactional, idempotent. Optional %(season)s bind
-- scopes the rebuild to one season; NULL rebuilds every season.
--
-- Two row kinds, both grouped straight off gold.pitching_game (never rolled
-- up from each other):
--   * is_combined = false: one per (player, season, team) -- the stint line.
--   * is_combined = true:  one per (player, season), team_id NULL -- the
--     full-season line. For a one-team pitcher it equals the single stint.
--
-- Counting stats are plain sums. Rate stats are computed from THIS grain's
-- summed components and are NULL when the denominator is 0 (MLB glossary /
-- FanGraphs; IP = outs / 3, so per-9-innings rates multiply by 27 / outs).
-- RA9 (runs allowed per 9) is produced, NOT ERA -- gold.pitching_game has no
-- earned runs.
--
-- The caller (report._build_backbone_relation) TRUNCATEs gold.pitching_season
-- first, in the same transaction.

WITH scoped AS (
    SELECT *
    FROM gold.pitching_game
    WHERE (%(season)s::integer IS NULL OR season = %(season)s::integer)
),
stint AS (
    SELECT
        player_id, season, team_id, false AS is_combined,
        count(DISTINCT game_id) AS g,
        sum(gs) AS gs, sum(bf) AS bf, sum(outs) AS outs, sum(h) AS h, sum(r) AS r,
        sum(bb) AS bb, sum(ibb) AS ibb, sum(so) AS so, sum(hr) AS hr,
        sum(hbp) AS hbp, sum(wp) AS wp, sum(bk) AS bk,
        sum(w) AS w, sum(l) AS l, sum(sv) AS sv
    FROM scoped
    GROUP BY player_id, season, team_id
),
combined AS (
    SELECT
        player_id, season, NULL::bigint AS team_id, true AS is_combined,
        count(DISTINCT game_id) AS g,
        sum(gs) AS gs, sum(bf) AS bf, sum(outs) AS outs, sum(h) AS h, sum(r) AS r,
        sum(bb) AS bb, sum(ibb) AS ibb, sum(so) AS so, sum(hr) AS hr,
        sum(hbp) AS hbp, sum(wp) AS wp, sum(bk) AS bk,
        sum(w) AS w, sum(l) AS l, sum(sv) AS sv
    FROM scoped
    GROUP BY player_id, season
),
allrows AS (
    SELECT * FROM stint
    UNION ALL
    SELECT * FROM combined
)
INSERT INTO gold.pitching_season (
    player_id, season, team_id, is_combined, g,
    gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv,
    ra9, whip, k9, bb9, hr9, k_bb
)
SELECT
    player_id, season, team_id, is_combined, g,
    gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv,
    CASE WHEN outs > 0 THEN r::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN (h + bb)::numeric * 3 / outs END,
    CASE WHEN outs > 0 THEN so::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN bb::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN hr::numeric * 27 / outs END,
    CASE WHEN bb > 0 THEN so::numeric / bb END
FROM allrows;
