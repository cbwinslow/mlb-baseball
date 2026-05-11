-- ============================================================
-- 10_pitch.sql
-- Pitch-level data (Statcast/Savant)
-- Schema: baseball
-- Mirrors: baseball.db.models.Pitch
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.pitch (
    pitch_id            SERIAL          PRIMARY KEY,
    game_id             INTEGER         NOT NULL REFERENCES baseball.game(game_id),
    play_id             VARCHAR(50),                -- Statcast play ID
    pitcher_id          INTEGER         REFERENCES baseball.player(player_id),
    batter_id           INTEGER         REFERENCES baseball.player(player_id),
    pitch_type          VARCHAR(10),                -- FF, CH, CU, etc.
    release_speed_mph   NUMERIC(6,2),
    spin_rate_rpm       INTEGER,
    spin_axis           NUMERIC(6,2),
    ivb                 NUMERIC(6,3),               -- induced vertical break
    hb                  NUMERIC(6,3),               -- horizontal break
    px                  NUMERIC(6,3),               -- plate x location
    pz                  NUMERIC(6,3),               -- plate z location
    vx0                 NUMERIC(6,3),               -- initial velocity x
    vy0                 NUMERIC(6,3),               -- initial velocity y
    vz0                 NUMERIC(6,3),               -- initial velocity z
    ax                  NUMERIC(6,3),               -- acceleration x
    ay                  NUMERIC(6,3),               -- acceleration y
    az                  NUMERIC(6,3),               -- acceleration z
    pfx_x               NUMERIC(6,3),               -- break x
    pfx_z               NUMERIC(6,3),               -- break z
    description         VARCHAR(100),               -- Called strike, foul, etc.
    result              VARCHAR(50),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_pitch_game_id   ON baseball.pitch (game_id);
CREATE INDEX IF NOT EXISTS ix_pitch_pitcher   ON baseball.pitch (pitcher_id);
CREATE INDEX IF NOT EXISTS ix_pitch_batter    ON baseball.pitch (batter_id);
CREATE INDEX IF NOT EXISTS ix_pitch_type      ON baseball.pitch (pitch_type);
