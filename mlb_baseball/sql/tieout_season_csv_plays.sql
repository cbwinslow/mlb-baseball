-- Retrosheet tie-out: season totals from Retrosheet's own CSV play-by-play.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- The CSV product's per-play flags: pa, k, hr, and walk (which is 1 for both
-- plain and intentional walks, checked on 60 games of 2019; iw marks the
-- intentional subset, as in CSV batting). runs is runs scored on the play.
-- raw.retrosheet_plays is large (about 20 GB); the tie-out script sets a long
-- statement timeout. _season is text with a plain btree index.
SELECT
    _season AS season,
    sum(pa::integer) AS pa,
    sum(k::integer) AS k,
    sum(walk::integer) AS bb,
    sum(hr::integer) AS hr,
    sum(runs::integer) AS r,
    count(DISTINCT gid) AS g
FROM raw.retrosheet_plays
WHERE _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season
ORDER BY _season
