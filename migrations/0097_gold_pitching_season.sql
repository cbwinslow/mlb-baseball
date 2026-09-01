-- gold.pitching_season / gold.pitching_team — season and team roll-ups of
-- gold.pitching_game.
--
-- Relation 4 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Built by `mlb report` from gold.pitching_game. Counting stats are plain
-- sums of the game lines; rate stats are computed from this grain's own
-- summed components. Same row-shape convention as gold.batting_season:
--
-- gold.pitching_season grain: (player_id, season, team_id) for the per-team
-- stint rows (is_combined = false), plus one (player_id, season) combined
-- row (is_combined = true, team_id NULL) per player-season -- for a
-- one-team pitcher the combined row equals the single stint.
--
-- ERA is deliberately absent: gold.pitching_game does not produce earned
-- runs (reconstructed-inning logic cwevent does not emit -- see migration
-- 0095). RA9 (from `r`) is the honest event-derived rate; ERA is available
-- per player-season from raw.bref_pitching / gold.player_season.
--
-- gold.pitching_team grain: (team_id, season).

CREATE TABLE IF NOT EXISTS gold.pitching_season (
    id          bigserial PRIMARY KEY,
    player_id   bigint  NOT NULL REFERENCES core.player (id),
    season      integer NOT NULL,
    team_id     bigint  REFERENCES core.team (id),   -- NULL iff is_combined
    is_combined boolean NOT NULL DEFAULT false,

    g       integer NOT NULL DEFAULT 0,   -- games pitched (distinct game_id)
    gs      integer NOT NULL DEFAULT 0,   -- games started
    bf      integer NOT NULL DEFAULT 0,
    outs    integer NOT NULL DEFAULT 0,   -- IP = outs / 3.0
    h       integer NOT NULL DEFAULT 0,
    r       integer NOT NULL DEFAULT 0,
    bb      integer NOT NULL DEFAULT 0,
    ibb     integer NOT NULL DEFAULT 0,
    so      integer NOT NULL DEFAULT 0,
    hr      integer NOT NULL DEFAULT 0,
    hbp     integer NOT NULL DEFAULT 0,
    wp      integer NOT NULL DEFAULT 0,
    bk      integer NOT NULL DEFAULT 0,
    w       integer NOT NULL DEFAULT 0,
    l       integer NOT NULL DEFAULT 0,
    sv      integer NOT NULL DEFAULT 0,

    -- Rate stats, NULL when the denominator is 0 (MLB glossary / FanGraphs):
    ra9     numeric,   -- R * 27 / outs      (runs allowed per 9 IP -- NOT ERA)
    whip    numeric,   -- (H + BB) * 3 / outs
    k9      numeric,   -- SO * 27 / outs
    bb9     numeric,   -- BB * 27 / outs
    hr9     numeric,   -- HR * 27 / outs
    k_bb    numeric,   -- SO / BB  (NULL when BB = 0)

    source      text        NOT NULL DEFAULT 'retrosheet_event',
    _built_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pitching_season_combined_null_team CHECK (is_combined = (team_id IS NULL)),
    CONSTRAINT pitching_season_stint_uniq UNIQUE (player_id, season, team_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS pitching_season_combined_uniq
    ON gold.pitching_season (player_id, season) WHERE is_combined;

CREATE INDEX IF NOT EXISTS pitching_season_season_idx ON gold.pitching_season (season);
CREATE INDEX IF NOT EXISTS pitching_season_team_idx   ON gold.pitching_season (team_id, season);

COMMENT ON TABLE gold.pitching_season IS
    'Season pitching line per (player, season, team) plus a combined all-teams '
    'row per (player, season), rolled up from gold.pitching_game. Rate stats '
    'computed at this grain. RA9 not ERA (no earned runs at this grain). Plan 03B.';


CREATE TABLE IF NOT EXISTS gold.pitching_team (
    team_id     bigint  NOT NULL REFERENCES core.team (id),
    season      integer NOT NULL,

    g       integer NOT NULL DEFAULT 0,
    gs      integer NOT NULL DEFAULT 0,
    bf      integer NOT NULL DEFAULT 0,
    outs    integer NOT NULL DEFAULT 0,
    h       integer NOT NULL DEFAULT 0,
    r       integer NOT NULL DEFAULT 0,
    bb      integer NOT NULL DEFAULT 0,
    ibb     integer NOT NULL DEFAULT 0,
    so      integer NOT NULL DEFAULT 0,
    hr      integer NOT NULL DEFAULT 0,
    hbp     integer NOT NULL DEFAULT 0,
    wp      integer NOT NULL DEFAULT 0,
    bk      integer NOT NULL DEFAULT 0,
    w       integer NOT NULL DEFAULT 0,
    l       integer NOT NULL DEFAULT 0,
    sv      integer NOT NULL DEFAULT 0,

    ra9     numeric,
    whip    numeric,
    k9      numeric,
    bb9     numeric,
    hr9     numeric,
    k_bb    numeric,

    source      text        NOT NULL DEFAULT 'retrosheet_event',
    _built_at   timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (team_id, season)
);

CREATE INDEX IF NOT EXISTS pitching_team_season_idx ON gold.pitching_team (season);

COMMENT ON TABLE gold.pitching_team IS
    'Season pitching line per (team, season), rolled up from gold.pitching_game. '
    'Plan 03B.';
