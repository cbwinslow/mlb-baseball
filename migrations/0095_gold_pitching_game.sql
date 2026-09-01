-- gold.pitching_game — one pitching box-score line per (pitcher, game).
--
-- Second relation of the grain-complete statistic backbone
-- (docs/superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md,
-- Plan 03B, ADR-278). Built by mlb_baseball/sql/pitching_game_build.sql from
-- raw.retrosheet_event (1910-2025), attributing every play to its charged
-- pitcher via re.resp_pit_id (verified against Chadwick's own docs as "the
-- pitcher actually charged for that play", correct across mid-at-bat
-- substitutions -- ADR on starter.py, DECISIONS.md). Runs are charged to the
-- responsible pitcher per runner: re.resp_pit_id for the batter-runner,
-- re.run{1,2,3}_resp_pit_id for runners already on base, so an inherited
-- runner's run lands on the pitcher who put them on, not the current one.
--
-- Grain: (game_id, player_id). A two-way player gets a row here and in
-- gold.batting_game.
--
-- er / era are NOT stored: earned runs need reconstructed-inning logic
-- (replay the inning without the errors), which cwevent does not emit. RA9
-- (from `r`) is the honest event-derived rate; ERA is available per player-
-- season from raw.bref_pitching. A reconstructed-inning ER pass is a
-- documented follow-up.

CREATE TABLE IF NOT EXISTS gold.pitching_game (
    game_id     bigint  NOT NULL REFERENCES core.game (id),
    player_id   bigint  NOT NULL REFERENCES core.player (id),
    team_id     bigint  REFERENCES core.team (id),
    season      integer NOT NULL,
    game_date   date    NOT NULL,

    gs      integer NOT NULL DEFAULT 0,   -- 1 if this pitcher started the game
    bf      integer NOT NULL DEFAULT 0,   -- batters faced (bat_event_fl = 'T', this pitcher charged)
    outs    integer NOT NULL DEFAULT 0,   -- outs recorded (sum of event_outs_ct); IP = outs / 3.0
    h       integer NOT NULL DEFAULT 0,   -- hits allowed (event_cd 20-23)
    r       integer NOT NULL DEFAULT 0,   -- runs allowed (charged per responsible pitcher)
    bb      integer NOT NULL DEFAULT 0,   -- walks allowed (event_cd 14-15)
    ibb     integer NOT NULL DEFAULT 0,   -- intentional walks (event_cd 15)
    so      integer NOT NULL DEFAULT 0,   -- strikeouts (event_cd 3)
    hr      integer NOT NULL DEFAULT 0,   -- home runs allowed (event_cd 23)
    hbp     integer NOT NULL DEFAULT 0,   -- hit batters (event_cd 16)
    wp      integer NOT NULL DEFAULT 0,   -- wild pitches (wp_fl = 'T')
    bk      integer NOT NULL DEFAULT 0,   -- balks (event_cd 11)
    w       integer NOT NULL DEFAULT 0,   -- win  (core.game.winning_pitcher_id)
    l       integer NOT NULL DEFAULT 0,   -- loss (core.game.losing_pitcher_id)
    sv      integer NOT NULL DEFAULT 0,   -- save (core.game.save_pitcher_id)

    source          text        NOT NULL DEFAULT 'retrosheet_event',
    _built_at       timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (game_id, player_id)
);

CREATE INDEX IF NOT EXISTS pitching_game_player_season_idx
    ON gold.pitching_game (player_id, season);
CREATE INDEX IF NOT EXISTS pitching_game_team_season_idx
    ON gold.pitching_game (team_id, season);
CREATE INDEX IF NOT EXISTS pitching_game_season_idx
    ON gold.pitching_game (season);

COMMENT ON TABLE gold.pitching_game IS
    'One pitching box-score line per (pitcher, game), from raw.retrosheet_event. '
    'Grain-complete statistic backbone, Plan 03B. Counting stats only; rate '
    'stats live in the season/career roll-ups. er/era deferred (needs '
    'reconstructed-inning logic).';
