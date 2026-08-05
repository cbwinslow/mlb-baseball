-- Gold-layer reporting surface (ADR-054): three materialized tables so a
-- future API/website can query one clean table per grain -- player-season,
-- team-season, division-standing -- instead of assembling from raw/core at
-- request time. See ADR-054 for the full materialized-vs-view reasoning and
-- mlb_baseball/report.py for the build logic (mlb report, not yet wired into
-- any CLI command -- see that module's own docstring).
--
-- Deliberately NO foreign keys to core.player/core.team here, unlike
-- gold.game_feature -- a real constraint found reading conform.py's run()
-- closely before writing this: its single consolidated TRUNCATE statement
-- (core.play, core.pitch, core.market, gold.game_feature, core.game,
-- core.team, core.player, core.venue, core.standing, core.team_alias,
-- core.player_war) must name every table that FKs into any of those, in the
-- same statement, or Postgres refuses the TRUNCATE outright (a bare
-- `TRUNCATE core.player` with some other table still FK-referencing it
-- fails with "cannot truncate a table referenced in a foreign key
-- constraint", regardless of row counts). Adding a real FK from these new
-- tables to core.player/core.team without also adding them to that
-- statement would silently break `mlb conform` the next time anyone ran it
-- -- and conform.py's own run() sequencing is explicitly off-limits for
-- this change (parallel work in progress elsewhere). Same tradeoff
-- gold.prediction already made for a related reason (a still-upcoming
-- game's prediction has no core.game row to FK against yet) -- plain
-- indexed bigint columns, referential correctness enforced by the build
-- module's own JOINs, not the schema.

-- One row per (player, season, batting-vs-pitching) -- matches
-- core.player_war's own is_pitcher discriminator rather than two separate
-- tables, since a two-way player (e.g. a real Shohei Ohtani case) needs one
-- row of each kind for the same season, not a forced single shape. Sourced
-- from raw.bref_batting/raw.bref_pitching (already one row per player per
-- season, every team a traded player appeared for that season already
-- combined by Baseball-Reference itself -- confirmed directly, not
-- assumed) joined to core.player via mlbid = core.player.mlbam_id (~99.5%
-- resolved, confirmed directly against production). Coverage is 2008-2026
-- only -- a hard limit in pybaseball itself (see mlb_baseball/connectors/
-- bref.py's own docstring), not a scoping choice made here; extending
-- further back via raw.lahman_batting/raw.lahman_pitching's stint-level
-- data is real, separate follow-up work (see ADR-054's "Revisit if").
--
-- h/r/bb/so/hr are genuinely dual-purpose depending on is_pitcher (hits/
-- runs/walks/strikeouts/homers a BATTER recorded vs. hits/runs/walks/
-- strikeouts/homers a PITCHER allowed) -- see the column comments below.
-- Kept as shared physical columns rather than doubled up
-- (batting_h/pitching_h) to stay inside CLAUDE.md's short-name convention;
-- avg/obp/slg/ops and gs/w/l/sv/ip/er/era/whip/so9 are unambiguous to one
-- side or the other and need no such sharing.
CREATE TABLE gold.player_season (
    id bigserial PRIMARY KEY,
    player_id bigint NOT NULL,
    season integer NOT NULL,
    is_pitcher boolean NOT NULL,
    player_name text,
    team text,
    games integer,
    -- Batting (NULL on a pitcher row)
    pa integer,
    ab integer,
    doubles integer,
    triples integer,
    rbi integer,
    hbp integer,
    sb integer,
    cs integer,
    avg numeric,
    obp numeric,
    slg numeric,
    ops numeric,
    -- Pitching (NULL on a batting row)
    gs integer,
    w integer,
    l integer,
    sv integer,
    ip numeric,
    er integer,
    era numeric,
    whip numeric,
    so9 numeric,
    -- Shared, dual-purpose depending on is_pitcher (see table comment)
    r integer,
    h integer,
    bb integer,
    so integer,
    hr integer,
    -- Baseball-Reference's own WAR (core.player_war), summed across every
    -- stint that season -- a traded player has multiple core.player_war
    -- rows per season (confirmed directly against production), but exactly
    -- one gold.player_season row, matching raw.bref_batting/pitching's own
    -- already-combined grain.
    war numeric,
    waa numeric,
    _built_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (player_id, season, is_pitcher)
);

CREATE INDEX ON gold.player_season (season);
CREATE INDEX ON gold.player_season (player_id);

COMMENT ON COLUMN gold.player_season.r IS 'Runs scored (batting row) or runs allowed (pitching row) -- see table comment.';
COMMENT ON COLUMN gold.player_season.h IS 'Hits (batting row) or hits allowed (pitching row) -- see table comment.';
COMMENT ON COLUMN gold.player_season.bb IS 'Walks drawn (batting row) or walks allowed (pitching row) -- see table comment.';
COMMENT ON COLUMN gold.player_season.so IS 'Strikeouts made (batting row) or strikeouts recorded (pitching row) -- see table comment.';
COMMENT ON COLUMN gold.player_season.hr IS 'Home runs hit (batting row) or home runs allowed (pitching row) -- see table comment.';
COMMENT ON COLUMN gold.player_season.team IS 'Baseball-Reference''s own team/city text, comma-joined for a multi-team season (e.g. "Miami,Oakland") -- free text, not a core.team FK, same reasoning as core.player_war.team_code.';

-- One row per (team, season) -- traditional batting/pitching/fielding
-- totals plus this project's own already-computed advanced metrics'
-- season-grain versions. Deliberately does NOT include division rank/games
-- back/wildcard standing -- those are gold.division_standing's job (see
-- below); this table is "how did the team perform," not "where did they
-- rank." wins/losses/win_pct appear on both tables anyway (a small,
-- deliberate overlap -- a team-season stats page and a division-standings
-- page each need their own record display without an extra join).
--
-- Traditional totals (wins/losses/runs/runs_allowed/hr/era) come from
-- raw.lahman_teams, not aggregated from gold.player_season -- confirmed
-- directly that raw.bref_batting/pitching's own "tm" column is a bare city
-- name (e.g. "Chicago", ambiguous between the Cubs and White Sox) rather
-- than a resolvable team code, and is comma-joined across cities for a
-- traded player's combined-season row -- neither shape supports a clean
-- team-level sum. raw.lahman_teams.teamidretro matches core.team.
-- retro_team_id exactly (confirmed directly across all 30 current teams,
-- 2023 spot check) and covers full history (1871-2025), unlike bref's
-- 2008+ limit -- so team_season's traditional-stat coverage is genuinely
-- wider than player_season's, a real, documented asymmetry, not a bug.
--
-- woba/wrc_plus/park_factor are freshly computed here as true season-final
-- aggregates, not read off gold.game_feature -- that table's own
-- home_woba/away_woba/park_factor are deliberately leakage-free
-- point-in-time values (a team's rolling wOBA entering each game, missing
-- that game's own contribution -- see mlb_baseball/model/offense.py's
-- module docstring), the wrong shape for "what was the team's actual final
-- number that season." See mlb_baseball/report.py for the season-aggregate
-- queries, reusing offense.py's/park.py's own formulas and constants.
-- war reuses mlb_baseball.model.war._BREF_TO_RETRO (imported, not
-- duplicated) to resolve core.player_war's bref-style team_code to
-- core.team -- covers only the current 30 teams, same documented
-- limitation war.py itself already carries.
CREATE TABLE gold.team_season (
    id bigserial PRIMARY KEY,
    team_id bigint NOT NULL,
    season integer NOT NULL,
    team_city text,
    team_nickname text,
    league text,
    wins integer,
    losses integer,
    win_pct numeric,
    runs integer,
    runs_allowed integer,
    hr integer,
    era numeric,
    woba numeric,
    wrc_plus numeric,
    park_factor numeric,
    war numeric,
    _built_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (team_id, season)
);

CREATE INDEX ON gold.team_season (season);

-- One row per (team, season) -- division standing/rank, enriching
-- core.standing (1969-present, already team-season grain with division/
-- div_rank/wins/losses/games_back/wildcard_rank/wildcard_games_back/
-- league_rank/sport_rank) rather than replacing it: adds resolved team
-- display fields (so a standings page needs zero extra joins, the whole
-- point of this reporting layer) plus elim_num/wc_elim_num from
-- raw.mlb_standing -- landed in raw the whole time, confirmed present,
-- never bridged to core (same "sat in raw with no bridge" gap class as
-- ADR-028/030 already closed for other sources) -- rather than a guessed
-- addition. win_pct is computed, not sourced (core.standing has no such
-- column). Same 1969+ coverage as core.standing itself -- MLB Stats API's
-- own standings_data() has no earlier coverage (confirmed in ADR-015);
-- this is an honest inherited limitation, not a new one.
--
-- elim_num/wildcard_elim_num are text, not integer -- confirmed directly
-- against real raw.mlb_standing data: values are either a digit string, a
-- bare '-' (mathematically alive but MLB doesn't publish a magic number
-- yet, e.g. very early season), or 'E' (eliminated). Collapsing 'E' and
-- '-' to the same NULL/0 would erase a real, meaningful distinction a
-- standings page needs (the whole point of surfacing this column at all),
-- so both are kept as their own source-faithful text values instead.
CREATE TABLE gold.division_standing (
    id bigserial PRIMARY KEY,
    team_id bigint NOT NULL,
    season integer NOT NULL,
    team_city text,
    team_nickname text,
    division text,
    div_rank integer,
    wins integer,
    losses integer,
    win_pct numeric,
    games_back numeric,
    wildcard_rank integer,
    wildcard_games_back numeric,
    league_rank integer,
    sport_rank integer,
    elim_num text,
    wildcard_elim_num text,
    _built_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (team_id, season)
);

CREATE INDEX ON gold.division_standing (season);
CREATE INDEX ON gold.division_standing (division);
