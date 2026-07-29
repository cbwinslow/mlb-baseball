-- Extends the core layer to actually use this project's differentiator
-- data (prediction markets, ADR-026/027) and two other rich sources that
-- landed in raw this session but never got joined into core: win
-- probability and Baseball-Reference's own WAR calculation. Found while
-- reviewing conform.py: everything from ADR-020 onward sat in raw with no
-- bridge to core.game at all -- unreachable without hand-matching team
-- names and dates in raw SQL yourself, the exact problem conform.py exists
-- to solve for everything else. See docs/DECISIONS.md ADR-028.

-- core.play gains win-probability columns, mlb_api-sourced rows only
-- (raw.mlb_win_prob has no Retrosheet equivalent -- see ADR-019). Kept as
-- columns on the existing play-level fact, not a separate table: a win
-- probability is an attribute of a specific plate appearance, and
-- core.play already has the exact join key needed (game_id + play_index).
ALTER TABLE core.play ADD COLUMN home_win_probability numeric;
ALTER TABLE core.play ADD COLUMN away_win_probability numeric;

-- One row per (source, market) -- the market-implied probability for one
-- side of one game, from Polymarket or Kalshi. game_id/team_id are
-- nullable: a market that can't be matched to a specific core.game row
-- (ambiguous doubleheader, a non-game prop that slipped through the
-- source-side filter, a team-name variant not yet in the alias map) stays
-- an honest NULL rather than a guessed match -- same philosophy as
-- core.game.game_pk's backfill (ADR-018).
CREATE TABLE core.market (
    id bigserial PRIMARY KEY,
    game_id bigint REFERENCES core.game (id),
    source text NOT NULL,
    market_ref text NOT NULL,
    team_id bigint REFERENCES core.team (id),
    implied_probability numeric,
    volume numeric,
    status text,
    _conformed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, market_ref)
);

CREATE INDEX ON core.market (game_id);
CREATE INDEX ON core.market (source);

-- One row per player-season-stint (a player traded mid-season has more
-- than one row, matching raw.bref_war_batting/pitching's own grain --
-- not aggregated here, since collapsing stints would need a choice this
-- project isn't making on Baseball-Reference's behalf). team_code is
-- Baseball-Reference's own 3-letter code, kept as free text rather than a
-- core.team FK -- bref's team codes don't consistently match Retrosheet's
-- (confirmed spot-checking a few: not worth a second team-alias map when
-- nothing here actually needs the team dimension, only the player one).
CREATE TABLE core.player_war (
    id bigserial PRIMARY KEY,
    player_id bigint REFERENCES core.player (id),
    season integer NOT NULL,
    is_pitcher boolean,
    team_code text,
    war numeric,
    waa numeric,
    war_replacement numeric,
    runs_above_avg numeric,
    runs_above_avg_offense numeric,
    runs_above_avg_defense numeric,
    _conformed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON core.player_war (player_id);
CREATE INDEX ON core.player_war (season);
