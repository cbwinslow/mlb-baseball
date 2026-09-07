## Why

The Baseball-Reference tie-out gate (`scripts/verify_baseball_reference_tie_out.py`)
has exactly two cases — Aaron Judge 2022 batting and Gerrit Cole 2023 pitching
— both at the season grain, both in the same three-year window. The v1 milestone
criterion is "backbone relations 1–6 tied out to Baseball-Reference within a
documented tolerance". Two modern season lines do not exercise the game-grain
builder, the team-season roll-up, the career roll-up, or any era before 2022.
This change expands the gate to every backbone grain across the modern +
mid-century range, so a builder bug at any grain or any decade-specific
edge (roster rules, IP conventions, sacrifice-fly history) is caught.

## What Changes

- **`scripts/verify_baseball_reference_tie_out.py` generalised to every grain.**
  `TieOutCase.table` extends to `batting_game` / `pitching_game` /
  `batting_team` / `pitching_team` / `batting_career` / `pitching_career`
  alongside the two season tables. The season-only `_fetch_combined_row` becomes
  a per-grain fetch keyed by the case's grain: `(game_id, player_id)` for a
  game, `(team_id, season)` for a team-season, `(player_id)` for a career,
  `(player_id, season, is_combined)` for a season.
- **New cases added** (all values hand-read from a cited Baseball-Reference
  page/box, no live fetch at runtime — same convention as the existing two):
  - **Game grain:** one real batting box line and one real pitching box line
    from a documented modern game, checked against that game's
    Baseball-Reference box score.
  - **Season grain:** the existing two plus mid-century and modern cases and at
    least one traded-in-season player (verifies the `is_combined` roll-up), each
    checked against the player's Baseball-Reference standard-batting /
    standard-pitching row.
  - **Team-season grain:** one batting and one pitching team-season, checked
    against the team's Baseball-Reference team-batting / team-pitching totals.
  - **Career grain:** one batting and one pitching career total for a retired
    player, checked against the Baseball-Reference career line.
- **Era scope:** ~1950 to present only — the range where Retrosheet event data
  is contemporaneous and complete. Every case is expected to match exactly
  (counting stats) / to Baseball-Reference's display precision (rate stats).
  Pre-1950 / deducted-era cases are explicitly out of scope (a mismatch there
  would be data coverage, not a builder bug) and noted as later follow-up.
- **`docs/` note:** the milestone / release checklist records that this script
  is the relation-1–6 tie-out gate and how to run it (`DATABASE_URL=… uv run
  python scripts/verify_baseball_reference_tie_out.py` against a
  fully-built database).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `statistic-backbone`: the "Each relation is deterministic and validated
  against a published figure" requirement changes from "an integration tie-out
  test that builds **one real player-season**" to a tie-out gate covering
  **every grain** (game, season, team, career) across the modern + mid-century
  range, with pre-1950 explicitly excluded and documented.

## Impact

- `scripts/verify_baseball_reference_tie_out.py` — generalised, ~8–10 new
  `TieOutCase`s.
- `openspec/specs/statistic-backbone/spec.md` — via the delta above.
- A milestone/release-checklist doc note (exact file confirmed during apply).
- No production code, no SQL, no migrations, no dependencies. The script stays a
  manual gate run against a fully-built database — CI has no real Retrosheet
  events, so it is not a CI check (unchanged).
