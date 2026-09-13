-- Rebuild gold.fangraphs_park_factors from raw.fangraphs_park_factors.
--
-- fangraphs-conform Beat 1 (ADR-290). Source: raw.fangraphs_park_factors,
-- FanGraphs' basic and component park factors (all-text landing table, one row
-- per (season, team)). Grain: one row per (season, team_id).
--
-- team resolution: raw's `team` is a FanGraphs nickname ("Yankees", "Red Sox",
-- "Guardians", and the historically accurate "Indians"/"Cleveland",
-- "Devil Rays"/"Rays", "Expos"/"Nationals"). It resolves to core.team via the
-- 'fangraphs' source block seeded into core.team_alias by
-- conform.py::_TEAM_ALIAS_SEED. A `team` with no alias produces no row (surfaced
-- by report.health_check's join-coverage check), never a null/guessed team.
--
-- SCOPE: season >= 2003. Pre-2003 FanGraphs park factors are low value and the
-- franchise set is unstable; those rows stay in raw (deferred).
--
-- Component factors are kept as the source publishes them (numeric cast only).
--
-- REFERENCE / CROSS-CHECK ONLY. local_research: never public_safe, never in the
-- published mlb-research dataset, never a reference-baseline-model input.
--
-- One statement, no per-season bind parameter. The caller
-- (report._build_backbone_relation) TRUNCATEs gold.fangraphs_park_factors
-- first, in the same transaction.

INSERT INTO gold.fangraphs_park_factors (
    season, team_id,
    basic_5yr, pf_3yr, pf_1yr, pf_1b, pf_2b, pf_3b, pf_hr,
    pf_so, pf_bb, pf_gb, pf_fb, pf_ld, pf_iffb, pf_fip
)
SELECT
    NULLIF(pf.season, '')::integer,
    t.id,
    NULLIF(pf.basic__5yr_, '')::numeric,
    NULLIF(pf.n3yr, '')::numeric,
    NULLIF(pf.n1yr, '')::numeric,
    NULLIF(pf.n1b, '')::numeric,
    NULLIF(pf.n2b, '')::numeric,
    NULLIF(pf.n3b, '')::numeric,
    NULLIF(pf.hr, '')::numeric,
    NULLIF(pf.so, '')::numeric,
    NULLIF(pf.bb, '')::numeric,
    NULLIF(pf.gb, '')::numeric,
    NULLIF(pf.fb, '')::numeric,
    NULLIF(pf.ld, '')::numeric,
    NULLIF(pf.iffb, '')::numeric,
    NULLIF(pf.fip, '')::numeric
FROM raw.fangraphs_park_factors AS pf
INNER JOIN core.team_alias AS a
    ON a.source = 'fangraphs' AND lower(a.alias) = lower(pf.team)
INNER JOIN core.team AS t
    ON t.id = a.team_id
WHERE NULLIF(pf.season, '')::integer >= 2003;
