# Readiness run — 2026-09-27 (task 4.2)

Target: production `mlb` (read-only for the tie-out; the feature store was
built into a scratch DuckDB file, not `~/.mlb/mlb.duckdb`). Feature set
`game-win:v1`.

## Steps

1. First run on the existing `~/.mlb/mlb.duckdb` (built 2026-09-23) failed with
   `Referenced column "home_pa_30d" not found`: the file predates the current
   `feat.game` schema.
2. Fresh `mlb build --only-features` built `feat.player_form: 0 rows` and
   `feat.pitcher_form: 0 rows`. Cause: production `gold.batting_game`,
   `gold.pitching_game` and the season, team and career roll-ups were empty
   (see `openspec/changes/pipeline-freshness/`). Result: **not ready**, and the
   Baseball-Reference tie-out failed for the same reason.
3. Owner ran `mlb migrate` (applied `0107_team_franchise.sql`) and `mlb report`.
   `mlb doctor --populated`: 9/9 backbone relations populated
   (`gold.batting_game` 4,351,484 rows; `gold.pitching_game` 1,186,599).
4. Fresh `mlb build --only-features`: `feat.player_form` 4,351,449 rows,
   `feat.pitcher_form` 1,186,597, `feat.game` 220,191.
5. `mlb readiness --feature-set game-win --feature-version v1`.

## Result: not ready — one bounded blocker

Passing: feature admission, declared columns, coverage, grain, clocks, both
leakage checks, every null-iff-empty integrity check, and the
Baseball-Reference backbone tie-out.

Failing: `feature_null_policy` — 30,000 unexplained in-window nulls (8 team-rate
fields x 3,750 games).

## What the blocker is

All 3,750 are games with no batting lines in the backbone, so `feat.game` has
no team-form row and the rate is honestly NULL with a NULL (not zero)
denominator. The gate counts a NULL denominator as unexplained.

- 1914–1933: a few games per season; 1935–1949: 824–3,136 field-rows per
  season (production check: 23,474 regular games in 1935–1949, 19,767 with
  batting lines); 1954 and 1979: one game each (`SLN195407182`,
  `CHA197907122`).
- 1950–2025 apart from those two games, and every season from 1980 on: zero
  unexplained nulls.
- Declared coverage is 1910–2025.

## Consequence

- Task 4.3 stays open: the report is not ready, so `game-win-v1` is not frozen
  yet. The follow-up change must choose between narrowing the declared
  coverage era or teaching the gate to recognise "no box-score lines for this
  game" as an explained missing value. That is a decision about the gate's
  rule, so it is not made here.
- `play-engine` fits on 2015 and later, and 2015–2025 has no unexplained
  nulls, so this blocker does not touch the engine's inputs.
