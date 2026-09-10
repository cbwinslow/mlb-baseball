-- Rebuild gold.batting_game from raw.mlb_boxscore_batting (2026 onward,
-- regular season only).
--
-- 1910-2025 is built by sql/batting_game_build.sql from raw.retrosheet_event.
-- Retrosheet publishes no event file for the in-progress season, so the
-- current season is built here from MLB's own official per-game box-score
-- line (backbone-2026-source). The `g.season >= 2026` bound is the partition
-- line: the two builders never write the same (game, player, team) key.
--
-- source = 'mlb_boxscore' on every row this builder writes (the Retrosheet
-- builder writes source = 'retrosheet_event', the column default).
--
-- Column mapping (raw.mlb_boxscore_batting -> gold.batting_game), every raw
-- column text-typed so NULLIF(x, '')::integer guards a blank cell:
--   pa   <- plate_appearances      ab  <- at_bats        r    <- runs
--   h    <- hits                   b2  <- doubles        b3   <- triples
--   hr   <- home_runs              tb  <- total_bases    rbi  <- rbi
--   bb   <- base_on_balls          ibb <- intentional_walks
--   hbp  <- hit_by_pitch           sf  <- sac_flies      sh   <- sac_bunts
--   so   <- strike_outs            gidp <- ground_into_double_play
--   b1   = h - b2 - b3 - hr        (MLB does not publish singles directly)
--
-- Grain: (game_id, player_id, team_id). player_id resolves via core.player on
-- the MLBAM id (raw person_id); team_id resolves from the game's own home /
-- away side by the box score's MLB team_id, so a box score whose team is not
-- one of the game's two teams is dropped rather than mis-attributed.
--
-- Known limitations (left NULL/0 with a reason, never guessed):
--   * Stolen bases / caught stealing are carried by the 2026 box score but
--     stay out of the batting relations (deferred to a future baserunning
--     relation, for cross-era consistency with the 1910-2025 rows).
--   * The 2026 line is MLB's scorer-assigned box score, not event-derived
--     like 1910-2025. Correctness is cross-checked against an independent
--     reconstruction from raw.mlb_playbyplay (scripts/verify_mlb_boxscore_tie_out.py),
--     the 2026 analogue of the Baseball-Reference tie-out.
--   * ~215 2026 regular-season core.game rows have no box score yet (ingest
--     freshness, not a builder defect) -- visible via the mlb doctor
--     join-coverage check.
--
-- Truncate-and-replace: the caller (report._build_backbone_relation) TRUNCATEs
-- gold.batting_game once, then runs the Retrosheet builder and this builder in
-- the same transaction. This file is one parameterized statement so psycopg
-- can prepare it. Optional %(season)s bind scopes the rebuild to one season;
-- NULL rebuilds every 2026+ season.

INSERT INTO gold.batting_game (
    game_id, player_id, team_id, season, game_date,
    pa, ab, r, h, b1, b2, b3, hr, tb, rbi, bb, ibb, hbp, sf, sh, so, gidp, source
)
WITH box AS (
    SELECT
        g.id AS game_id,
        g.season,
        g.game_date,
        tm.id AS team_id,
        mb.person_id,
        NULLIF(mb.plate_appearances, '')::integer        AS pa,
        NULLIF(mb.at_bats, '')::integer                  AS ab,
        NULLIF(mb.runs, '')::integer                     AS r,
        NULLIF(mb.hits, '')::integer                     AS h,
        NULLIF(mb.doubles, '')::integer                  AS b2,
        NULLIF(mb.triples, '')::integer                  AS b3,
        NULLIF(mb.home_runs, '')::integer               AS hr,
        NULLIF(mb.total_bases, '')::integer             AS tb,
        NULLIF(mb.rbi, '')::integer                      AS rbi,
        NULLIF(mb.base_on_balls, '')::integer           AS bb,
        NULLIF(mb.intentional_walks, '')::integer       AS ibb,
        NULLIF(mb.hit_by_pitch, '')::integer            AS hbp,
        NULLIF(mb.sac_flies, '')::integer               AS sf,
        NULLIF(mb.sac_bunts, '')::integer               AS sh,
        NULLIF(mb.strike_outs, '')::integer             AS so,
        NULLIF(mb.ground_into_double_play, '')::integer AS gidp
    FROM raw.mlb_boxscore_batting mb
    JOIN core.game g ON g.game_pk = mb.game_pk
    JOIN core.team tm
        ON tm.mlb_team_id = NULLIF(mb.team_id, '')::integer
       AND tm.id IN (g.home_team_id, g.away_team_id)
    WHERE g.season >= 2026
      AND lower(g.game_type) = 'regular'
      AND NULLIF(mb.plate_appearances, '')::integer > 0
      AND (%(season)s::integer IS NULL OR g.season = %(season)s::integer)
)
SELECT
    box.game_id,
    p.id AS player_id,
    box.team_id,
    box.season,
    box.game_date,
    box.pa, box.ab, box.r, box.h,
    box.h - box.b2 - box.b3 - box.hr AS b1,
    box.b2, box.b3, box.hr, box.tb, box.rbi, box.bb, box.ibb, box.hbp,
    box.sf, box.sh, box.so, box.gidp,
    'mlb_boxscore' AS source
FROM box
JOIN core.player p ON p.mlbam_id = box.person_id;
