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
-- current_retro_team_id exists for a consumer that specifically needs a
-- franchise's real, current code with no season/year context of its own
-- (e.g. matching an external source's live ticker/alias -- see
-- _build_team_aliases). It intentionally does NOT try to be a
-- season-independent "the" identity for a franchise: a franchise that has
-- relocated/reissued a code more than once (confirmed directly: the
-- Athletics alone span 'PHA' 1901-1954, 'KC1' 1955-1967, 'OAK' 1968-2024,
-- 'ATH' 2025 -- all under Lahman's one franchise_id 'OAK') already has one
-- real core.team row per era with its own matching retro_team_id and year
-- range. A season-scoped consumer (report.py's gold.team_season,
-- season.py's schedule loader) should resolve each row/season to ITS OWN
-- era directly -- core.team's existing (retro_team_id, first_year,
-- last_year) rows already do that correctly on their own -- not redirect
-- everything to one single franchise-wide anchor code, which would
-- silently misattribute or drop every other era's data. (An earlier
-- version of this migration/design also added legacy_retro_team_id, an
-- "oldest era" anchor; removed after review found it does exactly that
-- misattribution for any franchise with more than one historical code
-- change, not just the Athletics' most recent one.)
CREATE TABLE core.team_franchise (
    id bigserial PRIMARY KEY,
    franchise_id text NOT NULL UNIQUE,
    franchise_name text,
    current_retro_team_id text
);

ALTER TABLE core.team ADD COLUMN franchise_id bigint REFERENCES core.team_franchise (id);
CREATE INDEX ON core.team (franchise_id);
