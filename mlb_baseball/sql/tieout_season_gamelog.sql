-- Retrosheet tie-out: season totals from the regular-season game logs.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- Regular-season games only (register E1: postseason and all-star games are in
-- raw.retrosheet_gamelog_post). Team walks include intentional walks: for 2019,
-- regular-season walks (15,895) plus postseason walks (261) equal the event
-- total (16,156). Both teams' figures are summed.
SELECT
    _season AS season,
    sum(v_homeruns::integer + h_homeruns::integer) AS hr,
    sum(v_strikeouts::integer + h_strikeouts::integer) AS k,
    sum(v_walks::integer + h_walks::integer) AS bb,
    sum(v_score::integer + h_score::integer) AS r,
    count(*) AS g
FROM raw.retrosheet_gamelog
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season
ORDER BY _season
