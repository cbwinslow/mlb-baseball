-- gold.fangraphs_guts / gold.fangraphs_park_factors -- two FanGraphs reference
-- lookups conformed out of the (shipped-in-#173, ADR-288, so-far-unused)
-- raw.fangraphs_* landing tables.
--
-- fangraphs-conform Beat 1 (ADR-290). Built by `mlb report`
-- (report._build_backbone_relation, truncate-and-replace, skips cleanly on a
-- database that never ingested FanGraphs). Beat 1 is these two lookups only;
-- FanGraphs projections (feat.fangraphs_projection) and the full WAR / wOBA /
-- wRC+ / Stuff+ season-line conform are deferred.
--
--   * gold.fangraphs_guts        -- one row per season: FanGraphs' Guts!
--     per-season wOBA / FIP linear-weight constants, cast to numeric and
--     preserved verbatim from raw.fangraphs_guts (full history 1871+).
--   * gold.fangraphs_park_factors -- one row per (season, team_id): FanGraphs'
--     basic and component park factors, team resolved to core.team via a new
--     'fangraphs' source block in core.team_alias. Scoped season >= 2003;
--     pre-2003 rows stay in raw (low value, unstable franchise set).
--
-- RIGHTS: local_research only (FanGraphs, ADR-290). Never public_safe, never in
-- the published mlb-research dataset, never a reference-baseline-model input.
-- gold.fangraphs_guts is a cross-check / reference: a publishable wOBA / FIP is
-- computed from core.play, not from here.
--
-- Additive and reversible: rollback is
--   DROP TABLE gold.fangraphs_park_factors, gold.fangraphs_guts;
--   ALTER TABLE core.team_alias DROP CONSTRAINT team_alias_alias_source_key,
--     ADD CONSTRAINT team_alias_alias_key UNIQUE (alias);

CREATE TABLE IF NOT EXISTS gold.fangraphs_guts (
    season      integer PRIMARY KEY,
    woba        numeric,   -- league wOBA that season
    wobascale   numeric,   -- wOBA scale (divides the linear-weight run values)
    wbb         numeric,   -- run value of an unintentional walk
    whbp        numeric,   -- run value of a hit by pitch
    w1b         numeric,   -- run value of a single
    w2b         numeric,   -- run value of a double
    w3b         numeric,   -- run value of a triple
    whr         numeric,   -- run value of a home run
    runsb       numeric,   -- run value of a stolen base
    runcs       numeric,   -- run value of a caught stealing
    r_pa        numeric,   -- league runs per plate appearance
    r_w         numeric,   -- league runs per win
    cfip        numeric,   -- FIP constant that season
    _built_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE gold.fangraphs_guts IS
    'local_research only (FanGraphs, ADR-290) -- never public_safe, never in the '
    'published mlb-research dataset, never a reference-baseline-model input. '
    'gold.fangraphs_guts is a cross-check/reference: a publishable wOBA/FIP is '
    'computed from core.play, not from here.';


CREATE TABLE IF NOT EXISTS gold.fangraphs_park_factors (
    season      integer NOT NULL,
    team_id     bigint  NOT NULL REFERENCES core.team (id),
    basic_5yr   numeric,   -- FanGraphs "Basic (5yr)" park factor
    pf_3yr      numeric,   -- 3-year park factor
    pf_1yr      numeric,   -- 1-year park factor
    pf_1b       numeric,   -- single component
    pf_2b       numeric,   -- double component
    pf_3b       numeric,   -- triple component
    pf_hr       numeric,   -- home-run component
    pf_so       numeric,   -- strikeout component
    pf_bb       numeric,   -- walk component
    pf_gb       numeric,   -- ground-ball component
    pf_fb       numeric,   -- fly-ball component
    pf_ld       numeric,   -- line-drive component
    pf_iffb     numeric,   -- infield-fly component
    pf_fip      numeric,   -- FIP-based park factor
    _built_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (season, team_id)
);

CREATE INDEX IF NOT EXISTS fangraphs_park_factors_season_idx
    ON gold.fangraphs_park_factors (season);

COMMENT ON TABLE gold.fangraphs_park_factors IS
    'local_research only (FanGraphs, ADR-290) -- never public_safe, never in the '
    'published mlb-research dataset, never a reference-baseline-model input. '
    'gold.fangraphs_guts is a cross-check/reference: a publishable wOBA/FIP is '
    'computed from core.play, not from here.';


-- core.team_alias grew a third alias vocabulary in this change (FanGraphs team
-- nicknames), and FanGraphs shares two display strings with the existing
-- 'rebrand' block ("Athletics" -> OAK, "Rays" -> TBA). The single-column
-- UNIQUE(alias) from migration 0009 pre-dates a multi-source crosswalk; the
-- correct key for "one row per (alternate name, source)" is composite.
ALTER TABLE core.team_alias DROP CONSTRAINT IF EXISTS team_alias_alias_key;
ALTER TABLE core.team_alias
    ADD CONSTRAINT team_alias_alias_source_key UNIQUE (alias, source);
