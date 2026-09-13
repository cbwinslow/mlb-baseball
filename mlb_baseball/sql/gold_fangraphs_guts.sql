-- Rebuild gold.fangraphs_guts from raw.fangraphs_guts.
--
-- fangraphs-conform Beat 1 (ADR-290). Source: raw.fangraphs_guts, FanGraphs'
-- Guts! per-season wOBA / FIP constants (all-text landing table, one row per
-- season, full history 1871+). Grain: one row per season.
--
-- Values are cast to numeric and preserved verbatim -- no re-derivation, no
-- interpolation of missing seasons. Every season empty-string -> NULL.
--
-- REFERENCE / CROSS-CHECK ONLY. local_research: never public_safe, never in the
-- published mlb-research dataset, never a reference-baseline-model input. A wOBA
-- or FIP figure the project publishes is computed from core.play, not from here.
--
-- One statement, no per-season bind parameter (every season, like the career
-- builders). The caller (report._build_backbone_relation) TRUNCATEs
-- gold.fangraphs_guts first, in the same transaction.

INSERT INTO gold.fangraphs_guts (
    season, woba, wobascale, wbb, whbp, w1b, w2b, w3b, whr,
    runsb, runcs, r_pa, r_w, cfip
)
SELECT
    NULLIF(season, '')::integer,
    NULLIF(woba, '')::numeric,
    NULLIF(wobascale, '')::numeric,
    NULLIF(wbb, '')::numeric,
    NULLIF(whbp, '')::numeric,
    NULLIF(w1b, '')::numeric,
    NULLIF(w2b, '')::numeric,
    NULLIF(w3b, '')::numeric,
    NULLIF(whr, '')::numeric,
    NULLIF(runsb, '')::numeric,
    NULLIF(runcs, '')::numeric,
    NULLIF(r_pa, '')::numeric,
    NULLIF(r_w, '')::numeric,
    NULLIF(cfip, '')::numeric
FROM raw.fangraphs_guts
WHERE NULLIF(season, '') IS NOT NULL;
