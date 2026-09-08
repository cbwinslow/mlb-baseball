# Data dictionary

The published `mlb-research` distribution ships the **grain-complete statistic
backbone**: classical batting and pitching statistics at every grain a
sabermetric researcher expects — game, season (per stint and combined), team
season, and career — event-derived from Retrosheet.

The section below is included verbatim from the repository's canonical catalog,
[`docs/DATA_DICTIONARY.md`](https://github.com/cbwinslow/mlb-baseball/blob/main/docs/DATA_DICTIONARY.md)
(section 3). The full catalog also documents the internal `raw`, `core`, `meta`,
and `serve` layers, which are not part of the public distribution.

!!! note "Published tables only"
    The browser [Run SQL](query/index.html) page exposes eight of these as
    queryable relations. `player_season` and `team_season` are built but held
    back from public distribution on source-rights grounds.

---

--8<-- "DATA_DICTIONARY.md:backbone"
