MODEL (
  name serve.matchup_preview,
  kind FULL,
  cron '@daily',
  grain (game_instance_key)
);

SELECT
    f.game_instance_key,
    f.game_date,
    ht.retro_team_id AS home_team,
    at.retro_team_id AS away_team,
    v.name AS venue,
    f.park_factor_3yr AS park_factor,
    f.air_density_index,
    f.effective_wind_speed,
    f.home_starter_siera,
    f.away_starter_siera,
    f.home_starter_vert_separation_in,
    f.away_starter_vert_separation_in,
    f.home_bullpen_siera,
    f.away_bullpen_siera,
    f.home_offense_xwoba,
    f.away_offense_xwoba,
    f.home_catcher_csae_pct,
    f.away_catcher_csae_pct,
    f.starter_siera_diff,
    f.starter_vert_sep_diff,
    f.bullpen_siera_diff,
    f.offense_xwoba_diff,
    f.bsr_total_diff,
    f.catcher_framing_diff,
    f.home_platoon_matchup_woba_diff,
    f.away_platoon_matchup_woba_diff
FROM gold.game_feature f
LEFT JOIN core.team ht ON ht.id = f.home_team_id
LEFT JOIN core.team at ON at.id = f.away_team_id
LEFT JOIN core.venue v ON v.id = f.venue_id;
