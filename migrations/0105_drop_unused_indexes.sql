-- mlb:nontransactional
-- Drop indexes confirmed, against production `mlb`, to be either exact
-- duplicates or genuinely unused -- both pure maintenance overhead: every
-- INSERT/UPDATE/DELETE on the table has to maintain them for zero read
-- benefit, which matters on this project's full-rebuild-heavy pipeline
-- (ADR-266).
--
-- CONCURRENTLY (CodeRabbit review, PR #189): a plain DROP INDEX takes a
-- brief ACCESS EXCLUSIVE lock on the table. On the largest tables here
-- (raw.retrosheet_event etc.) that can still queue up behind an
-- in-progress read/write. DROP INDEX CONCURRENTLY avoids that lock but
-- cannot run inside a transaction, hence the `mlb:nontransactional` marker
-- -- the same established escape hatch migration 0036 already uses for
-- CREATE INDEX CONCURRENTLY (see migrate.py::_apply_nontransactional_migration).
--
-- Evidence (queried directly against production, stats never reset --
-- pg_stat_database.stats_reset is NULL, so idx_scan = 0 covers the table's
-- entire lifetime, not a recent reset artifact):
--
--   1. Five duplicate indexes: each dropped index is a plain single-column
--      index whose column is the *leading* column of an existing UNIQUE
--      composite index on the same table, so every query the plain index
--      could serve, the composite already serves via its leading column --
--      basic B-tree prefix matching, not a judgment call.
--
--   2. Eight zero-scan indexes, idx_scan = 0 over the database's entire
--      tracked lifetime. CORRECTION (CodeRabbit review, PR #189): the
--      original version of this migration claimed none of these eight had
--      an originating migration in this repo. That was wrong for five of
--      them -- migrations 0002 and 0010 create them with PostgreSQL's
--      *default auto-generated name* (bare `CREATE INDEX ON table (col)`,
--      no explicit name given), so grepping this repo for the literal
--      generated index name (e.g. `game_winning_pitcher_id_idx`) finds
--      nothing even though the index is fully tracked. Only three of the
--      eight are genuinely untracked -- created by hand against production
--      at some point, outside the migration history entirely.
--
--   Every dropped index's exact, verbatim `pg_get_indexdef()` output
--   (queried directly from production) is quoted below, per index -- this
--   is the actual reversibility guarantee CodeRabbit asked for: rollback
--   is running these fourteen statements verbatim, not reconstructing a
--   CREATE INDEX from a column-name summary.
--
--   core.market.market_source_idx -- covered by market_source_market_ref_key (source, market_ref)
--     CREATE INDEX market_source_idx ON core.market USING btree (source)
--   core.team.team_retro_team_id_idx -- covered by team_retro_team_id_first_year_last_year_key (retro_team_id, first_year, last_year)
--     CREATE INDEX team_retro_team_id_idx ON core.team USING btree (retro_team_id)
--   gold.player_season.player_season_player_id_idx -- covered by player_season_player_id_season_is_pitcher_key (player_id, season, is_pitcher)
--     CREATE INDEX player_season_player_id_idx ON gold.player_season USING btree (player_id)
--   gold.prediction.prediction_game_idx -- covered by prediction_pkey (mlb_game_pk, model_version, generated_at)
--     CREATE INDEX prediction_game_idx ON gold.prediction USING btree (mlb_game_pk)
--   gold.total_prediction.total_prediction_game_idx -- covered by total_prediction_pkey (mlb_game_pk, model_version, generated_at)
--     CREATE INDEX total_prediction_game_idx ON gold.total_prediction USING btree (mlb_game_pk)
--
--   raw.register_people.register_people_key_bbref_idx -- TRACKED: migration
--   0002's `CREATE INDEX ON raw.register_people (key_bbref)`, auto-named.
--     CREATE INDEX register_people_key_bbref_idx ON raw.register_people USING btree (key_bbref)
--   core.game.game_winning_pitcher_id_idx -- TRACKED: migration 0010's
--   `CREATE INDEX ON core.game (winning_pitcher_id)`, auto-named.
--     CREATE INDEX game_winning_pitcher_id_idx ON core.game USING btree (winning_pitcher_id)
--   core.game.game_losing_pitcher_id_idx -- TRACKED: migration 0010's
--   `CREATE INDEX ON core.game (losing_pitcher_id)`, auto-named.
--     CREATE INDEX game_losing_pitcher_id_idx ON core.game USING btree (losing_pitcher_id)
--   core.game.game_save_pitcher_id_idx -- TRACKED: migration 0010's
--   `CREATE INDEX ON core.game (save_pitcher_id)`, auto-named.
--     CREATE INDEX game_save_pitcher_id_idx ON core.game USING btree (save_pitcher_id)
--   core.game.game_venue_id_idx -- TRACKED: migration 0010's
--   `CREATE INDEX ON core.game (venue_id)`, auto-named.
--     CREATE INDEX game_venue_id_idx ON core.game USING btree (venue_id)
--
--   raw.retrosheet_pitching.idx_retrosheet_pitching_season -- UNTRACKED (no
--   migration in this repo creates it, under any name).
--     CREATE INDEX idx_retrosheet_pitching_season ON raw.retrosheet_pitching USING btree (_season)
--   raw.retrosheet_fielding.idx_retrosheet_fielding_season -- UNTRACKED.
--     CREATE INDEX idx_retrosheet_fielding_season ON raw.retrosheet_fielding USING btree (_season)
--   raw.retrosheet_allplayers.idx_retrosheet_allplayers_season -- UNTRACKED.
--     CREATE INDEX idx_retrosheet_allplayers_season ON raw.retrosheet_allplayers USING btree (_season)
--
-- Deliberately NOT dropped, despite also reading idx_scan = 0: two other
-- retrosheet_event indexes looked identical on the surface but are each a
-- documented, evidence-backed fix for a real, severe production incident,
-- not read-path indexes at all --
--   raw.retrosheet_event.retrosheet_event_outs_ct_int_idx (migration 0086):
--     an *expression* index whose job is to give ANALYZE real statistics on
--     `outs_ct::integer`, fixing a planner cardinality misestimate that made
--     leverage_index.compute() run 2+ hours instead of minutes -- idx_scan
--     staying at 0 is expected (ANALYZE uses it for statistics, not scans),
--     and dropping it would silently reintroduce that regression.
--   raw.retrosheet_event.idx_retrosheet_event_pit_id (migration 0090):
--     asserted to exist by tests/integration/test_migrations.py; a
--     documented fix (ADR-268) for a specific daily-enrichment query.
-- Also not touched: meta.game_instance's zero-scan indexes (identity/
-- dedup-critical table; needs its own closer look, not a batch drop) and
-- raw.statcast_pitch.idx_statcast_pitch_batter (only 22 scans, but created
-- deliberately alongside idx_statcast_pitch_pitcher in migration 0090 for
-- the same measured reason -- low scan count is not zero, and the pair
-- should stay symmetric until there's a specific reason to split them).
--
-- Rollback: run the fourteen `CREATE INDEX ... ON ... USING btree (...)`
-- statements quoted above verbatim (CONCURRENTLY, same reasoning as the
-- drops) -- no reconstruction needed, they are copy-paste exact.

DROP INDEX CONCURRENTLY IF EXISTS core.market_source_idx;
DROP INDEX CONCURRENTLY IF EXISTS core.team_retro_team_id_idx;
DROP INDEX CONCURRENTLY IF EXISTS gold.player_season_player_id_idx;
DROP INDEX CONCURRENTLY IF EXISTS gold.prediction_game_idx;
DROP INDEX CONCURRENTLY IF EXISTS gold.total_prediction_game_idx;

DROP INDEX CONCURRENTLY IF EXISTS raw.idx_retrosheet_pitching_season;
DROP INDEX CONCURRENTLY IF EXISTS raw.idx_retrosheet_fielding_season;
DROP INDEX CONCURRENTLY IF EXISTS raw.idx_retrosheet_allplayers_season;
DROP INDEX CONCURRENTLY IF EXISTS raw.register_people_key_bbref_idx;

DROP INDEX CONCURRENTLY IF EXISTS core.game_winning_pitcher_id_idx;
DROP INDEX CONCURRENTLY IF EXISTS core.game_losing_pitcher_id_idx;
DROP INDEX CONCURRENTLY IF EXISTS core.game_save_pitcher_id_idx;
DROP INDEX CONCURRENTLY IF EXISTS core.game_venue_id_idx;
