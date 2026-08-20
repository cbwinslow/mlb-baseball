-- Starter age on game date (PLN-04, docs/FEATURE_ADMISSION_QUEUE.md,
-- ADR-087). Pure derived value over two already-populated pieces --
-- gold.game_feature's own home_starter_id/away_starter_id (resolved by
-- starter.py) and core.player.birth_date -- no new raw-event dependency,
-- same "derive from a prior step's own output" shape as
-- int_diff_update.sql/trend_update.sql.
--
-- Self-joins gold.game_feature to itself via its real, always-populated
-- surrogate key (`id`, migration 0014) rather than `game_id` (NULL for
-- an upcoming/scheduled game that has no core.game row yet) -- joining
-- on game_id would silently exclude every upcoming game's row (NULL
-- never equals NULL in SQL).
--
-- Years as a continuous decimal (day-count / 365.25), not floored to an
-- integer -- "age on game date" in the admission queue's own words means
-- exact age, not age-in-completed-years. NULL whenever the starter isn't
-- resolved (unstarted game before starter.compute() has run) or the
-- resolved player's birth_date itself is unknown (a real, documented gap
-- -- 1,840 of 25,543 core.player rows have no birth_date, ~7%, confirmed
-- against production `mlb`) -- both cases the admission queue's own null
-- policy ("NULL unresolved identity") calls for.

UPDATE gold.game_feature f
SET home_starter_age = (f.game_date - hp.birth_date) / 365.25,
    away_starter_age = (f.game_date - ap.birth_date) / 365.25
FROM gold.game_feature gf
LEFT JOIN core.player hp ON hp.id = gf.home_starter_id
LEFT JOIN core.player ap ON ap.id = gf.away_starter_id
WHERE f.id = gf.id;
