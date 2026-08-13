-- Retained PA denominator (OFF-03, ADR-062 follow-up to ADR-061). Exposes
-- the same plate-appearance count team_rate_retrosheet_update.sql already
-- computes internally for its OBP/BB%/K% denominators and min-sample gate
-- (migration 0051 companion), so a consumer can tell a genuinely NULL
-- (below-min-sample) row from a well-supported one instead of guessing.

ALTER TABLE gold.game_feature ADD COLUMN home_pa numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_pa numeric;
