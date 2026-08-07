UPDATE core.venue v
SET mlb_venue_id = mv.venue_id::integer,
    latitude = NULLIF(mv.latitude, '')::numeric,
    longitude = NULLIF(mv.longitude, '')::numeric,
    capacity = NULLIF(mv.capacity, '')::numeric::integer,
    turf_type = mv.turf_type,
    roof_type = mv.roof_type,
    left_line = NULLIF(mv.left_line, '')::numeric::integer,
    center = NULLIF(mv.center, '')::numeric::integer,
    right_line = NULLIF(mv.right_line, '')::numeric::integer
FROM (
    SELECT DISTINCT ON (lower(trim(name)))
        name, venue_id, latitude, longitude, capacity, turf_type,
        roof_type, left_line, center, right_line
    FROM raw.mlb_venue
    ORDER BY lower(trim(name)), venue_id::integer
) mv
WHERE lower(trim(v.name)) = lower(trim(mv.name))
