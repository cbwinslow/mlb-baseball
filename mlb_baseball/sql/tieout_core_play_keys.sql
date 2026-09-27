-- Retrosheet tie-out (core check): every event key against core.play, both ways.
-- Read-only. Owner: mlb_baseball/tieout_run.py (openspec change raw-source-tieout).
--
-- expected: each de-duplicated (game_id, event_id) of an event game that exists
--           in core.game (conform's inner join, conform.py:1094), batter and
--           baserunning events alike.
-- actual:   core.play Retrosheet rows keyed by the same (game id, play index).
-- A plate-appearance count cannot see a dropped baserunning play; this can.
WITH expected AS (
    SELECT DISTINCT ON (ev.game_id, ev.event_id)
        ev.game_id, NULLIF(ev.event_id, '')::integer AS play_index, ev._season::integer AS season
    FROM raw.retrosheet_event ev
    JOIN core.game cg ON cg.retro_game_id = ev.game_id
    WHERE ev._season::integer BETWEEN %(lo)s AND %(hi)s
    ORDER BY ev.game_id, ev.event_id, ev._scope
),
actual AS (
    SELECT cg.retro_game_id AS game_id, p.play_index, p.season
    FROM core.play p
    JOIN core.game cg ON cg.id = p.game_id
    WHERE p.source = 'retrosheet'
        AND p.season BETWEEN %(lo)s AND %(hi)s
),
duplicated AS (
    SELECT season, count(*) AS n
    FROM (
        SELECT season, game_id, play_index
        FROM actual
        GROUP BY season, game_id, play_index
        HAVING count(*) > 1
    ) d
    GROUP BY season
)
SELECT
    coalesce(e.season, a.season) AS season,
    count(*) AS keys,
    count(*) FILTER (WHERE a.game_id IS NULL) AS missing_in_core,
    count(*) FILTER (WHERE e.game_id IS NULL) AS extra_in_core,
    coalesce(max(d.n), 0) AS duplicated_keys,
    min(e.game_id || '#' || e.play_index) FILTER (WHERE a.game_id IS NULL) AS example_missing,
    min(a.game_id || '#' || a.play_index) FILTER (WHERE e.game_id IS NULL) AS example_extra
FROM expected e
FULL JOIN actual a ON a.game_id = e.game_id AND a.play_index = e.play_index
LEFT JOIN duplicated d ON d.season = coalesce(e.season, a.season)
GROUP BY coalesce(e.season, a.season)
ORDER BY coalesce(e.season, a.season)
