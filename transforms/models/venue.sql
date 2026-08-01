MODEL (
  name core.venue,
  kind FULL,
  grain retro_park_id,
  description '
    Port of mlb_baseball/conform.py::_build_venues (ADR-030) -- one row per
    historical MLB ballpark, keyed on Retrosheet''s own parkid (the exact
    join key already stored in raw.retrosheet_gameinfo.site/core.game.site,
    same as the hand-written Python version), enriched from MLB''s richer
    venue catalog by exact case-insensitive name match, left NULL where
    nothing matches -- same "leave it NULL, don''t guess" precedent as the
    original.

    SQLMesh spike note: conform.py does this as two imperative steps (an
    INSERT, then a best-effort UPDATE...FROM for the enrichment columns,
    each independently optional depending on whether raw.retrosheet_park/
    raw.mlb_venue exist yet). A single declarative LEFT JOIN expresses the
    same "enrichment is optional, base row always lands" intent in one
    query -- SQLMesh (like Postgres generally) has no problem with a LEFT
    JOIN against a table that happens to be empty. What it CANNOT express
    for free is conform.py''s "raw table does not exist yet at all" case
    (a fresh clone that has not bootstrapped mlb_api yet) -- that still
    needs the table to exist, even empty, for this query to plan at all.

    Tie-break, made explicit here where the Python original left it
    implicit: raw.mlb_venue has real duplicate names (e.g. 15 different
    "Municipal Stadium" rows across MLB history -- confirmed directly).
    conform.py''s UPDATE...FROM matches non-deterministically among
    duplicates; this version deterministically keeps the lowest venue_id
    per name via DISTINCT ON. Not observed to change any real row this
    spike checked (Coors Field/Fenway Park are both unique in raw.mlb_venue),
    but it is a real, documented behavior difference worth calling out in
    the migration evaluation -- declarative SQL forces an explicit
    tie-break where an imperative UPDATE silently picked one.
  ',
  audits (
    unique_values(columns := (retro_park_id)),
    not_null(columns := (retro_park_id, name))
  )
);

WITH mlb_venue_dedup AS (
  SELECT DISTINCT ON (lower(trim(name)))
    name, venue_id, latitude, longitude, capacity, turf_type, roof_type,
    left_line, center, right_line
  FROM raw.mlb_venue
  ORDER BY lower(trim(name)), venue_id::int
)
SELECT
    p.parkid AS retro_park_id,
    p.name,
    p.city,
    p.state,
    p.league,
    CASE WHEN p.start ~ '^\d{2}/\d{2}/\d{4}$'
         THEN extract(year FROM to_date(p.start, 'MM/DD/YYYY'))::int END AS first_year,
    CASE WHEN p."end" ~ '^\d{2}/\d{2}/\d{4}$'
         THEN extract(year FROM to_date(p."end", 'MM/DD/YYYY'))::int END AS last_year,
    mv.venue_id::int AS mlb_venue_id,
    NULLIF(mv.latitude, '')::numeric AS latitude,
    NULLIF(mv.longitude, '')::numeric AS longitude,
    NULLIF(mv.capacity, '')::numeric::int AS capacity,
    mv.turf_type,
    mv.roof_type,
    NULLIF(mv.left_line, '')::numeric::int AS left_line,
    NULLIF(mv.center, '')::numeric::int AS center,
    NULLIF(mv.right_line, '')::numeric::int AS right_line
FROM raw.retrosheet_park p
LEFT JOIN mlb_venue_dedup mv ON lower(trim(p.name)) = lower(trim(mv.name))
