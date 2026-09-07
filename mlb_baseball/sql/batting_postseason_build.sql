-- Rebuild gold.batting_postseason from raw.lahman_batting_post.
--
-- separate-postseason-stats change (ADR-282). Truncate-and-replace,
-- transactional, idempotent. Optional %(season)s bind scopes the rebuild to one
-- season; NULL rebuilds every season. The caller
-- (report._build_backbone_relation) TRUNCATEs gold.batting_postseason first, in
-- the same transaction.
--
-- Lineage: Lahman BattingPost (1884+). playerid -> core.player.bbref_id
-- (Lahman playerID is the Baseball-Reference id), falling back to
-- raw.lahman_people.retroid -> core.player.retro_id for the recent debuts
-- whose bbref id is not in core.player yet (~0.999 resolve overall). teamid +
-- yearid -> raw.lahman_teams.teamidretro -> core.team.retro_team_id. Rows whose
-- player or team id does not resolve are dropped here and counted by a report
-- health check (never silently ignored).
--
-- Three row kinds (see migration 0100):
--   * per-round : is_combined = false, is_career = false, one per
--                 (player, season, round, team). `round` kept verbatim.
--   * combined  : is_combined = true, one per (player, season), all rounds.
--   * career    : is_career = true, one per (player), all seasons.
--
-- Lahman BattingPost has no PA column; PA = AB + BB + HBP + SF + SH.
-- Singles b1 = H - 2B - 3B - HR; TB = H + 2B + 2*3B + 3*HR.
--
-- raw.lahman_batting_post columns are text and pandas float-formats any
-- nullable integer column ("4.0", not "4") whenever the source left blanks in
-- that column -- so cast via ::numeric::integer, not ::integer directly.

WITH src AS (
    SELECT
        coalesce(pd.id, pr.id) AS player_id,
        t.id AS team_id,
        bp.yearid::integer AS season,
        bp.round AS round,
        coalesce(nullif(bp.g,   '')::numeric::integer, 0) AS g,
        coalesce(nullif(bp.ab,  '')::numeric::integer, 0) AS ab,
        coalesce(nullif(bp.r,   '')::numeric::integer, 0) AS r,
        coalesce(nullif(bp.h,   '')::numeric::integer, 0) AS h,
        coalesce(nullif(bp.n2b, '')::numeric::integer, 0) AS b2,
        coalesce(nullif(bp.n3b, '')::numeric::integer, 0) AS b3,
        coalesce(nullif(bp.hr,  '')::numeric::integer, 0) AS hr,
        coalesce(nullif(bp.rbi, '')::numeric::integer, 0) AS rbi,
        coalesce(nullif(bp.sb,  '')::numeric::integer, 0) AS sb,
        coalesce(nullif(bp.cs,  '')::numeric::integer, 0) AS cs,
        coalesce(nullif(bp.bb,  '')::numeric::integer, 0) AS bb,
        coalesce(nullif(bp.ibb, '')::numeric::integer, 0) AS ibb,
        coalesce(nullif(bp.hbp, '')::numeric::integer, 0) AS hbp,
        coalesce(nullif(bp.sf,  '')::numeric::integer, 0) AS sf,
        coalesce(nullif(bp.sh,  '')::numeric::integer, 0) AS sh,
        coalesce(nullif(bp.so,  '')::numeric::integer, 0) AS so,
        coalesce(nullif(bp.gidp,'')::numeric::integer, 0) AS gidp
    FROM raw.lahman_batting_post bp
    LEFT JOIN core.player pd ON pd.bbref_id = bp.playerid
    LEFT JOIN raw.lahman_people lp
        ON lp.playerid = bp.playerid AND lp.retroid <> '' AND pd.id IS NULL
    LEFT JOIN core.player pr ON pr.retro_id = lp.retroid
    JOIN raw.lahman_teams lt ON lt.teamid = bp.teamid AND lt.yearid = bp.yearid
    JOIN core.team t ON t.retro_team_id = lt.teamidretro
        AND bp.yearid::integer BETWEEN t.first_year AND t.last_year
    WHERE coalesce(pd.id, pr.id) IS NOT NULL
      AND (%(season)s::integer IS NULL OR bp.yearid::integer = %(season)s::integer)
),
agg AS (
    -- per-round
    SELECT
        player_id, season, round, team_id,
        false AS is_combined, false AS is_career,
        sum(g) AS g, sum(ab) AS ab, sum(r) AS r, sum(h) AS h,
        sum(b2) AS b2, sum(b3) AS b3, sum(hr) AS hr, sum(rbi) AS rbi,
        sum(sb) AS sb, sum(cs) AS cs, sum(bb) AS bb, sum(ibb) AS ibb,
        sum(hbp) AS hbp, sum(sf) AS sf, sum(sh) AS sh, sum(so) AS so, sum(gidp) AS gidp
    FROM src
    GROUP BY player_id, season, round, team_id
    UNION ALL
    -- combined: one per (player, season)
    SELECT
        player_id, season, NULL::text AS round, NULL::bigint AS team_id,
        true AS is_combined, false AS is_career,
        sum(g), sum(ab), sum(r), sum(h),
        sum(b2), sum(b3), sum(hr), sum(rbi),
        sum(sb), sum(cs), sum(bb), sum(ibb),
        sum(hbp), sum(sf), sum(sh), sum(so), sum(gidp)
    FROM src
    GROUP BY player_id, season
    UNION ALL
    -- career: one per (player)
    SELECT
        player_id, NULL::integer AS season, NULL::text AS round, NULL::bigint AS team_id,
        false AS is_combined, true AS is_career,
        sum(g), sum(ab), sum(r), sum(h),
        sum(b2), sum(b3), sum(hr), sum(rbi),
        sum(sb), sum(cs), sum(bb), sum(ibb),
        sum(hbp), sum(sf), sum(sh), sum(so), sum(gidp)
    FROM src
    GROUP BY player_id
),
shaped AS (
    SELECT
        player_id, season, round, team_id, is_combined, is_career, g,
        (ab + bb + hbp + sf + sh) AS pa,
        ab, r, h,
        (h - b2 - b3 - hr) AS b1, b2, b3, hr,
        (h + b2 + 2 * b3 + 3 * hr) AS tb,
        rbi, sb, cs, bb, ibb, hbp, sf, sh, so, gidp
    FROM agg
)
INSERT INTO gold.batting_postseason (
    player_id, season, round, team_id, is_combined, is_career, g,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, sb, cs, bb, ibb, hbp, sf, sh, so, gidp,
    avg, obp, slg, ops, iso, babip, bb_pct, k_pct
)
SELECT
    player_id, season, round, team_id, is_combined, is_career, g,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, sb, cs, bb, ibb, hbp, sf, sh, so, gidp,
    CASE WHEN ab > 0 THEN h::numeric / ab END,
    CASE WHEN (ab + bb + hbp + sf) > 0
         THEN (h + bb + hbp)::numeric / (ab + bb + hbp + sf) END,
    CASE WHEN ab > 0 THEN tb::numeric / ab END,
    CASE WHEN ab > 0
         THEN tb::numeric / ab + (h + bb + hbp)::numeric / (ab + bb + hbp + sf) END,
    CASE WHEN ab > 0 THEN (tb - h)::numeric / ab END,
    CASE WHEN (ab - so - hr + sf) > 0
         THEN (h - hr)::numeric / (ab - so - hr + sf) END,
    CASE WHEN pa > 0 THEN bb::numeric / pa END,
    CASE WHEN pa > 0 THEN so::numeric / pa END
FROM shaped;
