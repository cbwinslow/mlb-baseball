## Why

The classical statistic backbone (`gold.batting_game` / `gold.pitching_game`
and the season / team / career roll-ups) is built from `raw.retrosheet_event`,
which ends in **2025**. A researcher querying the backbone for the current
season gets nothing back. Retrosheet does not publish event files for the
in-progress season, so 2026-onward needs a different source. MLB's own
per-game box-score lines (`raw.mlb_boxscore_batting` / `raw.mlb_boxscore_pitching`,
already ingested) carry the exact column set the game grain needs, plus
earned runs. The `statistic-backbone` spec already names this as planned
follow-up work.

## What Changes

- **New game-grain builder for 2026+** — `mlb_baseball/sql/batting_game_mlb_build.sql`
  and `pitching_game_mlb_build.sql`, mapping `raw.mlb_boxscore_batting` /
  `raw.mlb_boxscore_pitching` (joined to `core.game` on `game_pk` for season,
  date, team, and the `game_type = 'regular'` filter) to `gold.batting_game` /
  `gold.pitching_game`. `mlb report` runs the Retrosheet builder for ≤ 2025
  and the MLB builder for ≥ 2026; the two never write the same `(game, player,
  team)` row.
- **`source` column** on `gold.batting_game` / `gold.pitching_game` records
  which builder wrote each row (`retrosheet_event` vs `mlb_boxscore`), matching
  the pattern already on the season / career relations.
- **Earned runs / ERA for 2026+.** MLB's official scorer assigns earned runs,
  so the MLB builder populates a new `er` column on `gold.pitching_game` and
  `er` + `era` on `gold.pitching_season` / `gold.pitching_career`. The
  Retrosheet builder leaves `er` null (no earned-run data in the event stream),
  so `era` is null for 1910–2025 and real for 2026+ — a documented coverage
  cliff. `ra9` stays populated for every year.
- **pbp cross-check gate** — `scripts/verify_mlb_boxscore_tie_out.py` (or a
  section in the existing tie-out harness) rebuilds a sample of 2026
  player-game lines from `raw.mlb_playbyplay` events and compares them to the
  box-score-built rows, the same shape as the Retrosheet builder being
  cross-checked against Baseball-Reference. Runs against a built database,
  not CI.
- **`mlb doctor` checks** — row counts and join coverage for the 2026 game
  rows; a guard that no `(game, player, team)` key is written by both builders;
  the regular-season envelope check already covers the new rows.
- **Docs** — `DATA_DICTIONARY.md`, `TABLE_CONTRACTS.md`, and the honest-
  limitations doc gain the 2026 source, the `era` coverage cliff, and the
  box-score-vs-event methodology note.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `statistic-backbone`: coverage extends past 2025 (the "Retrosheet-event
  builder covers 1910–2025" statement becomes "1910–2025 from Retrosheet
  events, 2026-onward from MLB box scores"); the "Statistics are computed from
  Retrosheet events" requirement gains a scoped carve-out for the current
  season (MLB's official box score is the primary source there, with a
  play-by-play cross-check standing in for the Baseball-Reference tie-out);
  the "no `era`" clause of the null-policy requirement is narrowed to
  1910–2025 (the event stream), because the 2026 source carries earned runs.

## Impact

- **Code:** `mlb_baseball/report.py` (builder dispatch by season), two new
  `mlb_baseball/sql/*.sql` builders, one new migration (`er` / `era` columns +
  `source` on the game relations if not already present), `mlb_baseball/health.py`
  or `report.health_check()` (new checks), `scripts/` (cross-check).
- **Schema:** additive columns only (`er`, `era`, `source` where missing) —
  no column removed, no type changed. `gold.pitching_season` / `_career`
  roll-up SQL recomputes `era` alongside `ra9`.
- **Data:** `mlb report` writes ~1,900 new game rows per team-season for 2026;
  the season / team / career roll-ups already aggregate from the game grain, so
  they pick up 2026 with no change beyond the `era` recompute.
- **Docs:** `DATA_DICTIONARY.md`, `TABLE_CONTRACTS.md`, honest-limitations doc,
  `openspec/specs/statistic-backbone/spec.md` (via the delta).
- **No new dependency.** `raw.mlb_boxscore_*` and `raw.mlb_playbyplay` are
  already ingested by the `mlb_api` connector.
