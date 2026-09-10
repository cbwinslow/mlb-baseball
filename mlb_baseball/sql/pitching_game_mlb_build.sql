-- Rebuild gold.pitching_game from raw.mlb_boxscore_pitching (2026 onward,
-- regular season only).
--
-- 1910-2025 is built by sql/pitching_game_build.sql from raw.retrosheet_event.
-- Retrosheet publishes no event file for the in-progress season, so the
-- current season is built here from MLB's own official per-game box-score
-- line (backbone-2026-source). The `g.season >= 2026` bound is the partition
-- line between the two builders.
--
-- source = 'mlb_boxscore' on every row this builder writes.
--
-- Unlike the Retrosheet builder (which leaves er NULL -- the event stream
-- carries no earned-run data), this builder populates `er` from MLB's
-- scorer-assigned earned_runs. That is the only reason era exists on the
-- pitching roll-ups from 2026 on; it is NULL through 2025 (migration 0102,
-- docs/TABLE_CONTRACTS.md coverage cliff).
--
-- Column mapping (raw.mlb_boxscore_pitching -> gold.pitching_game), every raw
-- column text-typed so NULLIF(x, '')::integer guards a blank cell:
--   gs  <- games_started    bf  <- batters_faced   outs <- outs
--   h   <- hits             r   <- runs            er   <- earned_runs
--   bb  <- base_on_balls    ibb <- intentional_walks
--   so  <- strike_outs      hr  <- home_runs
--   hbp <- hit_batsmen      wp  <- wild_pitches    bk   <- balks
--   w   <- wins             l   <- losses          sv   <- saves
-- (the box score's per-game wins/losses/saves are the decision for THIS game,
-- 0 or 1 -- verified against 2026 data.)
--
-- Grain: (game_id, player_id, team_id). player_id resolves via core.player on
-- the MLBAM id; team_id from the game's own home / away side by the box
-- score's MLB team_id.
--
-- One row per pitcher who actually faced a batter (batters_faced > 0) -- the
-- box score lists position players with an all-zero pitching stat group, which
-- would otherwise become empty rows.
--
-- Truncate-and-replace: the caller (report._build_backbone_relation) TRUNCATEs
-- gold.pitching_game once, then runs the Retrosheet builder and this builder
-- in the same transaction. One parameterized statement (psycopg prepare).
-- Optional %(season)s bind scopes the rebuild to one season.

INSERT INTO gold.pitching_game (
    game_id, player_id, team_id, season, game_date,
    gs, bf, outs, h, r, bb, ibb, so, hr, hbp, wp, bk, w, l, sv, er, source
)
WITH box AS (
    SELECT
        g.id AS game_id,
        g.season,
        g.game_date,
        tm.id AS team_id,
        mp.person_id,
        NULLIF(mp.games_started, '')::integer      AS gs,
        NULLIF(mp.batters_faced, '')::integer      AS bf,
        NULLIF(mp.outs, '')::integer               AS outs,
        NULLIF(mp.hits, '')::integer               AS h,
        NULLIF(mp.runs, '')::integer               AS r,
        NULLIF(mp.base_on_balls, '')::integer      AS bb,
        NULLIF(mp.intentional_walks, '')::integer  AS ibb,
        NULLIF(mp.strike_outs, '')::integer        AS so,
        NULLIF(mp.home_runs, '')::integer          AS hr,
        NULLIF(mp.hit_batsmen, '')::integer        AS hbp,
        NULLIF(mp.wild_pitches, '')::integer       AS wp,
        NULLIF(mp.balks, '')::integer              AS bk,
        NULLIF(mp.wins, '')::integer               AS w,
        NULLIF(mp.losses, '')::integer             AS l,
        NULLIF(mp.saves, '')::integer              AS sv,
        NULLIF(mp.earned_runs, '')::integer        AS er
    FROM raw.mlb_boxscore_pitching mp
    JOIN core.game g ON g.game_pk = mp.game_pk
    JOIN core.team tm
        ON tm.mlb_team_id = NULLIF(mp.team_id, '')::integer
       AND tm.id IN (g.home_team_id, g.away_team_id)
    WHERE g.season >= 2026
      AND lower(g.game_type) = 'regular'
      -- keep a line with any recorded activity: a pitcher can retire a
      -- baserunner (pickoff / caught stealing) for outs > 0 with bf = 0.
      AND (
            NULLIF(mp.batters_faced, '')::integer > 0
         OR NULLIF(mp.outs, '')::integer > 0
      )
      AND (%(season)s::integer IS NULL OR g.season = %(season)s::integer)
)
SELECT
    box.game_id,
    p.id AS player_id,
    box.team_id,
    box.season,
    box.game_date,
    box.gs, box.bf, box.outs, box.h, box.r, box.bb, box.ibb, box.so, box.hr,
    box.hbp, box.wp, box.bk, box.w, box.l, box.sv, box.er,
    'mlb_boxscore' AS source
FROM box
JOIN core.player p ON p.mlbam_id = box.person_id;
