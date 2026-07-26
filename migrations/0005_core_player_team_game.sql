-- First core (Silver-equivalent) dimensional tables: player, team, game.
-- Real types, surrogate primary keys, foreign keys, and indices — unlike
-- raw, which stays untyped/unconstrained on purpose (see ADR-013 and
-- ARCHITECTURE.md "Layered schema"). Populated by mlb_baseball/conform.py
-- (`mlb conform`), not a connector — it reads already-ingested raw tables,
-- it doesn't fetch anything over the network.

-- One row per real person who has a Retrosheet ID (the bridge column every
-- other ingested source's player references use). Scoped to key_retro IS
-- NOT NULL rather than every Chadwick Register row (517,320 rows, mostly
-- minor-leaguers/international players we have no other data for) — see
-- ADR-013 for the real row-count check behind that cutoff.
CREATE TABLE core.player (
    id bigserial PRIMARY KEY,
    retro_id text NOT NULL UNIQUE,
    mlbam_id text,
    bbref_id text,
    fangraphs_id text,
    chadwick_uuid text,
    last_name text,
    first_name text,
    birth_date date,
    death_date date,
    _conformed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON core.player (mlbam_id);
CREATE INDEX ON core.player (bbref_id);

-- One row per team-era, not per franchise — Retrosheet's own team_id can be
-- (and twice is, confirmed: HOU 1962-2012 vs 2013-2021, MIL 1970-1997 vs
-- 1998-2021 — both league changes, not overlapping) reused for a
-- non-contiguous era, so (retro_team_id, first_year, last_year) is the real
-- natural key, not retro_team_id alone. No franchise-continuity table yet
-- (e.g. linking Boston/Milwaukee/Atlanta Braves as one franchise) — a real,
-- known gap, not built until something actually needs it.
CREATE TABLE core.team (
    id bigserial PRIMARY KEY,
    retro_team_id text NOT NULL,
    league text,
    city text,
    nickname text,
    first_year integer NOT NULL,
    last_year integer NOT NULL,
    _conformed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (retro_team_id, first_year, last_year)
);

CREATE INDEX ON core.team (retro_team_id);

-- One row per game, built from the CSV product's gameinfo (raw.retrosheet_gameinfo,
-- 224,877 rows, 1898-2025 — the widest single game-level source, already the
-- one everything else this session was reconciled against). Team FKs resolve
-- via (team_code, season) against core.team's year ranges. Pitcher FKs are
-- nullable on purpose: 239 games' winning-pitcher ID doesn't resolve to any
-- core.player row (real, checked directly, not assumed), plus ~2,000 games
-- record no winning pitcher at all — losing that reference must not lose the
-- rest of the game's row.
CREATE TABLE core.game (
    id bigserial PRIMARY KEY,
    retro_game_id text NOT NULL UNIQUE,
    season integer NOT NULL,
    game_date date NOT NULL,
    game_number integer,
    away_team_id bigint REFERENCES core.team (id),
    home_team_id bigint REFERENCES core.team (id),
    away_score integer,
    home_score integer,
    game_type text,
    site text,
    attendance integer,
    duration_minutes integer,
    day_night text,
    winning_pitcher_id bigint REFERENCES core.player (id),
    losing_pitcher_id bigint REFERENCES core.player (id),
    save_pitcher_id bigint REFERENCES core.player (id),
    _conformed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON core.game (season);
CREATE INDEX ON core.game (game_date);
CREATE INDEX ON core.game (away_team_id);
CREATE INDEX ON core.game (home_team_id);
