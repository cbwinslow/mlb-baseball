-- Team weighted on-base average (wOBA), rolling within-season, no
-- leakage -- see ADR-036 and mlb_baseball/model/offense.py. Supersedes
-- the originally-planned "season-lagged Statcast xwOBA" approach from
-- docs/RESEARCH.md's backlog: reconstructing from raw.retrosheet_event
-- directly gives a genuine within-season rolling number (same quality
-- upgrade already applied to starting-pitcher quality, ADR-034), not a
-- lagged full-season aggregate.

ALTER TABLE gold.game_feature ADD COLUMN home_woba numeric;
ALTER TABLE gold.game_feature ADD COLUMN away_woba numeric;
