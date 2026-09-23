-- Adds core.team_franchise (one row per real MLB franchise, not per
-- team-era) and core.team.franchise_id, linking every team-era row to its
-- permanent franchise. See docs/DECISIONS.md ADR-<team-franchise-crosswalk>
-- and openspec/changes/team-franchise-crosswalk/.
--
-- core.team is one row per team-era (ADR-013: Retrosheet reuses
-- retro_team_id across non-contiguous eras, so retro_team_id alone isn't a
-- stable franchise key). Nothing today answers "what is this franchise's
-- current code" -- that fact was hand-patched with duplicated CASE WHEN
-- SQL in report.py and, separately, in the still-open PR wiring
-- season.py's real-data paths. This closes the gap ADR-013 already named
-- ("No franchise-continuity table yet ... a known, deliberate gap until
-- something needs it"), using the player-identity-style precedent
-- ADR-029 established for core.team.mlb_team_id.
--
-- franchise_id is Lahman's own franchid (raw.lahman_teams_franchises),
-- already ingested and already confirmed joining to core.team via
-- raw.lahman_teams.teamidretro = core.team.retro_team_id -- no new
-- external source. current_retro_team_id is backfilled by conform.py as
-- the retro_team_id of the franchise's resolved core.team row with the
-- greatest first_year, NOT whichever era core.team.last_year marks
-- active (verified directly: Retrosheet's own source file still marks
-- the Athletics' retired 'OAK' code active -- last_year = 9999 -- while
-- 'ATH' is the real current code since the 2025 relocation).
--
-- franchise_id is nullable on core.team by design: a real, documented
-- subset of team-eras (pre-1969 Negro League teams, ~449 rows, per
-- docs/DECISIONS.md) has no Lahman franchise crosswalk at all, and this
-- project's established precedent is an honest NULL over a fabricated
-- link.
--
-- legacy_retro_team_id (the franchise's OLDEST resolved era's code) is a
-- separate anchor from current_retro_team_id (the newest), added after
-- the initial design: report.py's gold.team_season and season.py's
-- schedule loader both need every era of a franchise's history to key off
-- ONE stable core.team row for their own existing reasons (gold.team_season
-- has UNIQUE (team_id, season); season.py's ALL_MLB_TEAMS/MLB_DIVISIONS
-- are a static list still keyed on the Athletics' old 'OAK' code, and
-- updating that list is separately scoped, out of this change) -- and for
-- both, the already-established stable anchor is the OLDEST code, not the
-- newest (owner decision, team-franchise-crosswalk implementation).
CREATE TABLE core.team_franchise (
    id bigserial PRIMARY KEY,
    franchise_id text NOT NULL UNIQUE,
    franchise_name text,
    current_retro_team_id text,
    legacy_retro_team_id text
);

ALTER TABLE core.team ADD COLUMN franchise_id bigint REFERENCES core.team_franchise (id);
CREATE INDEX ON core.team (franchise_id);
