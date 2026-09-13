-- Earned runs (er) and earned-run average (era) on the event/box-score
-- pitching backbone.
--
-- backbone-2026-source change. The 1910-2025 Retrosheet-event builder cannot
-- produce earned runs (reconstructed-inning logic cwevent does not emit -- see
-- migration 0095 / batting_game comments), so it writes er = NULL and era stays
-- NULL. The 2026-onward builder over raw.mlb_boxscore_pitching carries MLB's
-- scorer-assigned earned_runs, so er and era are populated there.
--
-- COVERAGE CLIFF: era is NULL for every pitcher-season through 2025 and
-- populated from 2026 on. ra9 (runs allowed per 9, from `r`) is the honest
-- cross-era rate and is populated for every year. A career-grain era exists
-- only for a pitcher whose entire career is 2026+ (every contributing season
-- must have a non-NULL er). See docs/TABLE_CONTRACTS.md.
--
-- Additive and reversible: ADD COLUMN only, no backfill. Rollback is
-- `ALTER TABLE ... DROP COLUMN er, DROP COLUMN era`.

ALTER TABLE gold.pitching_game
    ADD COLUMN IF NOT EXISTS er integer;   -- earned runs; NULL for 1910-2025 (event stream has none)

ALTER TABLE gold.pitching_season
    ADD COLUMN IF NOT EXISTS er  integer,  -- sum of game er; NULL if any contributing game lacks it
    ADD COLUMN IF NOT EXISTS era numeric;  -- er * 27 / outs; NULL through 2025, populated 2026+

ALTER TABLE gold.pitching_career
    ADD COLUMN IF NOT EXISTS er  integer,  -- sum of season er; NULL unless every season has er
    ADD COLUMN IF NOT EXISTS era numeric;  -- er * 27 / outs; career era only for wholly-2026+ careers

COMMENT ON COLUMN gold.pitching_game.er IS
    'Earned runs. NULL for 1910-2025 (Retrosheet events carry no earned-run data); populated from 2026 via raw.mlb_boxscore_pitching. Use r / ra9 for a cross-era figure.';
COMMENT ON COLUMN gold.pitching_season.era IS
    'Earned-run average (er * 27 / outs). NULL through 2025, populated from 2026. ra9 is the cross-era rate. backbone-2026-source.';
COMMENT ON COLUMN gold.pitching_career.era IS
    'Career ERA. NULL unless every season in the career has earned-run data (i.e. a wholly-2026+ career). ra9 is the cross-era rate. backbone-2026-source.';
