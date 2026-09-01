-- gold.batting_career / gold.pitching_career — career roll-ups of the
-- season tables.
--
-- Relation 5 of the grain-complete statistic backbone (Plan 03B, ADR-278).
-- Built by `mlb report` from gold.batting_season / gold.pitching_season,
-- summing each player's per-season combined rows (is_combined = true, one
-- per player-season) so a traded season is counted once, not once per
-- stint. Counting stats are plain sums; rate stats are recomputed from the
-- career-total components (a career AVG is total H / total AB).
--
-- Grain: one row per (player_id). No team dimension. ERA is absent on the
-- pitching side for the same reason as gold.pitching_season -- no earned
-- runs at this grain.

CREATE TABLE IF NOT EXISTS gold.batting_career (
    player_id       bigint  PRIMARY KEY REFERENCES core.player (id),
    seasons         integer NOT NULL DEFAULT 0,   -- distinct seasons played
    first_season    integer,
    last_season     integer,

    g       integer NOT NULL DEFAULT 0,
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

    avg     numeric,   -- H / AB
    obp     numeric,   -- (H + BB + HBP) / (AB + BB + HBP + SF)
    slg     numeric,   -- TB / AB
    ops     numeric,   -- OBP + SLG
    iso     numeric,   -- (TB - H) / AB
    babip   numeric,   -- (H - HR) / (AB - SO - HR + SF)
    bb_pct  numeric,   -- BB / PA
    k_pct   numeric,   -- SO / PA

    source      text        NOT NULL DEFAULT 'retrosheet_event',
    _built_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS batting_career_last_season_idx ON gold.batting_career (last_season);

COMMENT ON TABLE gold.batting_career IS
    'Career batting line per player, summed from gold.batting_season''s '
    'per-season combined rows. Rate stats recomputed at career grain. Plan 03B.';


CREATE TABLE IF NOT EXISTS gold.pitching_career (
    player_id       bigint  PRIMARY KEY REFERENCES core.player (id),
    seasons         integer NOT NULL DEFAULT 0,
    first_season    integer,
    last_season     integer,

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

    ra9     numeric,   -- R * 27 / outs (NOT ERA)
    whip    numeric,   -- (H + BB) * 3 / outs
    k9      numeric,   -- SO * 27 / outs
    bb9     numeric,   -- BB * 27 / outs
    hr9     numeric,   -- HR * 27 / outs
    k_bb    numeric,   -- SO / BB (NULL when BB = 0)

    source      text        NOT NULL DEFAULT 'retrosheet_event',
    _built_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pitching_career_last_season_idx ON gold.pitching_career (last_season);

COMMENT ON TABLE gold.pitching_career IS
    'Career pitching line per player, summed from gold.pitching_season''s '
    'per-season combined rows. RA9 not ERA (no earned runs at this grain). Plan 03B.';
