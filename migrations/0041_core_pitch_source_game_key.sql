-- Preserve Statcast's provider game key alongside the nullable resolved
-- core-game FK. A NULL game_id is an honest unresolved crosswalk, but without
-- this source key it cannot be classified or repaired after a full conform
-- rebuild. The source key is not a replacement primary key for core.pitch.
ALTER TABLE core.pitch ADD COLUMN source_game_pk text;
CREATE INDEX core_pitch_source_game_pk_idx ON core.pitch (source_game_pk);
