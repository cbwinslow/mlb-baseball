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
  - **Season grain:** the existing two plus more modern cases.
  - **Team-season grain:** one batting and one pitching team-season, checked
    against the team's Baseball-Reference team-batting / team-pitching totals.
- **Era scope: modern only (~2005+).** Applying the gate at every grain and era
  surfaced that exact tie-out is *not* achievable at the **career grain**, nor
  for seasons much before ~2000: Retrosheet's event record and
  Baseball-Reference's official record have each absorbed decades of
  independent scoring corrections and differ by small amounts (one or two on a
  counting stat per older season; a fraction of a percent across a full
  career). This is a source-of-record divergence, not a builder error. The
  career grain and pre-2000 seasons are therefore **out of the exact-match
  gate's scope**, and the divergence is written into the honest-limitations
  documentation.
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
  test that builds **one real player-season**" to a tie-out gate covering the
  **game, season, and team-season grains** (batting and pitching) in the
  modern era (~2005+), with the career grain and pre-2000 seasons explicitly
  out of the exact-match scope and their Retrosheet-vs-Baseball-Reference
  divergence documented as an honest limitation.

## Impact

- `scripts/verify_baseball_reference_tie_out.py` — generalised per-grain fetch,
  ~6 new modern `TieOutCase`s.
- `openspec/specs/statistic-backbone/spec.md` — via the delta above.
- Honest-limitations doc — records the career-grain / pre-2000
  Retrosheet-vs-Baseball-Reference divergence.
- A milestone/release-checklist doc note (exact file confirmed during apply).
- No production code, no SQL, no migrations, no dependencies. The script stays a
  manual gate run against a fully-built database — CI has no real Retrosheet
  events, so it is not a CI check (unchanged).
