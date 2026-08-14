-- Reconcile starter outs reconstruction against Baseball-Reference IP
WITH mine AS (
    SELECT p.mlbam_id, re._season, sum(re.event_outs_ct::numeric) AS outs
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi
        ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    JOIN core.player p ON p.retro_id = re.resp_pit_id
    WHERE p.mlbam_id IS NOT NULL
    GROUP BY p.mlbam_id, re._season
)
-- bp.ip is baseball notation ("217.2" = 217 innings + 2 outs,
-- NOT decimal 217.2) -- split_part on '.' and treat the
-- fractional part as a literal out count, not a fraction.
SELECT m.mlbam_id || '-' || m._season, m.outs,
    split_part(bp.ip, '.', 1)::numeric * 3
        + COALESCE(NULLIF(split_part(bp.ip, '.', 2), ''), '0')::numeric
FROM mine m
JOIN raw.bref_pitching bp ON bp.mlbid = m.mlbam_id AND bp._season = m._season
WHERE bp.ip ~ '^[0-9]+\\.?[0-9]*$';
