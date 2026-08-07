INSERT INTO core.venue
    (retro_park_id, name, city, state, league, first_year, last_year)
SELECT
    parkid, name, city, state, league,
    CASE WHEN start ~ '^\d{2}/\d{2}/\d{4}$'
         THEN extract(year FROM to_date(start, 'MM/DD/YYYY'))::integer END,
    CASE WHEN "end" ~ '^\d{2}/\d{2}/\d{4}$'
         THEN extract(year FROM to_date("end", 'MM/DD/YYYY'))::integer END
FROM raw.retrosheet_park
