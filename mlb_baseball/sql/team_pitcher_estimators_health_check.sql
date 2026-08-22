-- Health check assertions for starter/bullpen xFIP, SIERA, and platoon metrics.
-- Ensures domain bounds on all calculated metrics.

SELECT
    count(*) AS total_rows,
    count(home_starter_xfip) AS home_starter_xfip_rows,
    count(away_starter_xfip) AS away_starter_xfip_rows,
    count(home_starter_siera) AS home_starter_siera_rows,
    count(away_starter_siera) AS away_starter_siera_rows,
    count(home_starter_vs_lhb_woba) AS home_starter_vs_lhb_woba_rows,
    count(away_starter_vs_lhb_woba) AS away_starter_vs_lhb_woba_rows,
    count(home_starter_vs_rhb_woba) AS home_starter_vs_rhb_woba_rows,
    count(away_starter_vs_rhb_woba) AS away_starter_vs_rhb_woba_rows,
    count(home_starter_vs_lhb_k_pct) AS home_starter_vs_lhb_k_pct_rows,
    count(away_starter_vs_lhb_k_pct) AS away_starter_vs_lhb_k_pct_rows,
    count(home_starter_vs_rhb_k_pct) AS home_starter_vs_rhb_k_pct_rows,
    count(away_starter_vs_rhb_k_pct) AS away_starter_vs_rhb_k_pct_rows,
    count(home_bullpen_xfip) AS home_bullpen_xfip_rows,
    count(away_bullpen_xfip) AS away_bullpen_xfip_rows,
    count(home_bullpen_siera) AS home_bullpen_siera_rows,
    count(away_bullpen_siera) AS away_bullpen_siera_rows,
    -- Domain violation checks (should all be 0)
    count(*) FILTER (WHERE home_starter_xfip IS NOT NULL AND (home_starter_xfip < 0 OR home_starter_xfip > 25)) AS home_starter_xfip_out_of_bounds,
    count(*) FILTER (WHERE away_starter_xfip IS NOT NULL AND (away_starter_xfip < 0 OR away_starter_xfip > 25)) AS away_starter_xfip_out_of_bounds,
    count(*) FILTER (WHERE home_starter_siera IS NOT NULL AND (home_starter_siera < 0 OR home_starter_siera > 25)) AS home_starter_siera_out_of_bounds,
    count(*) FILTER (WHERE away_starter_siera IS NOT NULL AND (away_starter_siera < 0 OR away_starter_siera > 25)) AS away_starter_siera_out_of_bounds,
    count(*) FILTER (WHERE home_bullpen_xfip IS NOT NULL AND (home_bullpen_xfip < 0 OR home_bullpen_xfip > 25)) AS home_bullpen_xfip_out_of_bounds,
    count(*) FILTER (WHERE away_bullpen_xfip IS NOT NULL AND (away_bullpen_xfip < 0 OR away_bullpen_xfip > 25)) AS away_bullpen_xfip_out_of_bounds,
    count(*) FILTER (WHERE home_bullpen_siera IS NOT NULL AND (home_bullpen_siera < 0 OR home_bullpen_siera > 25)) AS home_bullpen_siera_out_of_bounds,
    count(*) FILTER (WHERE away_bullpen_siera IS NOT NULL AND (away_bullpen_siera < 0 OR away_bullpen_siera > 25)) AS away_bullpen_siera_out_of_bounds,
    count(*) FILTER (WHERE home_starter_vs_lhb_k_pct IS NOT NULL AND (home_starter_vs_lhb_k_pct < 0 OR home_starter_vs_lhb_k_pct > 1)) AS home_vs_lhb_k_pct_out_of_bounds,
    count(*) FILTER (WHERE away_starter_vs_lhb_k_pct IS NOT NULL AND (away_starter_vs_lhb_k_pct < 0 OR away_starter_vs_lhb_k_pct > 1)) AS away_vs_lhb_k_pct_out_of_bounds,
    count(*) FILTER (WHERE home_starter_vs_rhb_k_pct IS NOT NULL AND (home_starter_vs_rhb_k_pct < 0 OR home_starter_vs_rhb_k_pct > 1)) AS home_vs_rhb_k_pct_out_of_bounds,
    count(*) FILTER (WHERE away_starter_vs_rhb_k_pct IS NOT NULL AND (away_starter_vs_rhb_k_pct < 0 OR away_starter_vs_rhb_k_pct > 1)) AS away_vs_rhb_k_pct_out_of_bounds,
    count(*) FILTER (WHERE home_starter_vs_lhb_woba IS NOT NULL AND (home_starter_vs_lhb_woba < 0 OR home_starter_vs_lhb_woba > 2.5)) AS home_vs_lhb_woba_out_of_bounds,
    count(*) FILTER (WHERE away_starter_vs_lhb_woba IS NOT NULL AND (away_starter_vs_lhb_woba < 0 OR away_starter_vs_lhb_woba > 2.5)) AS away_vs_lhb_woba_out_of_bounds,
    count(*) FILTER (WHERE home_starter_vs_rhb_woba IS NOT NULL AND (home_starter_vs_rhb_woba < 0 OR home_starter_vs_rhb_woba > 2.5)) AS home_vs_rhb_woba_out_of_bounds,
    count(*) FILTER (WHERE away_starter_vs_rhb_woba IS NOT NULL AND (away_starter_vs_rhb_woba < 0 OR away_starter_vs_rhb_woba > 2.5)) AS away_vs_rhb_woba_out_of_bounds
FROM gold.game_feature;
