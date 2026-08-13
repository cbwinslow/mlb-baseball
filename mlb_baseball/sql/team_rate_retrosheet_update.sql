-- Prior rolling team OBP/SLG/ISO/BB%%/K%% (OFF-01/02/03). Two corrections
-- versus the earlier team_woba_retrosheet_update.sql this was originally
-- modeled on (both found by an independent whole-branch review after the
-- fact, ADR-061 follow-up):
--
-- 1. Every event_cd FILTER is gated on `bat_event_fl = 'T'`, matching
--    team_starter_retrosheet_update.sql / team_bullpen_retrosheet_update.sql
--    (ADR-034). bat_event_fl='T' is what actually scopes a raw.
--    retrosheet_event row to a real plate appearance; without it, K/BB/
--    HBP/hit counts can double-count Retrosheet's own non-batter-event
--    artifact rows. ADR-034's own docstring (mlb_baseball/model/
--    starter.py) documents a real deGrom-2018 reconciliation proving this
--    guard is required, not optional -- team_woba_retrosheet_update.sql
--    predates that finding and has the same gap, tracked separately
--    (github.com/cbwinslow/mlb-baseball/issues/9), not fixed here.
-- 2. The rolling window orders by `game_date, game_number NULLS LAST,
--    game_id`, not `game_date, game_id` alone -- matching the base
--    family's own window (mlb_baseball/sql/game_feature_rebuild.sql,
--    migration 0046). Ordering by game_id (an insertion-order serial)
--    made a doubleheader's prior-game order depend on load order rather
--    than the declared game_number, a real point-in-time-safety gap for
--    same-date games loaded out of order across separate ingestion runs.
--
-- SUM(...) OVER an UNBOUNDED PRECEDING .. 1 PRECEDING window: the value
-- entering a game reflects every completed game strictly before it,
-- within the same season.

WITH regular_games AS (
    SELECT g.id AS game_id, g.season, g.game_date, g.game_number, g.retro_game_id,
        g.home_team_id, g.away_team_id
    FROM core.game g
    WHERE g.game_type = 'regular'
),
team_game_stats AS (
    SELECT
        rg.game_id, rg.season, rg.game_date, rg.game_number,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END AS team_id,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '14') AS ubb,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '15') AS ibb,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '16') AS hbp,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '20') AS b1,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '21') AS b2,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '22') AS b3,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '23') AS hr,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '3') AS so,
        count(*) FILTER (WHERE re.ab_fl = 'T') AS ab,
        count(*) FILTER (WHERE re.sf_fl = 'T') AS sf
    FROM regular_games rg
    JOIN raw.retrosheet_gameinfo gi ON gi.gid = rg.retro_game_id AND lower(gi.gametype) = 'regular'
    JOIN raw.retrosheet_event re ON re.game_id = rg.retro_game_id
    GROUP BY rg.game_id, rg.season, rg.game_date, rg.game_number,
        CASE WHEN re.bat_home_id = '1' THEN rg.home_team_id ELSE rg.away_team_id END
),
rolling AS (
    SELECT game_id, team_id,
        SUM(ubb) OVER w AS ubb_sum, SUM(ibb) OVER w AS ibb_sum, SUM(hbp) OVER w AS hbp_sum,
        SUM(b1) OVER w AS b1_sum, SUM(b2) OVER w AS b2_sum, SUM(b3) OVER w AS b3_sum,
        SUM(hr) OVER w AS hr_sum, SUM(so) OVER w AS so_sum,
        SUM(ab) OVER w AS ab_sum, SUM(sf) OVER w AS sf_sum
    FROM team_game_stats
    WINDOW w AS (
        PARTITION BY team_id, season ORDER BY game_date, game_number NULLS LAST, game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),
-- Min-sample gate (ADR-062): below MIN_PA/MIN_AB plate appearances or at-
-- bats, a rate stat is one bad-luck game away from a wildly misleading
-- ratio (e.g. 1-for-1 reads as a 1.000 OBP) -- no gate existed anywhere in
-- this codebase before this (mlb_baseball/model/offense.py's wOBA
-- documents the same small-sample-noise risk in its health_check()
-- docstring but deliberately does not filter it; this establishes the
-- first precedent). MIN_PA=10 / MIN_AB=8 are scaled for this module's
-- entering-value, point-in-time context -- an early-season team can
-- easily have single-digit PA/AB entering its second or third game of a
-- season -- not a season-total batting-title qualification threshold
-- (e.g. 3.1 PA/team-game), which would leave most of a season NULL. PA
-- and AB are gated independently: OBP/BB%%/K%% depend on PA, SLG/ISO depend
-- on AB, and a team can clear one threshold while still below the other
-- (e.g. a string of walks raises PA without touching AB). pa_sum itself
-- is never gated -- it is exposed ungated so a consumer can see why a
-- gated rate is NULL rather than confusing "no data yet" with "sample too
-- small".
rate AS (
    SELECT game_id, team_id, ab_sum, hbp_sum, sf_sum, so_sum,
        (b1_sum + b2_sum + b3_sum + hr_sum) AS hits_sum,
        (b1_sum + 2 * b2_sum + 3 * b3_sum + 4 * hr_sum) AS tb_sum,
        (ubb_sum + ibb_sum) AS bb_sum,
        (ab_sum + ubb_sum + ibb_sum + sf_sum + hbp_sum) AS pa_sum
    FROM rolling
),
computed AS (
    SELECT game_id, team_id, pa_sum,
        CASE WHEN pa_sum >= %(min_pa)s THEN
            (hits_sum + bb_sum + hbp_sum)::numeric / NULLIF(pa_sum, 0)
        END AS obp,
        CASE WHEN ab_sum >= %(min_ab)s THEN tb_sum::numeric / ab_sum END AS slg,
        CASE WHEN ab_sum >= %(min_ab)s THEN
            (tb_sum::numeric / ab_sum) - (hits_sum::numeric / ab_sum)
        END AS iso,
        CASE WHEN pa_sum >= %(min_pa)s THEN bb_sum::numeric / pa_sum END AS bb_pct,
        CASE WHEN pa_sum >= %(min_pa)s THEN so_sum::numeric / pa_sum END AS k_pct
    FROM rate
)
UPDATE gold.game_feature f
SET home_obp = ch.obp, away_obp = ca.obp,
    home_slg = ch.slg, away_slg = ca.slg,
    home_iso = ch.iso, away_iso = ca.iso,
    home_bb_pct = ch.bb_pct, away_bb_pct = ca.bb_pct,
    home_k_pct = ch.k_pct, away_k_pct = ca.k_pct,
    home_pa = ch.pa_sum, away_pa = ca.pa_sum
FROM regular_games rg
LEFT JOIN computed ch ON ch.game_id = rg.game_id AND ch.team_id = rg.home_team_id
LEFT JOIN computed ca ON ca.game_id = rg.game_id AND ca.team_id = rg.away_team_id
WHERE f.game_id = rg.game_id;
