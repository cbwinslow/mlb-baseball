-- Adds core.play (one row per plate appearance, unifying Retrosheet's
-- 1910-2025 event files and MLB Stats API's 2026+ play-by-play) and
-- core.pitch (one row per tracked pitch, from Statcast). See
-- docs/DECISIONS.md ADR-017/ADR-018.
--
-- core.game gains game_pk: MLB's own numeric game identifier (distinct from
-- retro_game_id, Retrosheet's own scheme) -- the bridge that lets MLB-API-
-- and Statcast-sourced data (both keyed on game_pk) join back to core.game
-- (keyed on retro_game_id). Backfilled by conform.py via a (game_date, away
-- team, home team) match against raw.mlb_schedule -- confirmed directly
-- against real production data at an ~85% match rate (consistent across
-- eras, not concentrated in any one period); the remainder stays NULL
-- rather than a guessed value. Nullable and unindexed-unique on purpose:
-- not every core.game row will ever resolve one (pre-1901 games predate
-- MLB API's own coverage entirely), and that's a real, visible, honest
-- state, not an error to hide.

ALTER TABLE core.game ADD COLUMN game_pk text;
CREATE INDEX ON core.game (game_pk);

-- One row per plate appearance. `source` records which raw table a row
-- came from (`retrosheet` or `mlb_api`) since the two describe events in
-- different native vocabularies (Retrosheet's numeric event_cd + compact
-- event_tx code vs. MLB API's free-text event/eventType) that aren't force-
-- unified into one taxonomy here -- see ADR-018's rationale. play_index is
-- each source's own within-game sequence number (Retrosheet's event_id,
-- MLB API's atBatIndex).
CREATE TABLE core.play (
    id bigserial PRIMARY KEY,
    game_id bigint NOT NULL REFERENCES core.game (id),
    season integer NOT NULL,
    source text NOT NULL,
    play_index integer,
    inning integer,
    half_inning text,
    batter_id bigint REFERENCES core.player (id),
    pitcher_id bigint REFERENCES core.player (id),
    event_code text,
    event_desc text,
    away_score integer,
    home_score integer,
    balls integer,
    strikes integer,
    outs integer,
    _conformed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (game_id, source, play_index)
);

CREATE INDEX ON core.play (game_id);
CREATE INDEX ON core.play (batter_id);
CREATE INDEX ON core.play (pitcher_id);
CREATE INDEX ON core.play (season);

-- One row per tracked pitch, from Statcast (raw.statcast_pitch) only --
-- nothing else in this pipeline has pitch-level tracking data (see
-- mlb_api.py's module docstring and ADR-017 for why that data lives here
-- exclusively). game_id resolves via core.game.game_pk, so only rows for
-- games that resolved a game_pk can join here -- same honest-nullable
-- reasoning as core.game.game_pk itself. batter_id/pitcher_id resolve via
-- mlbam_id (Statcast's own batter/pitcher columns are already MLBAM IDs).
CREATE TABLE core.pitch (
    id bigserial PRIMARY KEY,
    game_id bigint REFERENCES core.game (id),
    season integer NOT NULL,
    at_bat_number integer,
    pitch_number integer,
    inning integer,
    batter_id bigint REFERENCES core.player (id),
    pitcher_id bigint REFERENCES core.player (id),
    pitch_type text,
    pitch_name text,
    release_speed numeric,
    release_spin_rate numeric,
    launch_speed numeric,
    launch_angle numeric,
    hit_distance numeric,
    description text,
    event text,
    _conformed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ON core.pitch (game_id);
CREATE INDEX ON core.pitch (batter_id);
CREATE INDEX ON core.pitch (pitcher_id);
CREATE INDEX ON core.pitch (season);
