-- gold.batting_game — one batting box-score line per (batter, game).
--
-- First relation of the grain-complete statistic backbone
-- (docs/superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md,
-- Plan 03B). Built by mlb_baseball/sql/batting_game_build.sql from
-- raw.retrosheet_event (1910-2025) using the same event-flag handling
-- (bat_event_fl / ab_fl / sf_fl / sh_fl / h_cd) that the already-tied-out
-- team stats use (sql/team_woba_retrosheet_update.sql, ADR-034). 2026+ MLB
-- Stats API play-by-play is a later, separate builder.
--
-- Grain: (game_id, player_id). A two-way player gets a row here for their
-- batting and a row in gold.pitching_game for their pitching.
--
-- Every column is a plain counting stat with an unambiguous MLB-glossary
-- definition. Rate stats (AVG/OBP/SLG/...) are NOT stored here -- they live
-- in the season/career roll-ups where the denominators are meaningful.

CREATE TABLE IF NOT EXISTS gold.batting_game (
    game_id     bigint  NOT NULL REFERENCES core.game (id),
    player_id   bigint  NOT NULL REFERENCES core.player (id),
    team_id     bigint  REFERENCES core.team (id),
    season      integer NOT NULL,
    game_date   date    NOT NULL,

    pa      integer NOT NULL DEFAULT 0,   -- plate appearances (bat_event_fl = 'T')
    ab      integer NOT NULL DEFAULT 0,   -- at bats (ab_fl = 'T')
    r       integer NOT NULL DEFAULT 0,   -- runs scored by this batter (as batter or baserunner)
    h       integer NOT NULL DEFAULT 0,   -- hits (event_cd 20-23)
    b1      integer NOT NULL DEFAULT 0,   -- singles
    b2      integer NOT NULL DEFAULT 0,   -- doubles
    b3      integer NOT NULL DEFAULT 0,   -- triples
    hr      integer NOT NULL DEFAULT 0,   -- home runs
    tb      integer NOT NULL DEFAULT 0,   -- total bases (b1 + 2*b2 + 3*b3 + 4*hr)
    rbi     integer NOT NULL DEFAULT 0,   -- runs batted in (sum of rbi_ct)
    bb      integer NOT NULL DEFAULT 0,   -- walks (event_cd 14-15)
    ibb     integer NOT NULL DEFAULT 0,   -- intentional walks (event_cd 15)
    hbp     integer NOT NULL DEFAULT 0,   -- hit by pitch (event_cd 16)
    sf      integer NOT NULL DEFAULT 0,   -- sacrifice flies (sf_fl = 'T')
    sh      integer NOT NULL DEFAULT 0,   -- sacrifice hits / bunts (sh_fl = 'T')
    so      integer NOT NULL DEFAULT 0,   -- strikeouts (event_cd 3)
    gidp    integer NOT NULL DEFAULT 0,   -- grounded into double play (dp_fl = 'T' AND grounder)

    source          text        NOT NULL DEFAULT 'retrosheet_event',
    _built_at       timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (game_id, player_id)
);

CREATE INDEX IF NOT EXISTS batting_game_player_season_idx
    ON gold.batting_game (player_id, season);
CREATE INDEX IF NOT EXISTS batting_game_team_season_idx
    ON gold.batting_game (team_id, season);
CREATE INDEX IF NOT EXISTS batting_game_season_idx
    ON gold.batting_game (season);

COMMENT ON TABLE gold.batting_game IS
    'One batting box-score line per (batter, game), from raw.retrosheet_event. '
    'Grain-complete statistic backbone, Plan 03B. Counting stats only; rate '
    'stats live in the season/career roll-ups.';
