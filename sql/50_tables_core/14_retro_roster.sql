-- =============================================================
-- 14_retro_roster.sql
-- Retrosheet roster entries (players on team rosters by year)
-- Schema: baseball
-- Table:  retro_roster
-- =============================================================

CREATE TABLE IF NOT EXISTS baseball.retro_roster (

    -- Primary key
    roster_id         BIGSERIAL PRIMARY KEY,

    -- Player identification
    player_id         VARCHAR(8)    NOT NULL,  -- Retrosheet player ID
    last_name         VARCHAR(50),
    first_name        VARCHAR(50),

    -- Team / season context
    team_id           VARCHAR(3)    NOT NULL,  -- Retrosheet team code
    season            SMALLINT      NOT NULL,  -- e.g. 2023

    -- Roster classification
    batting_hand      CHAR(1),                 -- B=both, L=left, R=right
    throwing_hand     CHAR(1),                 -- L=left, R=right
    position          VARCHAR(2),              -- P, C, 1B, 2B, 3B, SS, LF, CF, RF, OF, DH, PH, PR

    -- Source metadata
    source_file       VARCHAR(64),
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_retro_roster_season
    ON baseball.retro_roster (season);
CREATE INDEX IF NOT EXISTS idx_retro_roster_team_season
    ON baseball.retro_roster (team_id, season);
CREATE INDEX IF NOT EXISTS idx_retro_roster_player
    ON baseball.retro_roster (player_id);
CREATE UNIQUE INDEX IF NOT EXISTS uidx_retro_roster_player_team_season
    ON baseball.retro_roster (player_id, team_id, season);
