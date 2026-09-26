-- One row per real franchise (Lahman's own franchid), not per team-era.
--
-- current_retro_team_id is the retro_team_id of the resolved core.team row
-- with the greatest first_year for that franchise -- NOT whichever era
-- core.team.last_year happens to mark active (its 9999 "currently active"
-- sentinel reflects Retrosheet's own source file, which can lag a real
-- code reissue -- confirmed directly for the Athletics' 2025 relocation:
-- the retired 'OAK' code is still last_year = 9999 while 'ATH' is real).
-- Only for a consumer that specifically needs the franchise's real,
-- current code with no season/year context of its own (see migration
-- 0107's comment) -- season-scoped consumers must resolve each row to its
-- OWN era directly instead (core.team's own retro_team_id/year-range
-- columns already do that correctly).
--
-- The inner subquery first collapses raw.lahman_teams down to distinct
-- (franchid, teamidretro) pairs -- raw.lahman_teams has one row per
-- franchise-YEAR, so joining it to core.team directly would fan out one
-- row per year for no benefit; only the distinct code matters here.
INSERT INTO core.team_franchise (franchise_id, franchise_name, current_retro_team_id)
SELECT DISTINCT ON (lf.franchid)
    lf.franchid,
    lf.franchname,
    t.retro_team_id
FROM raw.lahman_teams_franchises lf
JOIN (SELECT DISTINCT franchid, teamidretro FROM raw.lahman_teams) lt
    ON lt.franchid = lf.franchid
JOIN core.team t ON t.retro_team_id = lt.teamidretro
ORDER BY lf.franchid, t.first_year DESC;
