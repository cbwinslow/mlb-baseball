-- One row per real franchise (Lahman's own franchid), not per team-era.
--
-- current_retro_team_id is the retro_team_id of the resolved core.team row
-- with the greatest first_year for that franchise -- NOT whichever era
-- core.team.last_year happens to mark active (its 9999 "currently active"
-- sentinel reflects Retrosheet's own source file, which can lag a real
-- code reissue -- confirmed directly for the Athletics' 2025 relocation:
-- the retired 'OAK' code is still last_year = 9999 while 'ATH' is real).
-- Used where a consumer needs the franchise's real, current code (e.g.
-- resolving an external source's current-season ticker/alias).
--
-- legacy_retro_team_id is the retro_team_id of the resolved core.team row
-- with the SMALLEST first_year -- the franchise's original/oldest code.
-- Used where a consumer already has its own established convention keyed
-- on that older code and a relocation must not silently break it (e.g.
-- gold.team_season's team_id stability, or a still-hardcoded team list
-- elsewhere in the codebase) -- see migration 0107's comment.
--
-- The inner subquery first collapses raw.lahman_teams down to distinct
-- (franchid, teamidretro) pairs -- raw.lahman_teams has one row per
-- franchise-YEAR, so joining it to core.team directly would fan out one
-- row per year for no benefit; only the distinct code matters here.
INSERT INTO core.team_franchise (
    franchise_id, franchise_name, current_retro_team_id, legacy_retro_team_id
)
SELECT DISTINCT
    lf.franchid,
    lf.franchname,
    first_value(t.retro_team_id) OVER (PARTITION BY lf.franchid ORDER BY t.first_year DESC),
    first_value(t.retro_team_id) OVER (PARTITION BY lf.franchid ORDER BY t.first_year ASC)
FROM raw.lahman_teams_franchises lf
JOIN (SELECT DISTINCT franchid, teamidretro FROM raw.lahman_teams) lt
    ON lt.franchid = lf.franchid
JOIN core.team t ON t.retro_team_id = lt.teamidretro;
