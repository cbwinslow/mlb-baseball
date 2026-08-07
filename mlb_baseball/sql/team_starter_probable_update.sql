WITH latest_probable AS (
    -- One row per (game_pk, side): the most recently captured probable --
    -- raw.mlb_probable is append-only specifically so a later snapshot (a
    -- scratch, a rotation swap) always wins over an earlier one instead of
    -- the first announcement staying authoritative forever.
    SELECT DISTINCT ON (game_pk, side) game_pk, side, pitcher_id
    FROM raw.mlb_probable
    WHERE pitcher_id IS NOT NULL
    ORDER BY game_pk, side, _loaded_at DESC
),
targets AS (
    -- Every still-upcoming game_feature row with an announced probable on
    -- at least one side. mlb_game_pk / raw.mlb_probable.game_pk are both
    -- MLB's own numeric game id (text, per the raw layer's own
    -- convention) -- no crosswalk needed for the game itself, only for
    -- the pitcher (below).
    SELECT f.id AS feature_id, f.game_date,
        hp.pitcher_id AS home_pitcher_id, ap.pitcher_id AS away_pitcher_id
    FROM gold.game_feature f
    LEFT JOIN latest_probable hp ON hp.game_pk = f.mlb_game_pk AND hp.side = 'home'
    LEFT JOIN latest_probable ap ON ap.game_pk = f.mlb_game_pk AND ap.side = 'away'
    WHERE f.home_win IS NULL AND (hp.pitcher_id IS NOT NULL OR ap.pitcher_id IS NOT NULL)
),
-- Every pitcher's own 2026 appearance, at (pitcher, calendar day) grain --
-- identical event-type mapping and per-play outs-diff logic as
-- compute_live()'s own play_outs/pitcher_game_stats (see that function's
-- docstring for why outs needs a LAG diff, not a direct column), just
-- dated via raw.mlb_schedule instead of core.game.
play_outs AS (
    SELECT pbp.game_pk, pbp.pitcher_id, pbp.event_type, ms.game_date::date AS game_date,
        pbp.outs::int - LAG(pbp.outs::int, 1, 0) OVER (
            PARTITION BY pbp.game_pk, pbp.inning, pbp.half_inning ORDER BY pbp.at_bat_index::int
        ) AS outs_this_play
    FROM raw.mlb_playbyplay pbp
    JOIN raw.mlb_schedule ms ON ms.game_id = pbp.game_pk AND ms.game_type = 'R'
),
pitcher_game_stats AS (
    SELECT pitcher_id, game_date,
        count(*) FILTER (WHERE event_type IN ('strikeout', 'strikeout_double_play')) AS k,
        count(*) FILTER (WHERE event_type IN ('walk', 'intent_walk')) AS bb,
        count(*) FILTER (WHERE event_type = 'home_run') AS hr,
        count(*) FILTER (WHERE event_type NOT IN (
            'caught_stealing_2b', 'caught_stealing_3b', 'caught_stealing_home',
            'pickoff_1b', 'pickoff_2b', 'pickoff_3b',
            'pickoff_caught_stealing_2b', 'pickoff_caught_stealing_3b',
            'wild_pitch', 'game_advisory'
        )) AS bf,
        sum(outs_this_play) AS outs
    FROM play_outs
    GROUP BY pitcher_id, game_date
),
-- Entering-this-(not-yet-played)-start totals: every one of the probable
-- pitcher's OWN appearances strictly before the target game's own date --
-- "through yesterday," not "as of right now," matters when a probable is
-- announced several days out and the pitcher makes another start in
-- between (a real, if rare, timing gap -- not glossed over). A pitcher
-- with zero qualifying prior appearances (a call-up making their MLB
-- debut) correctly leaves every rate NULL below -- identity (the id
-- itself) still resolves in the final UPDATE, just not a computed rate.
home_quality AS (
    SELECT t.feature_id,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.k)::numeric / sum(s.bf) END AS k_pct,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.bb)::numeric / sum(s.bf) END AS bb_pct,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.hr)::numeric / sum(s.bf) END AS hr_pct,
        CASE WHEN sum(s.outs) > 0 THEN
            (13 * sum(s.hr) + 3 * sum(s.bb) - 2 * sum(s.k))::numeric / (sum(s.outs) / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM targets t
    JOIN pitcher_game_stats s ON s.pitcher_id = t.home_pitcher_id AND s.game_date < t.game_date
    GROUP BY t.feature_id
),
away_quality AS (
    SELECT t.feature_id,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.k)::numeric / sum(s.bf) END AS k_pct,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.bb)::numeric / sum(s.bf) END AS bb_pct,
        CASE WHEN sum(s.bf) > 0 THEN sum(s.hr)::numeric / sum(s.bf) END AS hr_pct,
        CASE WHEN sum(s.outs) > 0 THEN
            (13 * sum(s.hr) + 3 * sum(s.bb) - 2 * sum(s.k))::numeric / (sum(s.outs) / 3.0)
                + %(fip_constant)s
        END AS fip
    FROM targets t
    JOIN pitcher_game_stats s ON s.pitcher_id = t.away_pitcher_id AND s.game_date < t.game_date
    GROUP BY t.feature_id
)
UPDATE gold.game_feature f
SET
    home_starter_id = hp.id,
    home_starter_era = hq.fip,
    home_starter_k_pct = hq.k_pct,
    home_starter_bb_pct = hq.bb_pct,
    home_starter_hr_pct = hq.hr_pct,
    away_starter_id = ap.id,
    away_starter_era = aq.fip,
    away_starter_k_pct = aq.k_pct,
    away_starter_bb_pct = aq.bb_pct,
    away_starter_hr_pct = aq.hr_pct
FROM targets t
LEFT JOIN core.player hp ON hp.mlbam_id = t.home_pitcher_id
LEFT JOIN core.player ap ON ap.mlbam_id = t.away_pitcher_id
LEFT JOIN home_quality hq ON hq.feature_id = t.feature_id
LEFT JOIN away_quality aq ON aq.feature_id = t.feature_id
WHERE f.id = t.feature_id
