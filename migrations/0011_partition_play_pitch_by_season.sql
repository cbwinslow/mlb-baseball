-- Partitions core.play and core.pitch by season (native Postgres RANGE
-- partitioning, no new extension) -- the real, growing cost behind `mlb
-- conform`'s full-rebuild time: both tables are truncated and rebuilt in
-- full on every run (16.48M / 11.01M rows in production at the time this
-- was written). Both already have a `season integer` column, a natural
-- partition key. Confirmed before writing this: no other table has an FK
-- into core.play or core.pitch, so this swap is safe from that angle.
--
-- conform.py needs NO logic changes for this -- Postgres transparently
-- routes INSERT...SELECT rows to the correct partition, and TRUNCATE on
-- the parent already truncates every partition. This migration is schema
-- + a one-time data copy only.
--
-- ALTER TABLE ... PARTITION BY isn't supported on an existing table in
-- Postgres, so this builds new partitioned tables alongside the old ones,
-- copies data in, then atomically renames old->*_old (kept as a rollback
-- safety net, not dropped here -- a deliberate later, separate step once
-- the swap is confirmed healthy) and new->the live name.
--
-- Constraint/index names are schema-scoped in Postgres, not per-table, and
-- ALTER TABLE ... RENAME does *not* rename a table's constraints or
-- indexes along with it -- found the hard way, applying this against
-- mlb_test, before touching production: naming play_new's PK "play_pkey"
-- up front collided with the still-existing original core.play's own
-- play_pkey. Fixed by explicitly renaming the *old* table's constraints/
-- indexes out of the way first, then renaming the new ones into the now-
-- free original names -- see the two renaming blocks below.

CREATE TABLE core.play_new (
    id bigserial,
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
    home_win_probability numeric,
    away_win_probability numeric,
    -- season must be part of every unique constraint on a partitioned
    -- table (Postgres requirement) -- game_id already implies exactly one
    -- season in practice, so this doesn't weaken the real guarantee.
    PRIMARY KEY (id, season),
    UNIQUE (season, game_id, source, play_index)
) PARTITION BY RANGE (season);

CREATE TABLE core.pitch_new (
    id bigserial,
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
    _conformed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, season)
) PARTITION BY RANGE (season);

-- One partition per season, 1871-2035 (comfortable margin past the
-- current 2026 season so this doesn't need revisiting again soon), plus a
-- DEFAULT partition on each table as a safety net for anything outside
-- that range -- Postgres rejects an INSERT into a partitioned table with
-- no matching partition and no DEFAULT, which would otherwise turn a
-- stray out-of-range season into a hard failure instead of an honest,
-- visible row.
DO $$
DECLARE
    yr integer;
BEGIN
    FOR yr IN 1871..2035 LOOP
        EXECUTE format(
            'CREATE TABLE core.play_%1$s PARTITION OF core.play_new FOR VALUES FROM (%1$s) TO (%2$s)',
            yr, yr + 1
        );
        EXECUTE format(
            'CREATE TABLE core.pitch_%1$s PARTITION OF core.pitch_new FOR VALUES FROM (%1$s) TO (%2$s)',
            yr, yr + 1
        );
    END LOOP;
    EXECUTE 'CREATE TABLE core.play_default PARTITION OF core.play_new DEFAULT';
    EXECUTE 'CREATE TABLE core.pitch_default PARTITION OF core.pitch_new DEFAULT';
END $$;

-- One-time data copy -- the real cost of this migration, not a recurring
-- one. Column lists spelled out explicitly (not SELECT *) so this doesn't
-- silently break if either table's column order ever drifts.
INSERT INTO core.play_new (
    id, game_id, season, source, play_index, inning, half_inning,
    batter_id, pitcher_id, event_code, event_desc, away_score, home_score,
    balls, strikes, outs, _conformed_at, home_win_probability, away_win_probability
)
SELECT
    id, game_id, season, source, play_index, inning, half_inning,
    batter_id, pitcher_id, event_code, event_desc, away_score, home_score,
    balls, strikes, outs, _conformed_at, home_win_probability, away_win_probability
FROM core.play;

INSERT INTO core.pitch_new (
    id, game_id, season, at_bat_number, pitch_number, inning,
    batter_id, pitcher_id, pitch_type, pitch_name, release_speed,
    release_spin_rate, launch_speed, launch_angle, hit_distance,
    description, event, _conformed_at
)
SELECT
    id, game_id, season, at_bat_number, pitch_number, inning,
    batter_id, pitcher_id, pitch_type, pitch_name, release_speed,
    release_spin_rate, launch_speed, launch_angle, hit_distance,
    description, event, _conformed_at
FROM core.pitch;

-- Keep both bigserial sequences advancing from where the old tables left
-- off -- otherwise the next INSERT could collide with an id already
-- copied above.
SELECT setval(
    pg_get_serial_sequence('core.play_new', 'id'),
    COALESCE((SELECT max(id) FROM core.play_new), 1)
);
SELECT setval(
    pg_get_serial_sequence('core.pitch_new', 'id'),
    COALESCE((SELECT max(id) FROM core.pitch_new), 1)
);

-- Free up the original constraint/index names by renaming the old table's
-- versions out of the way first -- table rename alone does not rename
-- these (see the note at the top of this file).
ALTER TABLE core.play RENAME TO play_old;
ALTER TABLE core.play_old RENAME CONSTRAINT play_pkey TO play_pkey_old;
ALTER TABLE core.play_old
    RENAME CONSTRAINT play_game_id_source_play_index_key TO play_game_id_source_play_index_key_old;
ALTER INDEX core.play_game_id_idx RENAME TO play_game_id_idx_old;
ALTER INDEX core.play_batter_id_idx RENAME TO play_batter_id_idx_old;
ALTER INDEX core.play_pitcher_id_idx RENAME TO play_pitcher_id_idx_old;
ALTER INDEX core.play_season_idx RENAME TO play_season_idx_old;

ALTER TABLE core.pitch RENAME TO pitch_old;
ALTER TABLE core.pitch_old RENAME CONSTRAINT pitch_pkey TO pitch_pkey_old;
ALTER INDEX core.pitch_game_id_idx RENAME TO pitch_game_id_idx_old;
ALTER INDEX core.pitch_batter_id_idx RENAME TO pitch_batter_id_idx_old;
ALTER INDEX core.pitch_pitcher_id_idx RENAME TO pitch_pitcher_id_idx_old;
ALTER INDEX core.pitch_season_idx RENAME TO pitch_season_idx_old;

-- Real bug found verifying this migration against mlb_test, before
-- touching production: leaving these FK constraints on the *_old* tables
-- breaks every future TRUNCATE of core.game/core.player anywhere in the
-- codebase, including conform.py's own run() -- Postgres refuses to
-- truncate a table still referenced by another table's FK unless that
-- other table is truncated in the same statement or the FK is dropped.
-- *_old tables are meant to be an inert rollback snapshot, not part of
-- the live referential graph, so the constraints (not the data) get
-- dropped here.
ALTER TABLE core.play_old DROP CONSTRAINT play_game_id_fkey;
ALTER TABLE core.play_old DROP CONSTRAINT play_batter_id_fkey;
ALTER TABLE core.play_old DROP CONSTRAINT play_pitcher_id_fkey;
ALTER TABLE core.pitch_old DROP CONSTRAINT pitch_game_id_fkey;
ALTER TABLE core.pitch_old DROP CONSTRAINT pitch_batter_id_fkey;
ALTER TABLE core.pitch_old DROP CONSTRAINT pitch_pitcher_id_fkey;

-- Now rename the new (partitioned) tables into place, and their
-- auto-named constraints (play_new_pkey, etc. -- assigned at CREATE TABLE
-- time, also unaffected by the table rename above) to the clean original
-- names, now free.
ALTER TABLE core.play_new RENAME TO play;
ALTER TABLE core.play RENAME CONSTRAINT play_new_pkey TO play_pkey;
ALTER TABLE core.play
    RENAME CONSTRAINT play_new_season_game_id_source_play_index_key TO play_game_id_source_play_index_key;

ALTER TABLE core.pitch_new RENAME TO pitch;
ALTER TABLE core.pitch RENAME CONSTRAINT pitch_new_pkey TO pitch_pkey;

-- Secondary indexes created now, on the correctly-named live tables --
-- auto-naming lands exactly on the original names since the old table's
-- versions were already renamed out of the way above. Cascades to every
-- partition automatically (Postgres 11+).
CREATE INDEX ON core.play (game_id);
CREATE INDEX ON core.play (batter_id);
CREATE INDEX ON core.play (pitcher_id);
CREATE INDEX ON core.play (season);
CREATE INDEX ON core.pitch (game_id);
CREATE INDEX ON core.pitch (batter_id);
CREATE INDEX ON core.pitch (pitcher_id);
CREATE INDEX ON core.pitch (season);
