-- Retrosheet tie-out: season totals from the regular-season game logs.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- Regular-season games only (register E1: postseason and all-star games are in
-- raw.retrosheet_gamelog_post). Team walks include intentional walks: for 2019,
-- regular-season walks (15,895) plus postseason walks (261) equal the event
-- total (16,156). Both teams' figures are summed.
--
-- Cast via ::numeric, not straight ::integer, for the four counting stats
-- (not v_score/h_score): 1901-1979 formats them "N.0" rather than "N" -- the
-- same real Retrosheet CSV formatting quirk as raw.retrosheet_batting's
-- b_pa/b_k/b_w/b_hr/b_r (see tieout_season_csv_batting.sql), not fractional
-- data (every decimal value ends in exactly ".0", verified with no
-- exceptions). Found by the first full-history run (task 4.2,
-- results-history.md).
--
-- A season is entirely excluded here (not comparable via gamelog, exactly
-- like the box-score product's 1871-1961-only coverage) if even one of its
-- games has NULL home-run/strikeout/walk counts: some early seasons (1873,
-- 1875-1890s) have it for no game at all, and a handful of scattered
-- individual games in otherwise-complete seasons (1901, 1902, 1904, 1906,
-- 1914, 1937, 1954, 1979 -- 1 or 2 games each) also lack it. All six of
-- v/h_homeruns, v/h_strikeouts, v/h_walks are always NULL together, never
-- partially (verified with no exceptions). Excluding the whole season keeps
-- this an honest "missing measurement, not zero" rather than a season total
-- silently short by one game's real count (which would look like a genuine
-- disagreement with the event source). v_score/h_score are never NULL, so
-- `r`/`g` lose nothing except for these same seasons, where they remain
-- checkable via other source pairs (event vs gameinfo, etc).
WITH gl AS (
    SELECT
        *,
        bool_or(v_homeruns IS NULL) OVER (PARTITION BY _season) AS season_has_null_counts
    FROM raw.retrosheet_gamelog
    WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
)
-- A negative count is Retrosheet's "not recorded" sentinel (-1): a season's
-- total for a fact is NULL (not recorded, never compared) if any game in it has
-- a negative value for that fact, same as tieout_game_gamelog.sql.
SELECT
    _season AS season,
    CASE WHEN bool_and(v_homeruns::numeric >= 0 AND h_homeruns::numeric >= 0)
        THEN sum(v_homeruns::numeric::integer + h_homeruns::numeric::integer) END AS hr,
    CASE WHEN bool_and(v_strikeouts::numeric >= 0 AND h_strikeouts::numeric >= 0)
        THEN sum(v_strikeouts::numeric::integer + h_strikeouts::numeric::integer) END AS k,
    CASE WHEN bool_and(v_walks::numeric >= 0 AND h_walks::numeric >= 0)
        THEN sum(v_walks::numeric::integer + h_walks::numeric::integer) END AS bb,
    sum(v_score::integer + h_score::integer) AS r,
    count(*) AS g
FROM gl
WHERE NOT season_has_null_counts
GROUP BY _season
ORDER BY _season
