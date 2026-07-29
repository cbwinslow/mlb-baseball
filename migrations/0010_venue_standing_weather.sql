-- Closes three raw-to-core gaps found during a research-database review:
-- raw.retrosheet_park, raw.mlb_venue, and raw.mlb_standing were all fully
-- ingested but never bridged into core, the exact "sat in raw with no
-- bridge to core at all" problem ADR-028 already fixed for
-- market/player_war/win-probability. Also adds the four FK indexes core's
-- other tables all have but these were missing (found in the same review).

-- One row per historical ballpark, from raw.retrosheet_park (260 rows,
-- 1871-present, exact-match keyed on Retrosheet's own parkid -- the same
-- code already stored, unused as a join key, in
-- raw.retrosheet_gameinfo.site/core.game.site). mlb_venue_id and the
-- richer MLB-API-sourced columns (lat/long/capacity/turf/roof/dimensions)
-- are a best-effort enrichment, backfilled by conform.py via an exact
-- case-insensitive name match against raw.mlb_venue -- left NULL where no
-- exact match is found, not guessed, same "leave it NULL, don't guess"
-- precedent as core.game.game_pk. Retrosheet is the primary source (not
-- MLB's venue catalog) because it's the one with an exact, non-fuzzy join
-- key back to core.game.
CREATE TABLE core.venue (
    id bigserial PRIMARY KEY,
    retro_park_id text NOT NULL UNIQUE,
    name text,
    city text,
    state text,
    league text,
    first_year integer,
    last_year integer,
    mlb_venue_id integer,
    latitude numeric,
    longitude numeric,
    capacity integer,
    turf_type text,
    roof_type text,
    left_line integer,
    center integer,
    right_line integer,
    _conformed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON core.venue (mlb_venue_id);

-- core.game gains a venue FK (resolved via raw.retrosheet_gameinfo.site =
-- core.venue.retro_park_id, an exact match -- no string-matching risk,
-- unlike team/game_pk resolution) plus Retrosheet's own per-game weather
-- columns (temp/wind/sky/precipitation/field condition -- confirmed
-- already landed in raw.retrosheet_gameinfo, 97%+ filled for
-- wind/sky/precip, 71% for temp, spanning 1900-2025, and completely
-- unused until now). MLB-API-sourced core.game rows (2026+, no Retrosheet
-- coverage yet) get NULL here -- raw.mlb_game_context has no weather
-- equivalent to backfill from, same honest-NULL treatment as every other
-- MLB-API-only gap in this project.
ALTER TABLE core.game ADD COLUMN venue_id bigint REFERENCES core.venue (id);
ALTER TABLE core.game ADD COLUMN temp_f integer;
ALTER TABLE core.game ADD COLUMN wind_dir text;
ALTER TABLE core.game ADD COLUMN wind_speed_mph integer;
ALTER TABLE core.game ADD COLUMN sky text;
ALTER TABLE core.game ADD COLUMN precip text;
ALTER TABLE core.game ADD COLUMN field_cond text;

CREATE INDEX ON core.game (venue_id);

-- One row per team-season, from raw.mlb_standing (1969-present, the
-- divisional era -- MLB Stats API's own standings_data() has no earlier
-- coverage, confirmed in ADR-015; pre-1969 win-loss is already available
-- via raw.lahman_teams/raw.retrosheet_gamelog, so this isn't a coverage
-- loss). team_id resolves via core.team.mlb_team_id (raw.mlb_standing's
-- own team_id is already MLB's numeric scheme, the same anchor
-- ADR-029 built for exactly this kind of join) -- must run after
-- _backfill_mlb_team_id, not before.
CREATE TABLE core.standing (
    id bigserial PRIMARY KEY,
    team_id bigint REFERENCES core.team (id),
    season integer NOT NULL,
    division text,
    div_rank integer,
    wins integer,
    losses integer,
    games_back numeric,
    wildcard_rank integer,
    wildcard_games_back numeric,
    league_rank integer,
    sport_rank integer,
    _conformed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (team_id, season)
);

CREATE INDEX ON core.standing (season);

-- Missing FK indexes found in the same review -- every other FK in core
-- is indexed, these four weren't.
CREATE INDEX ON core.market (team_id);
CREATE INDEX ON core.game (winning_pitcher_id);
CREATE INDEX ON core.game (losing_pitcher_id);
CREATE INDEX ON core.game (save_pitcher_id);
