-- ============================================================
-- 04_player.sql
-- Core player dimension table
-- Schema: baseball
-- Mirrors: baseball.db.models.Player
-- ============================================================

CREATE TABLE IF NOT EXISTS baseball.player (
    player_id          SERIAL          PRIMARY KEY,
    player_mlbam_id    INTEGER         UNIQUE,
    player_retrosheet_id VARCHAR(20)   UNIQUE,
    player_lahman_id   VARCHAR(20)     UNIQUE,
    first_name         VARCHAR(100)    NOT NULL,
    last_name          VARCHAR(100)    NOT NULL,
    bats               CHAR(1),                    -- L, R, S
    throws             CHAR(1),                    -- L, R
    birth_date         DATE,
    death_date         DATE,
    debut_date         DATE,
    final_game_date    DATE,
    height_inches      INTEGER,
    weight_lbs         INTEGER,
    position_primary   VARCHAR(10),
    created_at         TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP       NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_player_names  ON baseball.player (last_name, first_name);
CREATE INDEX IF NOT EXISTS ix_player_debut  ON baseball.player (debut_date);
CREATE INDEX IF NOT EXISTS ix_player_mlbam  ON baseball.player (player_mlbam_id);
CREATE INDEX IF NOT EXISTS ix_player_retro  ON baseball.player (player_retrosheet_id);
CREATE INDEX IF NOT EXISTS ix_player_lahman ON baseball.player (player_lahman_id);
