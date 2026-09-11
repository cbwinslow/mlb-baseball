-- Drop indexes confirmed, against production `mlb`, to be either exact
-- duplicates or genuinely unused -- both pure maintenance overhead: every
-- INSERT/UPDATE/DELETE on the table has to maintain them for zero read
-- benefit, which matters on this project's full-rebuild-heavy pipeline
-- (ADR-266).
--
-- Evidence (queried directly against production, stats never reset --
-- pg_stat_database.stats_reset is NULL, so idx_scan = 0 covers the table's
-- entire lifetime, not a recent reset artifact):
--
--   1. Five duplicate indexes: each dropped index is a plain single-column
--      index whose column is the *leading* column of an existing UNIQUE
--      composite index on the same table, so every query the plain index
--      could serve, the composite already serves via its leading column --
--      basic B-tree prefix matching, not a judgment call:
--        core.market.market_source_idx (source)
--          -> covered by market_source_market_ref_key (source, market_ref)
--        core.team.team_retro_team_id_idx (retro_team_id)
--          -> covered by team_retro_team_id_first_year_last_year_key
--             (retro_team_id, first_year, last_year)
--        gold.player_season.player_season_player_id_idx (player_id)
--          -> covered by player_season_player_id_season_is_pitcher_key
--             (player_id, season, is_pitcher)
--        gold.prediction.prediction_game_idx (mlb_game_pk)
--          -> covered by prediction_pkey (mlb_game_pk, model_version, generated_at)
--        gold.total_prediction.total_prediction_game_idx (mlb_game_pk)
--          -> covered by total_prediction_pkey (mlb_game_pk, model_version, generated_at)
--
--   2. Eight zero-scan indexes with NO originating migration in this repo
--      (grepped migrations/*.sql -- none create them; they exist only in
--      production, most likely created by hand outside the migration
--      history at some point). idx_scan = 0 for each, over the database's
--      entire tracked lifetime:
--        raw.retrosheet_pitching.idx_retrosheet_pitching_season (_season)
--        raw.retrosheet_fielding.idx_retrosheet_fielding_season (_season)
--        raw.retrosheet_allplayers.idx_retrosheet_allplayers_season (_season)
--        raw.register_people.register_people_key_bbref_idx (key_bbref)
--        core.game.game_winning_pitcher_id_idx (winning_pitcher_id)
--        core.game.game_losing_pitcher_id_idx (losing_pitcher_id)
--        core.game.game_save_pitcher_id_idx (save_pitcher_id)
--        core.game.game_venue_id_idx (venue_id)
--
-- Deliberately NOT dropped, despite also showing idx_scan = 0: two other
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
-- Additive-safe and fully reversible: `IF EXISTS` guards mean this is a
-- no-op on any database that never had these hand-created indexes (a fresh
-- `mlb migrate` run, most test databases). Rollback: recreate each index
-- verbatim from the `CREATE INDEX` statements in this file's own history
-- (every dropped index's exact definition is quoted above and in the PR).

DROP INDEX IF EXISTS core.market_source_idx;
DROP INDEX IF EXISTS core.team_retro_team_id_idx;
DROP INDEX IF EXISTS gold.player_season_player_id_idx;
DROP INDEX IF EXISTS gold.prediction_game_idx;
DROP INDEX IF EXISTS gold.total_prediction_game_idx;

DROP INDEX IF EXISTS raw.idx_retrosheet_pitching_season;
DROP INDEX IF EXISTS raw.idx_retrosheet_fielding_season;
DROP INDEX IF EXISTS raw.idx_retrosheet_allplayers_season;
DROP INDEX IF EXISTS raw.register_people_key_bbref_idx;

DROP INDEX IF EXISTS core.game_winning_pitcher_id_idx;
DROP INDEX IF EXISTS core.game_losing_pitcher_id_idx;
DROP INDEX IF EXISTS core.game_save_pitcher_id_idx;
DROP INDEX IF EXISTS core.game_venue_id_idx;
