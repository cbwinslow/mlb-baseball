-- Rebuild gold.pitching_postseason from raw.lahman_pitching_post.
--
-- separate-postseason-stats change (ADR-282). Truncate-and-replace,
-- transactional, idempotent. Optional %(season)s bind scopes the rebuild to one
-- season; NULL rebuilds every season. The caller
-- (report._build_backbone_relation) TRUNCATEs gold.pitching_postseason first,
-- in the same transaction.
--
-- Lineage: Lahman PitchingPost (1884+). playerid -> core.player.bbref_id,
-- falling back to raw.lahman_people.retroid -> core.player.retro_id
-- (~0.9997 resolve). teamid + yearid -> raw.lahman_teams.teamidretro ->
-- core.team.retro_team_id. Unresolved rows are dropped here and counted by a
-- report health check.
--
-- Three row kinds (see migration 0100): per-round, combined (per player-season),
-- career (per player). Lahman IPouts -> outs; per-9 rates multiply by 27 / outs.
-- Unlike gold.pitching_season, PitchingPost carries ER, so ERA is real.

WITH src AS (
    SELECT
        coalesce(pd.id, pr.id) AS player_id,
        t.id AS team_id,
        pp.yearid::integer AS season,
        pp.round AS round,
        coalesce(nullif(pp.g,     '')::integer, 0) AS g,
        coalesce(nullif(pp.gs,    '')::integer, 0) AS gs,
        coalesce(nullif(pp.cg,    '')::integer, 0) AS cg,
        coalesce(nullif(pp.sho,   '')::integer, 0) AS sho,
        coalesce(nullif(pp.bfp,   '')::integer, 0) AS bf,
        coalesce(nullif(pp.ipouts,'')::integer, 0) AS outs,
        coalesce(nullif(pp.h,     '')::integer, 0) AS h,
        coalesce(nullif(pp.r,     '')::integer, 0) AS r,
        coalesce(nullif(pp.er,    '')::integer, 0) AS er,
        coalesce(nullif(pp.bb,    '')::integer, 0) AS bb,
        coalesce(nullif(pp.ibb,   '')::integer, 0) AS ibb,
        coalesce(nullif(pp.so,    '')::integer, 0) AS so,
        coalesce(nullif(pp.hr,    '')::integer, 0) AS hr,
        coalesce(nullif(pp.hbp,   '')::integer, 0) AS hbp,
        coalesce(nullif(pp.wp,    '')::integer, 0) AS wp,
        coalesce(nullif(pp.bk,    '')::integer, 0) AS bk,
        coalesce(nullif(pp.w,     '')::integer, 0) AS w,
        coalesce(nullif(pp.l,     '')::integer, 0) AS l,
        coalesce(nullif(pp.sv,    '')::integer, 0) AS sv
    FROM raw.lahman_pitching_post pp
    LEFT JOIN core.player pd ON pd.bbref_id = pp.playerid
    LEFT JOIN raw.lahman_people lp
        ON lp.playerid = pp.playerid AND lp.retroid <> '' AND pd.id IS NULL
    LEFT JOIN core.player pr ON pr.retro_id = lp.retroid
    JOIN raw.lahman_teams lt ON lt.teamid = pp.teamid AND lt.yearid = pp.yearid
    JOIN core.team t ON t.retro_team_id = lt.teamidretro
        AND pp.yearid::integer BETWEEN t.first_year AND t.last_year
    WHERE coalesce(pd.id, pr.id) IS NOT NULL
      AND (%(season)s::integer IS NULL OR pp.yearid::integer = %(season)s::integer)
),
agg AS (
    SELECT
        player_id, season, round, team_id,
        false AS is_combined, false AS is_career,
        sum(g) AS g, sum(gs) AS gs, sum(cg) AS cg, sum(sho) AS sho, sum(bf) AS bf,
        sum(outs) AS outs, sum(h) AS h, sum(r) AS r, sum(er) AS er, sum(bb) AS bb,
        sum(ibb) AS ibb, sum(so) AS so, sum(hr) AS hr, sum(hbp) AS hbp,
        sum(wp) AS wp, sum(bk) AS bk, sum(w) AS w, sum(l) AS l, sum(sv) AS sv
    FROM src
    GROUP BY player_id, season, round, team_id
    UNION ALL
    SELECT
        player_id, season, NULL::text AS round, NULL::bigint AS team_id,
        true AS is_combined, false AS is_career,
        sum(g), sum(gs), sum(cg), sum(sho), sum(bf),
        sum(outs), sum(h), sum(r), sum(er), sum(bb),
        sum(ibb), sum(so), sum(hr), sum(hbp),
        sum(wp), sum(bk), sum(w), sum(l), sum(sv)
    FROM src
    GROUP BY player_id, season
    UNION ALL
    SELECT
        player_id, NULL::integer AS season, NULL::text AS round, NULL::bigint AS team_id,
        false AS is_combined, true AS is_career,
        sum(g), sum(gs), sum(cg), sum(sho), sum(bf),
        sum(outs), sum(h), sum(r), sum(er), sum(bb),
        sum(ibb), sum(so), sum(hr), sum(hbp),
        sum(wp), sum(bk), sum(w), sum(l), sum(sv)
    FROM src
    GROUP BY player_id
)
INSERT INTO gold.pitching_postseason (
    player_id, season, round, team_id, is_combined, is_career, g,
    gs, cg, sho, bf, outs, h, r, er, bb, ibb, so, hr, hbp, wp, bk, w, l, sv,
    era, ra9, whip, k9, bb9, hr9, k_bb
)
SELECT
    player_id, season, round, team_id, is_combined, is_career, g,
    gs, cg, sho, bf, outs, h, r, er, bb, ibb, so, hr, hbp, wp, bk, w, l, sv,
    CASE WHEN outs > 0 THEN er::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN r::numeric  * 27 / outs END,
    CASE WHEN outs > 0 THEN (h + bb)::numeric * 3 / outs END,
    CASE WHEN outs > 0 THEN so::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN bb::numeric * 27 / outs END,
    CASE WHEN outs > 0 THEN hr::numeric * 27 / outs END,
    CASE WHEN bb > 0 THEN so::numeric / bb END
FROM agg;
