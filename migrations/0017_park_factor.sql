-- Park factor: standard methodology (FanGraphs/Baseball Prospectus) --
-- ratio of a venue's home run-scoring rate to the same teams' road rate,
-- scaled to 100 = league average, over a trailing multi-year window --
-- see ADR-035 and mlb_baseball/model/park.py.

ALTER TABLE gold.game_feature ADD COLUMN park_factor numeric;
