-- =============================================================
-- 04_raw_fangraphs.sql
-- RAW FanGraphs data tables - batting, pitching, fielding stats
-- Source: https://www.fangraphs.com/leaders.aspx
--         pybaseball batting_stats() / pitching_stats() functions
-- Schema: raw
-- Tables: raw.fg_batting, raw.fg_pitching, raw.fg_fielding,
--         raw.fg_team_batting, raw.fg_team_pitching
-- NOTE:   All FanGraphs standard + advanced stat columns preserved.
-- =============================================================

-- -----------------------------------------------------------
-- raw.fg_batting
-- FanGraphs season batting stats (one row per player-season)
-- pybaseball: batting_stats(start_season, end_season)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.fg_batting (
    -- Identifiers
    playerid                   TEXT,
    season                     SMALLINT      NOT NULL,
    name                       TEXT,
    team                       TEXT,
    age                        SMALLINT,
    -- Playing time
    g                          SMALLINT,     -- games
    ab                         INTEGER,      -- at-bats
    pa                         INTEGER,      -- plate appearances
    h                          INTEGER,      -- hits
    "1b"                       INTEGER,      -- singles
    "2b"                       INTEGER,      -- doubles
    "3b"                       INTEGER,      -- triples
    hr                         INTEGER,      -- home runs
    r                          INTEGER,      -- runs
    rbi                        INTEGER,      -- runs batted in
    bb                         INTEGER,      -- walks
    ibb                        INTEGER,      -- intentional walks
    so                         INTEGER,      -- strikeouts
    hbp                        INTEGER,      -- hit by pitch
    sf                         INTEGER,      -- sacrifice flies
    sh                         INTEGER,      -- sacrifice hits
    gdp                        INTEGER,      -- grounded into DP
    sb                         INTEGER,      -- stolen bases
    cs                         INTEGER,      -- caught stealing
    -- Rate stats
    avg                        NUMERIC(6,4), -- batting average
    obp                        NUMERIC(6,4), -- on-base %
    slg                        NUMERIC(6,4), -- slugging %
    ops                        NUMERIC(6,4), -- OPS
    -- Advanced
    bb_pct                     NUMERIC(7,4), -- walk rate
    k_pct                      NUMERIC(7,4), -- strikeout rate
    bb_k                       NUMERIC(7,4), -- BB/K
    woba                       NUMERIC(6,4),
    wrc_plus                   NUMERIC(8,2), -- wRC+
    wrc                        NUMERIC(8,2), -- wRC
    wraa                       NUMERIC(8,2), -- wRAA
    off                        NUMERIC(8,2), -- offensive runs above avg
    def_val                    NUMERIC(8,2), -- defensive runs above avg
    "war"                      NUMERIC(7,2), -- fWAR
    -- Batted ball
    gb_pct                     NUMERIC(7,4),
    fb_pct                     NUMERIC(7,4),
    ld_pct                     NUMERIC(7,4),
    iffb_pct                   NUMERIC(7,4),
    hr_fb                      NUMERIC(7,4), -- HR/FB rate
    gb_fb                      NUMERIC(7,4),
    pull_pct                   NUMERIC(7,4),
    cent_pct                   NUMERIC(7,4),
    oppo_pct                   NUMERIC(7,4),
    soft_pct                   NUMERIC(7,4),
    med_pct                    NUMERIC(7,4),
    hard_pct                   NUMERIC(7,4),
    -- Statcast / expected
    ev                         NUMERIC(6,2), -- exit velocity avg
    la                         NUMERIC(6,2), -- launch angle avg
    barrels                    INTEGER,
    barrel_pct                 NUMERIC(7,4),
    maxev                      NUMERIC(6,2),
    hard_hit_pct               NUMERIC(7,4),
    xba                        NUMERIC(6,4),
    xslg                       NUMERIC(6,4),
    xwoba                      NUMERIC(6,4),
    xwrc_plus                  NUMERIC(8,2),
    xera                       NUMERIC(6,3),
    -- Plate discipline
    o_swing_pct                NUMERIC(7,4), -- O-Swing%
    z_swing_pct                NUMERIC(7,4), -- Z-Swing%
    swing_pct                  NUMERIC(7,4),
    o_contact_pct              NUMERIC(7,4),
    z_contact_pct              NUMERIC(7,4),
    contact_pct                NUMERIC(7,4),
    zone_pct                   NUMERIC(7,4),
    f_strike_pct               NUMERIC(7,4),
    swstr_pct                  NUMERIC(7,4),
    -- Win probability
    wpa                        NUMERIC(8,4),
    neg_wpa                    NUMERIC(8,4),
    pos_wpa                    NUMERIC(8,4),
    re24                       NUMERIC(8,3),
    rew                        NUMERIC(8,3),
    pli                        NUMERIC(7,4),
    phli                       NUMERIC(7,4),
    ph_r                       NUMERIC(7,4),
    wpa_li                     NUMERIC(8,4),
    clutch                     NUMERIC(7,4),
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fg_bat_playerid ON raw.fg_batting (playerid);
CREATE INDEX IF NOT EXISTS ix_fg_bat_season   ON raw.fg_batting (season);
CREATE INDEX IF NOT EXISTS ix_fg_bat_team     ON raw.fg_batting (team, season);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_fg_bat_player_season ON raw.fg_batting (playerid, season, team);

-- -----------------------------------------------------------
-- raw.fg_pitching
-- FanGraphs season pitching stats (one row per pitcher-season)
-- pybaseball: pitching_stats(start_season, end_season)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.fg_pitching (
    playerid                   TEXT,
    season                     SMALLINT      NOT NULL,
    name                       TEXT,
    team                       TEXT,
    age                        SMALLINT,
    -- Role
    w                          SMALLINT,
    l                          SMALLINT,
    sv                         SMALLINT,
    g                          SMALLINT,
    gs                         SMALLINT,
    cg                         SMALLINT,
    sho                        SMALLINT,
    hld                        SMALLINT,
    bs                         SMALLINT,
    -- Volume
    ip                         NUMERIC(7,1),
    tbf                        INTEGER,      -- total batters faced
    h                          INTEGER,
    r                          INTEGER,
    er                         INTEGER,
    hr                         INTEGER,
    bb                         INTEGER,
    ibb                        INTEGER,
    hbp                        INTEGER,
    wp                         INTEGER,
    bk                         INTEGER,
    so                         INTEGER,
    -- Rate stats
    era                        NUMERIC(6,3),
    ra9                        NUMERIC(6,3),
    fip                        NUMERIC(6,3),
    xfip                       NUMERIC(6,3),
    siera                      NUMERIC(6,3),
    -- Advanced
    k_9                        NUMERIC(7,3),
    bb_9                       NUMERIC(7,3),
    k_bb                       NUMERIC(7,3),
    h_9                        NUMERIC(7,3),
    hr_9                       NUMERIC(7,3),
    avg                        NUMERIC(6,4),
    whip                       NUMERIC(6,3),
    babip                      NUMERIC(6,4),
    lob_pct                    NUMERIC(7,4),
    gb_pct                     NUMERIC(7,4),
    fb_pct                     NUMERIC(7,4),
    ld_pct                     NUMERIC(7,4),
    hr_fb                      NUMERIC(7,4),
    k_pct                      NUMERIC(7,4),
    bb_pct                     NUMERIC(7,4),
    -- Statcast
    ev                         NUMERIC(6,2),
    la                         NUMERIC(6,2),
    barrels                    INTEGER,
    barrel_pct                 NUMERIC(7,4),
    maxev                      NUMERIC(6,2),
    hard_hit_pct               NUMERIC(7,4),
    xba                        NUMERIC(6,4),
    xslg                       NUMERIC(6,4),
    xwoba                      NUMERIC(6,4),
    xera                       NUMERIC(6,3),
    -- Plate discipline
    o_swing_pct                NUMERIC(7,4),
    z_swing_pct                NUMERIC(7,4),
    swing_pct                  NUMERIC(7,4),
    o_contact_pct              NUMERIC(7,4),
    z_contact_pct              NUMERIC(7,4),
    contact_pct                NUMERIC(7,4),
    zone_pct                   NUMERIC(7,4),
    f_strike_pct               NUMERIC(7,4),
    swstr_pct                  NUMERIC(7,4),
    -- WAR
    "war"                      NUMERIC(7,2),
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fg_pit_playerid ON raw.fg_pitching (playerid);
CREATE INDEX IF NOT EXISTS ix_fg_pit_season   ON raw.fg_pitching (season);
CREATE INDEX IF NOT EXISTS ix_fg_pit_team     ON raw.fg_pitching (team, season);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_fg_pit_player_season ON raw.fg_pitching (playerid, season, team);

-- -----------------------------------------------------------
-- raw.fg_fielding
-- FanGraphs season fielding stats (one row per player-position-season)
-- pybaseball: fielding_stats(start_season, end_season)
-- -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw.fg_fielding (
    playerid                   TEXT,
    season                     SMALLINT      NOT NULL,
    name                       TEXT,
    team                       TEXT,
    pos                        TEXT,
    age                        SMALLINT,
    g                          SMALLINT,
    gs                         SMALLINT,
    inn                        NUMERIC(8,1), -- innings played
    po                         INTEGER,
    a                          INTEGER,
    e                          INTEGER,
    dp                         INTEGER,
    fpct                       NUMERIC(6,4), -- fielding %
    drs                        NUMERIC(8,2), -- defensive runs saved
    biz                        INTEGER,      -- balls in zone
    plays                      INTEGER,
    rszr                       NUMERIC(7,3), -- revised zone rating
    rng                        NUMERIC(7,3), -- range factor
    rng_r                      NUMERIC(7,3), -- range factor per 9
    err_r                      NUMERIC(7,3),
    arm_r                      NUMERIC(7,3),
    dp_r                       NUMERIC(7,3),
    sbr                        NUMERIC(7,3), -- stolen base runs (catchers)
    ubr                        NUMERIC(7,3), -- ultimate base running
    frm_runs                   NUMERIC(7,3), -- catcher framing runs
    "def"                      NUMERIC(8,2),
    -- ingestion metadata
    source_url                 TEXT,
    loaded_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_fg_fld_playerid ON raw.fg_fielding (playerid);
CREATE INDEX IF NOT EXISTS ix_fg_fld_season   ON raw.fg_fielding (season);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_fg_fld_player_pos_season ON raw.fg_fielding (playerid, pos, season, team);
