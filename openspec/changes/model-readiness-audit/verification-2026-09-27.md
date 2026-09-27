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
game with no play-by-play has no `gold` row. Across the whole declared window
(regular games, 1910–2025) exactly **3,750** games have no `gold.batting_game`
row. That equals the readiness count (30,000 field-rows / 8 fields), and every
one is accounted for:

| Class (audit query below) | Games | Seasons | Play-by-play |
| --- | --- | --- | --- |
| Full box score, no play-by-play (`box` = y) | 1,586 | 1920–1949 | none |
| Partial player stats only (no box score) | 1,886 | 1929–1949 | none |
| No batting lines in any raw table | 266 | 1935–1949 | none |
| Forfeits (`forfeit` set in `raw.retrosheet_gameinfo`) | 12 | 1914–1979 | none |

By period: 41 games in 1910–1934, 3,707 in 1935–1949, 2 in 1950–2025 (the
1954 and 1979 forfeits, `SLN195407182` and `CHA197907122`, both 9–0).

- The full-box-score group holds about 21 batting lines per game in the CSV;
  1,307 of the 1935–1949 ones are also in `raw.retrosheet_box_batting`. The
  partial group holds about 8 lines per game.
- Of the 3,707 games in 1935–1949, 3,706 involve only clubs with no AL/NL
  league in `core.team` — Negro League clubs (Memphis, Homestead, Chicago
  American Giants, Philadelphia Stars, Baltimore Elite Giants, Kansas City,
  Birmingham and others), in the same `game_type = 'regular'` pool. The 1935–1949
  span holds 23,474 regular games; 19,767 have gold rows (`pbp` values `y`
  16,688 and `d` 3,079).
- Every season from 1950 on, apart from the two forfeits, has zero unexplained
  nulls.

So the raw data has no error. Two different things are going on: about 1,586
games have real box scores that our backbone does not use (a coverage gap in
our build, fixable), and about 2,160 games have no usable full lines (honest
missing values).

### Audit query (read-only, repeatable)

```sql
-- Backbone gap audit: regular games, 1910-2025, with no gold.batting_game row,
-- classified by what Retrosheet has for them. Read-only.
CREATE TEMP TABLE gap AS
SELECT g.retro_game_id AS rid, g.season
FROM core.game g
WHERE g.game_type = 'regular' AND g.season BETWEEN 1910 AND 2025
  AND g.retro_game_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM gold.batting_game b WHERE b.game_id = g.id);

-- Retrosheet's combined batting CSV, one row per game: box = "do we have a box score",
-- lines = number of player lines it holds for the game.
CREATE TEMP TABLE csvg AS
SELECT gid, max(box) AS box, count(*) AS lines
FROM raw.retrosheet_batting
WHERE substring(gid, 4, 4)::int BETWEEN 1910 AND 2025
GROUP BY gid;

CREATE TEMP TABLE ev AS
SELECT DISTINCT game_id FROM raw.retrosheet_event
WHERE substring(game_id, 4, 4)::int BETWEEN 1910 AND 2025;

CREATE TEMP TABLE forf AS
SELECT gid FROM raw.retrosheet_gameinfo WHERE forfeit IS NOT NULL AND forfeit <> '';

SELECT
  CASE
    WHEN f.gid IS NOT NULL                   THEN '4 forfeit'
    WHEN c.box IN ('y', 'Y')                 THEN '1 full box score, no play-by-play'
    WHEN c.gid IS NOT NULL                   THEN '2 partial player stats only'
    ELSE                                          '3 no batting lines in any raw table'
  END AS class,
  count(*) AS games,
  min(m.season) AS first_season,
  max(m.season) AS last_season,
  count(*) FILTER (WHERE e.game_id IS NOT NULL) AS has_play_by_play
FROM gap m
LEFT JOIN csvg c ON c.gid = m.rid
LEFT JOIN ev e ON e.game_id = m.rid
LEFT JOIN forf f ON f.gid = m.rid
GROUP BY 1 ORDER BY 1;

SELECT 'games missing, total' AS k, count(*) FROM gap
UNION ALL SELECT 'missing in 1910-1934', count(*) FROM gap WHERE season < 1935
UNION ALL SELECT 'missing in 1935-1949', count(*) FROM gap WHERE season BETWEEN 1935 AND 1949
UNION ALL SELECT 'missing in 1950-2025', count(*) FROM gap WHERE season >= 1950;
```

## Consequence

- Task 4.3 stays open: the report is not ready, so `game-win-v1` is not frozen
  yet. The follow-up change must choose between narrowing the declared
  coverage era, teaching the gate to recognise "no full box score for this
  game" as an explained missing value, or (separately) building backbone lines
  from Retrosheet box scores for the 1,586 box-only games. Those are decisions
  about the gate and the backbone, so they are not made here.
- Negro League games sit in the `regular` pool and `core.team.league` is blank
  for those clubs. Whether the game-win model should include them is a scoping
  question for its owner; it does not affect the 2015+ plate-appearance engine.
- `play-engine` fits on 2015 and later, and 2015–2025 has no unexplained
  nulls, so this blocker does not touch the engine's inputs.
