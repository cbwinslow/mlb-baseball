-- Links every resolvable core.team era-row to its franchise. A
-- raw.lahman_teams row is matched to the specific era whose year it falls
-- within (first_year..last_year), not just by code, so a code Retrosheet
-- reused across two distinct eras (e.g. HOU 1962-2012 NL vs 2013-2021 AL,
-- MIL 1970-1997 AL vs 1998-2021 NL -- both real, per ADR-013) links each
-- era to the correct franchise rather than an ambiguous code-only match.
-- A core.team row with no matching raw.lahman_teams row (a real, documented
-- gap -- pre-1969 Negro League team-eras Lahman's franchise data does not
-- cover) is left with franchise_id NULL, not guessed.
UPDATE core.team t
SET franchise_id = tf.id
FROM raw.lahman_teams lt
JOIN core.team_franchise tf ON tf.franchise_id = lt.franchid
WHERE t.retro_team_id = lt.teamidretro
  AND lt.yearid::integer BETWEEN t.first_year AND t.last_year;
