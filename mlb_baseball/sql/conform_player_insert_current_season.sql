-- Second pass of core.player admission (see conform_player_insert.sql for the
-- first). Retrosheet assigns a player's key_retro only months after a season
-- ends; Chadwick assigns key_mlbam immediately. So a current-season debut or
-- call-up sits in raw.register_people with an MLBAM id but no key_retro, and
-- the first pass (WHERE key_retro IS NOT NULL) drops them. backbone-2026-source
-- joins core.player on mlbam_id and lost ~8.4% of 2026 regular-season
-- player-games this way.
--
-- Admit the bounded set of MLBAM-only people who actually appear in MLB's own
-- game record -- NOT every one of the ~104k register rows that merely carry an
-- MLBAM id (that is every minor-leaguer and foreign-league player). key_retro
-- IS NULL keeps this disjoint from the first pass, so no row is inserted twice.
-- retro_id lands NULL here and backfills on the next full conform run once
-- raw.register_people carries the real key_retro (conform.run() truncates
-- core.player every time -- there is no upsert).
--
-- conform._build_players wraps this in a savepoint and swallows UndefinedTable:
-- raw.mlb_boxscore_* / raw.mlb_playbyplay are optional (a fresh clone may not
-- have run the mlb_api connector yet).
INSERT INTO core.player (
    retro_id, mlbam_id, bbref_id, fangraphs_id, chadwick_uuid,
    last_name, first_name, birth_date, death_date
)
SELECT
    key_retro,
    key_mlbam,
    key_bbref,
    key_fangraphs,
    key_uuid,
    name_last,
    name_first,
    CASE WHEN birth_year IS NOT NULL AND birth_month IS NOT NULL
              AND birth_day IS NOT NULL
         THEN make_date(birth_year::integer, birth_month::integer, birth_day::integer)
    END,
    CASE WHEN death_year IS NOT NULL AND death_month IS NOT NULL
              AND death_day IS NOT NULL
         THEN make_date(death_year::integer, death_month::integer, death_day::integer)
    END
FROM raw.register_people
WHERE key_retro IS NULL
  AND key_mlbam IN (
        SELECT person_id FROM raw.mlb_boxscore_batting
        UNION
        SELECT person_id FROM raw.mlb_boxscore_pitching
        UNION
        SELECT batter_id FROM raw.mlb_playbyplay
        UNION
        SELECT pitcher_id FROM raw.mlb_playbyplay
  )
