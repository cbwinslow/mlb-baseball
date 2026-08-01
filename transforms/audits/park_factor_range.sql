-- Ported bound from mlb_baseball/model/park.py::health_check (ADR-035):
-- real MLB park factors have never been observed outside roughly 80-130
-- (Coors Field, the most extreme modern hitter's park, sits around
-- 110-135), so 50-200 is a generous plausible-range bound that would still
-- catch a real bug (e.g. an inverted home/road ratio, which would produce
-- values near 0 or in the thousands) without false-positiving on a
-- legitimately extreme park.
AUDIT (
  name park_factor_plausible_range
);

SELECT *
FROM @this_model
WHERE park_factor IS NOT NULL AND (park_factor < 50 OR park_factor > 200)
