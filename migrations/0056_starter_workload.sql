-- Starter rest days and workload outs (PIT-03).
-- Rest days: calendar days since starting pitcher's immediately preceding start (nullable integer).
-- Workload outs: total outs pitched (any role) in trailing 7-day window entering today's game (nullable numeric).

ALTER TABLE gold.game_feature ADD COLUMN home_starter_rest_days integer;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_rest_days integer;
ALTER TABLE gold.game_feature ADD COLUMN home_starter_outs_7d numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_starter_outs_7d numeric;
