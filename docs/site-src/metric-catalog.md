# Metric catalog

Every publicly-visible statistic this project implements, generated from `meta.metric` (`mlb catalog docs`) -- see `openspec/changes/metric-catalog/` for how this catalog is built and maintained. An internal (non-public) entry never appears here.

## fangraphs_guts

FanGraphs' "Guts!" per-season linear-weight constants used to compute wOBA and FIP correctly for a given season's actual run environment, rather than a single fixed weight set applied to every year.

- **Status:** published
- **Citation:** FanGraphs, Guts! constants (https://www.fangraphs.com/guts.aspx)
- **Data source:** raw.fangraphs_guts
- **Grain:** season
- **Layer:** gold
- **Source:** [https://github.com/cbwinslow/mlb-baseball/blob/13adfaf840d8659bde70efccdd1c92d541e66d2e/mlb_baseball/sql/gold_fangraphs_guts.sql](https://github.com/cbwinslow/mlb-baseball/blob/13adfaf840d8659bde70efccdd1c92d541e66d2e/mlb_baseball/sql/gold_fangraphs_guts.sql)
- **Notes:** Verbatim numeric conform of FanGraphs' own published constants -- no re-derivation. Not yet independently tie-out tested against a second source, hence "published" rather than "validated" (ADR-290). This is a cross-check/reference relation: a publishable wOBA/FIP for this project's own data is computed from core.play, not from here (see gold.fangraphs_guts' table comment).
