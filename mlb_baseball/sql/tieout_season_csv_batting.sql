-- Retrosheet tie-out: season totals from Retrosheet's CSV per-player batting.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- Only stattype 'value' rows. The table also holds 'official' (36,118 rows),
-- 'lower' and 'upper' variants of the same player-games; summing them would
-- double count. b_w already includes intentional walks (b_iw is the subset):
-- for 2019 b_w = 16,156 = event codes 14 (15,380) + 15 (776).
SELECT
    _season AS season,
    sum(b_pa::integer) AS pa,
    sum(b_k::integer) AS k,
    sum(b_w::integer) AS bb,
    sum(b_hr::integer) AS hr,
    sum(b_r::integer) AS r,
    count(DISTINCT gid) AS g
FROM raw.retrosheet_batting
WHERE stattype = 'value'
    AND _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season
ORDER BY _season
