-- gold.batting_postseason / gold.pitching_postseason -- postseason batting and
-- pitching lines, kept entirely separate from the regular-season backbone.
--
-- Part of the separate-postseason-stats change (ADR-282). Built by `mlb report`
-- from raw.lahman_batting_post / raw.lahman_pitching_post (Lahman's own
-- BattingPost / PitchingPost, 1884+) -- the direct parallel to Lahman's own
-- postseason tables, and the same lineage as gold.player_season. Player ids
-- conform via core.player.bbref_id (Lahman playerID is the Baseball-Reference
-- id); team ids via raw.lahman_teams (teamid + yearid -> teamidretro ->
-- core.team.retro_team_id).
--
-- Reference: baseball.computer keeps every season/career aggregate
-- regular-season only and publishes no postseason aggregate; Lahman ships
-- BattingPost / PitchingPost at the player grain. We follow Lahman -- one player
-- total table per stat type, three row kinds:
--   * per-round : is_combined = false, is_career = false -- one per
--                 (player, season, round, team). `round` is Lahman's raw value.
--   * combined  : is_combined = true -- one per (player, season), all rounds
--                 summed, round / team_id NULL.
--   * career    : is_career = true -- one per (player), every postseason season
--                 summed, season / round / team_id NULL.
-- A postseason team total is a GROUP BY over this table and is a deferred
-- follow-up (Lahman and baseball.computer both ship only player-grain
-- postseason data).
--
-- Column shape mirrors gold.batting_season / gold.pitching_season so a
-- researcher can UNION / compare. Unlike the event-derived gold.pitching_season
-- (RA9, no earned runs), Lahman's PitchingPost carries ER, so
-- gold.pitching_postseason has a real ERA.
--
-- The caller (report._build_backbone_relation) TRUNCATEs each table first, in
-- the same transaction.

CREATE TABLE IF NOT EXISTS gold.batting_postseason (
    id          bigserial PRIMARY KEY,
    player_id   bigint  NOT NULL REFERENCES core.player (id),
    season      integer,                          -- NULL iff is_career
    team_id     bigint  REFERENCES core.team (id), -- NULL unless a per-round row
    round       text,                             -- Lahman's raw round; NULL unless per-round
    is_combined boolean NOT NULL DEFAULT false,    -- true = all-rounds season line
    is_career   boolean NOT NULL DEFAULT false,    -- true = all-seasons career line

    g       integer NOT NULL DEFAULT 0,
    pa      integer NOT NULL DEFAULT 0,   -- AB + BB + HBP + SF + SH (Lahman post has no PA column)
    ab      integer NOT NULL DEFAULT 0,
    r       integer NOT NULL DEFAULT 0,
    h       integer NOT NULL DEFAULT 0,
    b1      integer NOT NULL DEFAULT 0,   -- H - 2B - 3B - HR
    b2      integer NOT NULL DEFAULT 0,
    b3      integer NOT NULL DEFAULT 0,
    hr      integer NOT NULL DEFAULT 0,
    tb      integer NOT NULL DEFAULT 0,
    rbi     integer NOT NULL DEFAULT 0,
    sb      integer NOT NULL DEFAULT 0,
    cs      integer NOT NULL DEFAULT 0,
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

    source      text        NOT NULL DEFAULT 'lahman_batting_post',
    _built_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT batting_postseason_flags_excl   CHECK (NOT (is_combined AND is_career)),
    CONSTRAINT batting_postseason_career_season CHECK (is_career = (season IS NULL)),
    CONSTRAINT batting_postseason_round_scope  CHECK ((round IS NOT NULL) = (NOT is_combined AND NOT is_career)),
    CONSTRAINT batting_postseason_team_scope   CHECK ((team_id IS NOT NULL) = (NOT is_combined AND NOT is_career))
);

CREATE UNIQUE INDEX IF NOT EXISTS batting_postseason_round_uniq
    ON gold.batting_postseason (player_id, season, round, team_id)
    WHERE NOT is_combined AND NOT is_career;
CREATE UNIQUE INDEX IF NOT EXISTS batting_postseason_combined_uniq
    ON gold.batting_postseason (player_id, season) WHERE is_combined;
CREATE UNIQUE INDEX IF NOT EXISTS batting_postseason_career_uniq
    ON gold.batting_postseason (player_id) WHERE is_career;
CREATE INDEX IF NOT EXISTS batting_postseason_season_idx ON gold.batting_postseason (season);

COMMENT ON TABLE gold.batting_postseason IS
    'Postseason batting line per (player, season, round) plus a combined '
    'all-rounds row per (player, season) and a career row per player, from '
    'Lahman BattingPost. Never contains a regular-season game. '
    'separate-postseason-stats / ADR-282.';


CREATE TABLE IF NOT EXISTS gold.pitching_postseason (
    id          bigserial PRIMARY KEY,
    player_id   bigint  NOT NULL REFERENCES core.player (id),
    season      integer,
    team_id     bigint  REFERENCES core.team (id),
    round       text,
    is_combined boolean NOT NULL DEFAULT false,
    is_career   boolean NOT NULL DEFAULT false,

    g       integer NOT NULL DEFAULT 0,
    gs      integer NOT NULL DEFAULT 0,
    cg      integer NOT NULL DEFAULT 0,
    sho     integer NOT NULL DEFAULT 0,
    bf      integer NOT NULL DEFAULT 0,
    outs    integer NOT NULL DEFAULT 0,   -- Lahman IPouts
    h       integer NOT NULL DEFAULT 0,
    r       integer NOT NULL DEFAULT 0,
    er      integer NOT NULL DEFAULT 0,   -- Lahman PitchingPost carries earned runs
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

    era     numeric,   -- ER * 27 / outs   (real ERA -- earned runs are in the source)
    ra9     numeric,   -- R  * 27 / outs
    whip    numeric,   -- (H + BB) * 3 / outs
    k9      numeric,   -- SO * 27 / outs
    bb9     numeric,   -- BB * 27 / outs
    hr9     numeric,   -- HR * 27 / outs
    k_bb    numeric,   -- SO / BB (NULL when BB = 0)

    source      text        NOT NULL DEFAULT 'lahman_pitching_post',
    _built_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pitching_postseason_flags_excl   CHECK (NOT (is_combined AND is_career)),
    CONSTRAINT pitching_postseason_career_season CHECK (is_career = (season IS NULL)),
    CONSTRAINT pitching_postseason_round_scope  CHECK ((round IS NOT NULL) = (NOT is_combined AND NOT is_career)),
    CONSTRAINT pitching_postseason_team_scope   CHECK ((team_id IS NOT NULL) = (NOT is_combined AND NOT is_career))
);

CREATE UNIQUE INDEX IF NOT EXISTS pitching_postseason_round_uniq
    ON gold.pitching_postseason (player_id, season, round, team_id)
    WHERE NOT is_combined AND NOT is_career;
CREATE UNIQUE INDEX IF NOT EXISTS pitching_postseason_combined_uniq
    ON gold.pitching_postseason (player_id, season) WHERE is_combined;
CREATE UNIQUE INDEX IF NOT EXISTS pitching_postseason_career_uniq
    ON gold.pitching_postseason (player_id) WHERE is_career;
CREATE INDEX IF NOT EXISTS pitching_postseason_season_idx ON gold.pitching_postseason (season);

COMMENT ON TABLE gold.pitching_postseason IS
    'Postseason pitching line per (player, season, round) plus a combined '
    'all-rounds row per (player, season) and a career row per player, from '
    'Lahman PitchingPost. Real ERA (earned runs are in the source). Never '
    'contains a regular-season game. separate-postseason-stats / ADR-282.';
