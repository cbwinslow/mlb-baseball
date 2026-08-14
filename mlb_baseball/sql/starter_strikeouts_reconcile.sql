-- Reconcile starter strikeout reconstruction against Baseball-Reference
WITH mine AS (
    SELECT p.mlbam_id, re._season,
        count(*) FILTER (WHERE re.bat_event_fl = 'T' AND re.event_cd = '3') AS k
    FROM raw.retrosheet_event re
    JOIN raw.retrosheet_gameinfo gi
        ON gi.gid = re.game_id AND lower(gi.gametype) = 'regular'
    JOIN core.player p ON p.retro_id = re.resp_pit_id
    WHERE p.mlbam_id IS NOT NULL
    GROUP BY p.mlbam_id, re._season
)
SELECT m.mlbam_id || '-' || m._season, m.k, bp.so::integer
FROM mine m
JOIN raw.bref_pitching bp ON bp.mlbid = m.mlbam_id AND bp._season = m._season
WHERE bp.so ~ '^[0-9]+$';
