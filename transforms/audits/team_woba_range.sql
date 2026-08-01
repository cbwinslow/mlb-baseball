-- Ported bound from mlb_baseball/model/offense.py::health_check (ADR-036):
-- home_woba holds a per-game ENTERING value, which for an early-season game
-- can reflect just 1-3 real games (legitimate small-sample noise), not a
-- full-season average -- confirmed directly in production that the real
-- range across all of MLB history is 0.0606-0.5870. 0.05-0.65 is that same
-- bound, calibrated against real values, not guessed.
AUDIT (
  name team_woba_plausible_range
);

SELECT *
FROM @this_model
WHERE woba IS NOT NULL AND (woba < 0.05 OR woba > 0.65)
