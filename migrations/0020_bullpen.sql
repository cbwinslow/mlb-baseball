-- Bullpen quality and fatigue (ADR-039, docs/RESEARCH.md's feature-
-- engineering backlog item 7). Team-level, not pitcher-level: which
-- specific relievers a manager uses is an in-game decision made after
-- the point this feature is computed for, so per-pitcher bullpen
-- composition would leak. Instead this rolls up every relief appearance
-- (any pitcher who wasn't that game's starter) into a team aggregate,
-- the same shape as home_starter_k_pct/bb_pct/hr_pct one level up.
-- fatigue is a separate, trailing-3-calendar-day workload count (outs
-- recorded by the team's bullpen), a proxy for how taxed the pen is
-- entering today's game -- distinct from quality, which is a full
-- season-to-date rate stat.

ALTER TABLE gold.game_feature ADD COLUMN home_bullpen_fip numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bullpen_fip numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_bullpen_k_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bullpen_k_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_bullpen_bb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bullpen_bb_pct numeric;
ALTER TABLE gold.game_feature ADD COLUMN home_bullpen_fatigue numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_bullpen_fatigue numeric;
