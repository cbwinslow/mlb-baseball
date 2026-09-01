-- gold.batting_season / gold.batting_team — season and team roll-ups of
-- gold.batting_game.
--
-- Relation 3 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Built by `mlb report` from gold.batting_game (which is itself built from
-- raw.retrosheet_event, 1910-2025). Counting stats are plain sums of the
-- game lines; rate stats are computed from this grain's own summed
-- components (you cannot average a season's game-by-game AVGs).
--
-- gold.batting_season grain: (player_id, season, team_id) for the per-team
-- stint rows (is_combined = false), plus one (player_id, season) combined
-- row (is_combined = true, team_id NULL) per player-season -- for a
-- one-team player the combined row equals the single stint row, so
-- `WHERE is_combined` always yields exactly one full-season line per
-- player. Matches Baseball-Reference, which shows both the per-team lines
-- and a combined "2TM"/"3TM" line for a traded player.
--
-- SB / CS / SB% are deliberately absent: gold.batting_game does not carry
-- them (steals are baserunning, deferred to a later gold.baserunning_game),
-- so a season roll-up cannot produce them yet. Added when that relation
-- lands. ERA has no analogue here (this is batting).
--
-- gold.batting_team grain: (team_id, season) -- one row per team per season,
-- no combined-row complication.

CREATE TABLE IF NOT EXISTS gold.batting_season (
    id          bigserial PRIMARY KEY,
    player_id   bigint  NOT NULL REFERENCES core.player (id),
    season      integer NOT NULL,
    team_id     bigint  REFERENCES core.team (id),   -- NULL iff is_combined
    is_combined boolean NOT NULL DEFAULT false,      -- true = all-teams full-season line

    g       integer NOT NULL DEFAULT 0,   -- games played (distinct game_id)
    pa      integer NOT NULL DEFAULT 0,
    ab      integer NOT NULL DEFAULT 0,
    r       integer NOT NULL DEFAULT 0,
    h       integer NOT NULL DEFAULT 0,
    b1      integer NOT NULL DEFAULT 0,
    b2      integer NOT NULL DEFAULT 0,
    b3      integer NOT NULL DEFAULT 0,
    hr      integer NOT NULL DEFAULT 0,
    tb      integer NOT NULL DEFAULT 0,
    rbi     integer NOT NULL DEFAULT 0,
    bb      integer NOT NULL DEFAULT 0,
    ibb     integer NOT NULL DEFAULT 0,
    hbp     integer NOT NULL DEFAULT 0,
    sf      integer NOT NULL DEFAULT 0,
    sh      integer NOT NULL DEFAULT 0,
    so      integer NOT NULL DEFAULT 0,
    gidp    integer NOT NULL DEFAULT 0,

    -- Rate stats, NULL when the denominator is 0 (MLB glossary / FanGraphs):
    avg     numeric,   -- H / AB
    obp     numeric,   -- (H + BB + HBP) / (AB + BB + HBP + SF)
    slg     numeric,   -- TB / AB
    ops     numeric,   -- OBP + SLG
    iso     numeric,   -- SLG - AVG
    babip   numeric,   -- (H - HR) / (AB - SO - HR + SF)
    bb_pct  numeric,   -- BB / PA
    k_pct   numeric,   -- SO / PA

    source      text        NOT NULL DEFAULT 'retrosheet_event',
    _built_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT batting_season_combined_null_team CHECK (is_combined = (team_id IS NULL)),
    CONSTRAINT batting_season_stint_uniq UNIQUE (player_id, season, team_id)
);

-- Exactly one combined row per (player, season). The UNIQUE above can't
-- enforce this (NULL team_id compares distinct), so a partial index does.
CREATE UNIQUE INDEX IF NOT EXISTS batting_season_combined_uniq
    ON gold.batting_season (player_id, season) WHERE is_combined;

CREATE INDEX IF NOT EXISTS batting_season_season_idx ON gold.batting_season (season);
CREATE INDEX IF NOT EXISTS batting_season_team_idx   ON gold.batting_season (team_id, season);

COMMENT ON TABLE gold.batting_season IS
    'Season batting line per (player, season, team) plus a combined all-teams '
    'row per (player, season), rolled up from gold.batting_game. Rate stats '
    'computed at this grain. SB/CS deferred (baserunning). Plan 03B.';


CREATE TABLE IF NOT EXISTS gold.batting_team (
    team_id     bigint  NOT NULL REFERENCES core.team (id),
    season      integer NOT NULL,

    g       integer NOT NULL DEFAULT 0,   -- team games (distinct game_id)
    pa      integer NOT NULL DEFAULT 0,
    ab      integer NOT NULL DEFAULT 0,
    r       integer NOT NULL DEFAULT 0,
    h       integer NOT NULL DEFAULT 0,
    b1      integer NOT NULL DEFAULT 0,
    b2      integer NOT NULL DEFAULT 0,
    b3      integer NOT NULL DEFAULT 0,
    hr      integer NOT NULL DEFAULT 0,
    tb      integer NOT NULL DEFAULT 0,
    rbi     integer NOT NULL DEFAULT 0,
    bb      integer NOT NULL DEFAULT 0,
    ibb     integer NOT NULL DEFAULT 0,
    hbp     integer NOT NULL DEFAULT 0,
    sf      integer NOT NULL DEFAULT 0,
    sh      integer NOT NULL DEFAULT 0,
    so      integer NOT NULL DEFAULT 0,
    gidp    integer NOT NULL DEFAULT 0,

    avg     numeric,
    obp     numeric,
    slg     numeric,
    ops     numeric,
    iso     numeric,
    babip   numeric,
    bb_pct  numeric,
    k_pct   numeric,

    source      text        NOT NULL DEFAULT 'retrosheet_event',
    _built_at   timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (team_id, season)
);

CREATE INDEX IF NOT EXISTS batting_team_season_idx ON gold.batting_team (season);

COMMENT ON TABLE gold.batting_team IS
    'Season batting line per (team, season), rolled up from gold.batting_game. '
    'Plan 03B.';
