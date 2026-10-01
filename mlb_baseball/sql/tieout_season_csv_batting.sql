-- Retrosheet tie-out: season totals from Retrosheet's CSV per-player batting.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- Only stattype 'value' rows. The table also holds 'official' (36,118 rows),
-- 'lower' and 'upper' variants of the same player-games; summing them would
-- double count. b_w already includes intentional walks (b_iw is the subset):
-- for 2019 b_w = 16,156 = event codes 14 (15,380) + 15 (776).
--
-- Cast via ::numeric, not straight ::integer: 1898-1981 (every row, not a few)
-- formats these five columns as "N.0" rather than "N" -- a real Retrosheet CSV
-- formatting quirk in this era, not fractional data (every decimal value ends
-- in exactly ".0", verified with no exceptions; 1982 onward is plain integers).
-- Found by the first full-history run (task 4.2, results-history.md): a bare
-- ::integer cast crashes the query outright as soon as the season range
-- reaches 1981.
-- A total is NULL unless every row in the group has a value: the CSV leaves
-- these columns blank for early seasons (b_k blank for most of 1898-1915).
-- Blank is "not recorded", never zero, and a partial sum would under-count.
SELECT
    _season AS season,
    CASE WHEN count(*) = count(b_pa) THEN sum(b_pa::numeric::integer) END AS pa,
    CASE WHEN count(*) = count(b_k) THEN sum(b_k::numeric::integer) END AS k,
    CASE WHEN count(*) = count(b_w) THEN sum(b_w::numeric::integer) END AS bb,
    CASE WHEN count(*) = count(b_hr) THEN sum(b_hr::numeric::integer) END AS hr,
    CASE WHEN count(*) = count(b_r) THEN sum(b_r::numeric::integer) END AS r,
    count(DISTINCT gid) AS g
FROM raw.retrosheet_batting
WHERE stattype = 'value'
    AND _season BETWEEN %(lo)s::text AND %(hi)s::text
GROUP BY _season
ORDER BY _season
