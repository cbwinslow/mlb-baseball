-- Platoon Splits & Handedness Matchup Calculation (PLT-01, ADR-101).
-- Computes starter throwing hand, team offense vs LHP/RHP wOBA, and net platoon advantage deltas.
--
-- Throwing hand is a one-pass DISTINCT ON (pitcher) against raw.statcast_pitch,
-- not a correlated subquery per gold.game_feature row. The old shape ran
-- `SELECT p_throws ... LIMIT 1` twice per game (home and away starter)
-- against 13.5M Statcast rows with no pitcher index -- ~400k potential
-- seq scans. Measured in production 2026-08-28: that UPDATE was still
-- running after 80+ minutes. One pass over the pitch table is enough.
--
-- home/away_offense_woba_vs_lhp/rhp (bug fix, 2026-09-17): previously both
-- set to the team's own overall wOBA regardless of pitcher hand -- not a
-- real split at all. Statcast's own per-plate-appearance woba_value/
-- woba_denom (already the correct, per-season-weighted numerator/
-- denominator Baseball Savant publishes) are now aggregated by the batting
-- team and the actual opposing pitcher's throwing hand for that PA (every
-- pitcher who actually pitched, not just the starter), then rolled up as a
-- zero-lookahead season-to-date rate (this game and everything after it
-- excluded), same ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING shape
-- team_pitcher_estimators_retrosheet_update.sql already uses for the
-- pitcher-side splits. Below MIN_PLATOON_PA prior plate appearances against
-- that hand, or before Statcast coverage begins (2015), the value is
-- correctly NULL -- an honest missing measurement, not a fabricated
-- default.

WITH starter_throws AS (
    SELECT DISTINCT ON (pitcher)
        pitcher,
        p_throws
    FROM raw.statcast_pitch
    WHERE p_throws IS NOT NULL
        AND NULLIF(pitcher, '') IS NOT NULL
    ORDER BY pitcher
),

game_starters AS (
    SELECT
        f.game_instance_key,
        f.game_id,
        f.season,
        f.game_date,
        f.home_team_id,
        f.away_team_id,
        f.home_starter_id,
        f.away_starter_id,
        COALESCE(ht.p_throws, 'R') AS home_starter_throws,
        COALESCE(at.p_throws, 'R') AS away_starter_throws
    FROM gold.game_feature AS f
    LEFT JOIN core.player AS hp ON hp.id = f.home_starter_id
    LEFT JOIN core.player AS ap ON ap.id = f.away_starter_id
    LEFT JOIN starter_throws AS ht
        ON ht.pitcher = COALESCE(
            NULLIF(hp.mlbam_id, ''),
            NULLIF(hp.retro_id, ''),
            f.home_starter_id::text
        )
    LEFT JOIN starter_throws AS at
        ON at.pitcher = COALESCE(
            NULLIF(ap.mlbam_id, ''),
            NULLIF(ap.retro_id, ''),
            f.away_starter_id::text
        )
),

-- One row per plate appearance actually faced: woba_denom is populated by
-- Statcast only on the pitch that ends a PA. game_pk (Statcast's own MLB
-- gamePk) joins to core.game.game_pk -- the project's existing, unambiguous
-- Statcast<->core.game link -- rather than re-deriving a team-abbreviation
-- crosswalk (Statcast's short codes diverge from core.team.retro_team_id in
-- more places than the D-backs/Rays/Guardians case team_oaa_update.sql
-- already has to handle).
offense_pa AS (
    SELECT
        g.id AS game_id,
        g.season,
        g.game_date,
        g.game_number,
        CASE WHEN sp.inning_topbot = 'Top' THEN g.away_team_id ELSE g.home_team_id END
            AS batting_team_id,
        sp.p_throws,
        sp.woba_value::numeric AS woba_value,
        sp.woba_denom::numeric AS woba_denom
    FROM raw.statcast_pitch AS sp
    JOIN core.game AS g ON g.game_pk = sp.game_pk
    WHERE NULLIF(sp.woba_denom, '') IS NOT NULL
        AND sp.p_throws IN ('L', 'R')
),

offense_team_game_agg AS (
    SELECT
        game_id,
        season,
        game_date,
        game_number,
        batting_team_id,
        SUM(woba_value) FILTER (WHERE p_throws = 'L') AS woba_val_lhp,
        SUM(woba_denom) FILTER (WHERE p_throws = 'L') AS woba_den_lhp,
        SUM(woba_value) FILTER (WHERE p_throws = 'R') AS woba_val_rhp,
        SUM(woba_denom) FILTER (WHERE p_throws = 'R') AS woba_den_rhp
    FROM offense_pa
    GROUP BY game_id, season, game_date, game_number, batting_team_id
),

offense_team_rolling AS (
    SELECT
        game_id,
        batting_team_id,
        SUM(woba_val_lhp) OVER w AS prior_woba_val_lhp,
        SUM(woba_den_lhp) OVER w AS prior_woba_den_lhp,
        SUM(woba_val_rhp) OVER w AS prior_woba_val_rhp,
        SUM(woba_den_rhp) OVER w AS prior_woba_den_rhp
    FROM offense_team_game_agg
    WINDOW w AS (
        PARTITION BY batting_team_id, season
        ORDER BY game_date, COALESCE(game_number, 0), game_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
    )
),

offense_team_rates AS (
    SELECT
        game_id,
        batting_team_id,
        CASE
            WHEN prior_woba_den_lhp >= %(min_platoon_pa)s
                THEN ROUND((prior_woba_val_lhp / NULLIF(prior_woba_den_lhp, 0))::numeric, 4)
            ELSE NULL
        END AS offense_woba_vs_lhp,
        CASE
            WHEN prior_woba_den_rhp >= %(min_platoon_pa)s
                THEN ROUND((prior_woba_val_rhp / NULLIF(prior_woba_den_rhp, 0))::numeric, 4)
            ELSE NULL
        END AS offense_woba_vs_rhp
    FROM offense_team_rolling
)

UPDATE gold.game_feature AS gf
SET
    home_starter_throws = gs.home_starter_throws,
    away_starter_throws = gs.away_starter_throws,
    home_offense_woba_vs_lhp = hr.offense_woba_vs_lhp,
    home_offense_woba_vs_rhp = hr.offense_woba_vs_rhp,
    away_offense_woba_vs_lhp = ar.offense_woba_vs_lhp,
    away_offense_woba_vs_rhp = ar.offense_woba_vs_rhp,
    home_platoon_matchup_woba_diff = ROUND(
        CASE
            WHEN gs.away_starter_throws = 'L'
                THEN COALESCE(gf.home_woba, 0.320)
                - COALESCE(gf.away_starter_vs_lhb_woba, 0.320)
            ELSE COALESCE(gf.home_woba, 0.320)
                - COALESCE(gf.away_starter_vs_rhb_woba, 0.320)
        END,
        3
    ),
    away_platoon_matchup_woba_diff = ROUND(
        CASE
            WHEN gs.home_starter_throws = 'L'
                THEN COALESCE(gf.away_woba, 0.320)
                - COALESCE(gf.home_starter_vs_lhb_woba, 0.320)
            ELSE COALESCE(gf.away_woba, 0.320)
                - COALESCE(gf.home_starter_vs_rhb_woba, 0.320)
        END,
        3
    )
FROM game_starters AS gs
LEFT JOIN offense_team_rates AS hr
    ON hr.game_id = gs.game_id AND hr.batting_team_id = gs.home_team_id
LEFT JOIN offense_team_rates AS ar
    ON ar.game_id = gs.game_id AND ar.batting_team_id = gs.away_team_id
WHERE gf.game_instance_key = gs.game_instance_key;
