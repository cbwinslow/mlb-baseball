# Pass marks and explained-differences register

Task 1.3 of `raw-source-tieout`. **This file is committed before the gate is run
against the full history.** Once the first full run has happened, a mark in
section 1 does not change and a section 2 entry is only added with evidence in a
new commit; loosening a rule to make a run pass is not allowed (the run records
this file's commit id, task 4.1).

Facts marked *(checked 2026-09-27)* were read from production `mlb` (read-only)
while writing this file. Everything else is taken from the cited code or from the
session handoff and is confirmed again by the gate's first run.

## 1. Pass marks

**The tolerance for every comparison is zero.** Two sources describing the same
game are the same fact, so a compared count either matches exactly or the
difference must be covered by a register entry in section 2. There are no
percentages and no "close enough".

| Comparison | Levels run (every season in range, none skipped) | Pass mark |
| --- | --- | --- |
| Event files vs CSV play-by-play (`retrosheet_event` vs `retrosheet_plays`) | season, game, player-game | plate appearances, strikeouts, walks, home runs, runs equal exactly |
| Event files vs CSV batting (`retrosheet_batting`) | season, game, player-game | same facts equal exactly |
| Event files vs game logs (`retrosheet_gamelog`, `retrosheet_gamelog_post`) | season, game | home runs, strikeouts, walks, runs, game count equal exactly, after applying E1 |
| Game logs vs CSV game info (`retrosheet_gameinfo`) | season, game | score, game count equal exactly |
| Box scores vs the above (`retrosheet_box_*`) | season, game, player-game | equal exactly, only for seasons box scores cover (section 3) |
| `core.game` vs `raw.retrosheet_gameinfo` | season | game count equal; no duplicated `retro_game_id`; sampled attributes equal (dates, teams, scores) |
| `core.play` (Retrosheet rows) vs `raw.retrosheet_event` after E2 | season, game | every (`game_id`, `event_id`) event whose game is in `core.game` has exactly one `core.play` row, and no `core.play` row lacks an event; plate-appearance count equal; sampled attributes equal (inning, half, event code, batter, pitcher) |
| Event games missing from `core.game` | season | not a pass/fail on `conform`; the count is **reported** per season so a change in it is visible (audit G7) |
| Event batter and pitcher ids vs rosters and all-players | season | every id resolves, or is listed with season and count |
| Production columns vs pinned source contract | per table | no missing or unexpected column, except era-dependent columns listed in section 2 |

Two further rules that are part of the pass mark, not exceptions to it:

- **A season total that matches is not enough.** Game and player-game levels run for
  every compared season; two opposite errors inside one season total must still be
  reported (design D2).
- **A register entry that no longer matches its rule fails.** If an entry predicts a
  difference in a season and the difference is absent or a different size, the gate
  fails until the entry is corrected or removed (design D3).

## 2. Explained-differences register (initial)

Each entry: id, sources, fact, seasons, cause, evidence, and a **rule** the gate
can check.

### E1. Regular-season game logs exclude postseason and all-star games

- **Sources:** event files (`retrosheet_event`, all groups) and CSV batting vs
  `retrosheet_gamelog` (regular season).
- **Fact:** home runs, strikeouts, walks, runs, games; every season with a
  postseason or all-star game.
- **Cause:** `retrosheet_gamelog` holds regular-season games only. Postseason and
  all-star games are in `retrosheet_gamelog_post` (`connectors/retrosheet_gamelog.py`,
  `POST_TABLE`), and the event tables contain those games too.
- **Evidence:** the session handoff (2026-09-27) recorded that event and CSV
  batting agree exactly on plate appearances, strikeouts and home runs for every
  season 2015–2025, and that game-log home runs are lower by exactly the
  `retrosheet_gamelog_post` home runs (differences of 94, 97, 159 and 116 were
  checked; the seasons for those four were not recorded, so the gate's first run
  re-derives them for every season).
- **Rule:** per season and per fact,
  `event total − regular-season game-log total = game-log-post total`,
  and per game, a game present in events and absent from the regular-season game
  log must be present in `retrosheet_gamelog_post`. Direction matters: the event
  total is the larger number.
- **Limit of the evidence:** it covers home runs only. The rule is checked for every
  listed fact on every run, so it excuses a strikeout, walk, run or game-count
  difference only where it reproduces that difference exactly; anything else is
  unexplained and fails.

### E2. Negro League games published twice; events are compared after de-duplication

- **Sources:** `retrosheet_event` (and `retrosheet_game`).
- **Fact:** every event and game count.
- **Cause:** 1,872 Negro League games are published in both the general
  play-by-play archive and the dedicated Negro League archive, so the same
  (`game_id`, `event_id`) exists under two `_scope` values with identical content
  (`conform.py:1081-1093` records this and de-duplicates the same way).
- **Evidence (checked 2026-09-27):** in `raw.retrosheet_game`, 1,877 games are in
  group `negro_league` and 1,872 of them are also in group `pbp`.
- **Rule:** the gate counts events and games as distinct (`game_id`, `event_id`) /
  `game_id`, exactly as `core.play` does. It also reports the number of duplicate
  keys per season and fails if a duplicated key has differing content.

### E3. Era-dependent columns in CSV `plays`

- **Sources:** `retrosheet_plays` column contract.
- **Fact:** column set, not a count.
- **Cause:** early seasons have fewer columns in Retrosheet's own CSV
  (1899 has 161 columns where 1898 and 2024 have 177: no ball/strike count,
  left-on-base id, pinch-runner base state, reached-on-error, or scores at play).
  See `connectors/retrosheet.py` module docstring, audit G9.
- **Rule:** the column contract for `retrosheet_plays` is a set of columns present in
  every season plus a set that may be absent for seasons before a stated year; the
  exact year is measured by the gate's first run and recorded here in a new commit
  before it is relied on. Missing before that year is accepted; missing after it is
  a failure.

## 3. Coverage boundaries (reported as "not comparable", never as a pass)

A source that does not cover a season cannot agree or disagree for it. These are
listed so a gap is stated, not hidden. *(checked 2026-09-27 from production)*

| Source | First season | Last season | Note |
| --- | --- | --- | --- |
| `retrosheet_box_game` (box scores) | 1871 | 1961 | 60 distinct seasons; cannot check modern seasons |
| `retrosheet_gamelog` | 1871 | 2025 | 155 seasons |
| `retrosheet_gamelog_post` | 1903 | 2025 | 122 seasons |
| `retrosheet_gameinfo` (CSV product) | 1898 | 2025 | 128 seasons |
| `retrosheet_batting` (CSV product) | 1898 | 2025 | 128 seasons |
| `retrosheet_game` / `retrosheet_event` | 1910 (gate) | 2025 | rows exist back to 1900, but the gate treats 1910 as the real start: every row before 1910 is `_group` `postseason` or `negro_league` (never `pbp`, zero exceptions -- checked by the first full-history run, task 4.2), so a pre-1910 season only ever holds a handful of World Series/Negro-League games, not the comprehensive regular season the CSV/game-log products have back to 1898. `tieout_season_event.sql`/`tieout_game_event.sql`/`tieout_player_event.sql` exclude seasons before 1910 for this reason. By group: `pbp` 1910–2025, `postseason` 1900–2025, `allstar` 1933–2025, `negro_league` 1903–1961 |
| `retrosheet_plays` (CSV product) | not measured | not measured | 1898 onward per the connector docstring; the table is too slow to scan in the read-only tool, so the gate measures it |

A season that only one source covers is reported "not comparable". 2026 is not
published by Retrosheet at all and is outside this gate.

## 4. Adding to the register

Differences found by a run are triaged into either a new entry here (with the
seven fields above and a rule the gate can verify) or a GitHub issue. A new entry
is a new commit that names the run that found it. No entry is added without
evidence, and none may cover an unexplained difference in the current data
"until someone looks".
