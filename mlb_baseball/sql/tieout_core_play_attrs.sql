-- Retrosheet tie-out (core check): attributes copied into core.play equal raw.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- Every matched (game, event) row, not a sample. The mapping mirrors
-- conform._build_plays (conform.py:1068-1079); see core-lineage.md. away_score
-- and home_score are compared too: the session handoff observed them null in
-- core for 2015-2025, and this reports that against raw rather than assuming it.
WITH expected AS (
    SELECT DISTINCT ON (ev.game_id, ev.event_id)
        ev.game_id, NULLIF(ev.event_id, '')::integer AS play_index, ev._season::integer AS season,
        ev.inn_ct, ev.bat_home_id, ev.event_cd, ev.event_tx, ev.away_score_ct, ev.home_score_ct,
        ev.bat_id, ev.pit_id
    FROM raw.retrosheet_event ev
    JOIN core.game cg ON cg.retro_game_id = ev.game_id
    WHERE ev._season::integer BETWEEN %(lo)s AND %(hi)s
    ORDER BY ev.game_id, ev.event_id, ev._scope
)
SELECT
    e.season,
    count(*) AS compared,
    count(*) FILTER (WHERE p.inning IS DISTINCT FROM NULLIF(e.inn_ct, '')::integer) AS inning,
    count(*) FILTER (WHERE p.half_inning IS DISTINCT FROM
        CASE e.bat_home_id WHEN '0' THEN 'top' WHEN '1' THEN 'bottom' END) AS half_inning,
    count(*) FILTER (WHERE p.event_code IS DISTINCT FROM e.event_cd) AS event_code,
    count(*) FILTER (WHERE p.event_desc IS DISTINCT FROM e.event_tx) AS event_desc,
    count(*) FILTER (WHERE p.away_score IS DISTINCT FROM
        NULLIF(e.away_score_ct, '')::integer) AS away_score,
    count(*) FILTER (WHERE p.home_score IS DISTINCT FROM
        NULLIF(e.home_score_ct, '')::integer) AS home_score,
    count(*) FILTER (WHERE p.batter_id IS DISTINCT FROM bat.id) AS batter,
    count(*) FILTER (WHERE p.pitcher_id IS DISTINCT FROM pit.id) AS pitcher,
    min(e.game_id || '#' || e.play_index) FILTER (WHERE
        p.inning IS DISTINCT FROM NULLIF(e.inn_ct, '')::integer
        OR p.event_code IS DISTINCT FROM e.event_cd
        OR p.batter_id IS DISTINCT FROM bat.id
        OR p.pitcher_id IS DISTINCT FROM pit.id) AS example
FROM expected e
JOIN core.game cg ON cg.retro_game_id = e.game_id
JOIN core.play p ON p.game_id = cg.id AND p.source = 'retrosheet' AND p.play_index = e.play_index
LEFT JOIN core.player bat ON bat.retro_id = e.bat_id
LEFT JOIN core.player pit ON pit.retro_id = e.pit_id
GROUP BY e.season
ORDER BY e.season
