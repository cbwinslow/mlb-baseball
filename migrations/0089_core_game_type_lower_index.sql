-- Fixes the same class of query-planner cardinality misestimate migration
-- 0086 fixed for raw.retrosheet_gameinfo.gametype, now confirmed on
-- core.game.game_type: `lower(g.game_type) = 'regular'` is a
-- function-wrapped predicate Postgres has no statistics for, so it
-- estimated 381 matching rows when the real number is 222,180 (off by
-- ~583x) -- confirmed directly via EXPLAIN while diagnosing a real slow
-- stage (catcher_framing_csae_update.sql, CAT-02) during the first
-- real end-to-end `mlb predict` run since ADR-260's P0 fix. The
-- misestimate drove a nested-loop plan with `core.game` as the
-- (wrongly-tiny-estimated) outer/driving table, iterating far more times
-- than the planner accounted for.
--
-- `core.game` is a core-schema table created by earlier migrations, not
-- loader-created like raw.retrosheet_gameinfo -- no to_regclass guard
-- needed, matching the difference migration 0057's own header explains
-- between core/gold tables and raw loader-created ones. Six real SQL
-- files in this codebase filter on `lower(g.game_type)`/`lower(game_type)`,
-- so this fixes more than just the one query that surfaced it.

CREATE INDEX IF NOT EXISTS game_type_lower_idx ON core.game (lower(game_type));
