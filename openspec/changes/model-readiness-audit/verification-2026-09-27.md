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

## What the blocker is (re-checked against raw tables and Retrosheet's docs)

The first write-up said "games with no batting lines". That was too coarse.
Checked against `raw.retrosheet_batting` (Retrosheet's own combined CSV),
`raw.retrosheet_box_batting`, `raw.retrosheet_event` and Retrosheet's column
definitions (`csvcontents.html`: `box` = "do we have a box score; blank
indicates no"; `pbp` blank = no play-by-play, `d` = deduced, `y` = account from
newspaper or scorecard):

`gold.batting_game` is built from play-by-play (`raw.retrosheet_event`), so a
game with no play-by-play has no `gold` row. Of the 3,707 regular games from
1935–1949 that are missing from it:

| Group | Games | What Retrosheet has |
| --- | --- | --- |
| Full box score, no play-by-play (`box` = y) | 1,547 | about 21 batting lines per game in the CSV; 1,307 also in `raw.retrosheet_box_batting` |
| No box score, partial player stats only | 1,889 | about 8 lines per game (Retrosheet's own bounds and official lines) |
| Nothing at all | 271 | no batting lines in any raw table |

- None of the 3,707 has play-by-play in `raw.retrosheet_event`.
- 3,706 of them involve only teams with no AL/NL league in `core.team`; the
  home teams are Negro League clubs (Memphis, Homestead, Chicago American
  Giants, Philadelphia Stars, Baltimore Elite Giants, Kansas City, Birmingham
  and others). They sit in the same `game_type = 'regular'` pool as the rest.
- The 1935–1949 span holds 23,474 regular games; 19,767 have gold rows (the
  `pbp` values there are `y` 16,688 and `d` 3,079).
- 1954 (`SLN195407182`) and 1979 (`CHA197907122`): both are 9–0 forfeits
  (`forfeit` = Y in `raw.retrosheet_gameinfo`) with no batting lines anywhere.
  Their blank values are correct.
- Every season from 1980 on, and every season from 1950 on apart from those two
  forfeits, has zero unexplained nulls.

So the raw data has no error. Two different things are going on: 1,547 games
have real box scores that our backbone does not use (a coverage gap in our
build, fixable), and about 2,160 games have no usable full lines (honest
missing values).

## Consequence

- Task 4.3 stays open: the report is not ready, so `game-win-v1` is not frozen
  yet. The follow-up change must choose between narrowing the declared
  coverage era, teaching the gate to recognise "no full box score for this
  game" as an explained missing value, or (separately) building backbone lines
  from Retrosheet box scores for the 1,547 box-only games. Those are decisions
  about the gate and the backbone, so they are not made here.
- Negro League games sit in the `regular` pool and `core.team.league` is blank
  for those clubs. Whether the game-win model should include them is a scoping
  question for its owner; it does not affect the 2015+ plate-appearance engine.
- `play-engine` fits on 2015 and later, and 2015–2025 has no unexplained
  nulls, so this blocker does not touch the engine's inputs.
