INSERT INTO core.team (retro_team_id, league, city, nickname, first_year, last_year)
SELECT
    team_id,
    league,
    city,
    nickname,
    first_year::integer,
    -- Retrosheet uses its shared latest last_year for all active teams. Keep
    -- that documented sentinel open-ended so future seasons still resolve.
    CASE
        WHEN last_year::integer = max(last_year::integer) OVER () THEN 9999
        ELSE last_year::integer
    END
FROM raw.retrosheet_team
