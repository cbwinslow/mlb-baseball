INSERT INTO core.player (
    retro_id, mlbam_id, bbref_id, fangraphs_id, chadwick_uuid,
    last_name, first_name, birth_date, death_date
)
SELECT
    key_retro,
    key_mlbam,
    key_bbref,
    key_fangraphs,
    key_uuid,
    name_last,
    name_first,
    CASE WHEN birth_year IS NOT NULL AND birth_month IS NOT NULL
              AND birth_day IS NOT NULL
         THEN make_date(birth_year::integer, birth_month::integer, birth_day::integer)
    END,
    CASE WHEN death_year IS NOT NULL AND death_month IS NOT NULL
              AND death_day IS NOT NULL
         THEN make_date(death_year::integer, death_month::integer, death_day::integer)
    END
FROM raw.register_people
WHERE key_retro IS NOT NULL
