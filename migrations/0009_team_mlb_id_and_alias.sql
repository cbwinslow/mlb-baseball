-- Adds core.team.mlb_team_id (MLB Stats API's own stable numeric team ID)
-- and core.team_alias (a small crosswalk for external sources with no
-- shared ID scheme with MLB at all). See docs/DECISIONS.md ADR-029.
--
-- mlb_team_id is the team equivalent of core.player.mlbam_id: a stable
-- external numeric anchor, not a name to string-match. Confirmed directly
-- against raw.mlb_team_history: MLB's own team_id survives every rename
-- (108: Los Angeles/California/Anaheim/Los Angeles Angels; 114: Cleveland
-- Indians/Guardians, 2022; 133: Philadelphia/Kansas City/Oakland/
-- Sacramento Athletics; 139: Tampa Bay Devil Rays/Rays, 2008) -- exactly
-- the churn that broke plain city+nickname string matching. A real,
-- separate bug this surfaced: 42 core.game rows since 2025 had NULL
-- team_id because MLB's own schedule now lists the Athletics as just
-- "Athletics" (no city, mid-relocation), which no longer string-matches
-- "Oakland Athletics" at all.
--
-- Backfilled by conform.py, not this migration -- see _backfill_mlb_team_id
-- (a self-verifying majority vote over already-resolved core.game rows,
-- not a second round of string matching) and _backfill_team_ids_via_mlb_id
-- (uses the resulting crosswalk to fix the rows the original string match
-- missed).

ALTER TABLE core.team ADD COLUMN mlb_team_id integer;
CREATE INDEX ON core.team (mlb_team_id);

-- One row per known alternate name/code for a team, for sources with no
-- shared ID scheme with MLB at all (Polymarket's own team-name strings,
-- Kalshi's own ticker codes). Nothing MLB-API-sourced needs this table --
-- that uses mlb_team_id directly.
CREATE TABLE core.team_alias (
    id bigserial PRIMARY KEY,
    team_id bigint NOT NULL REFERENCES core.team (id),
    alias text NOT NULL UNIQUE,
    source text
);
