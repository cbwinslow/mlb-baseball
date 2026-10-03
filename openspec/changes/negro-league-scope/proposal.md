## Why

Negro League games (Retrosheet's `negro_league` archives, 1903–1961) sit in
`core.game` with `game_type = 'regular'`, next to MLB games, and nothing marks
them. They are a different league, outside the betting markets the product
targets, and they mix into league averages, Elo, park factors and the
game-win training window (issue #258). They are also nearly the whole readiness
blocker (#256): about 3,700 of the 3,750 games the readiness gate counts as
unexplained nulls are Negro League games with no play-by-play.
`core.team.league` is not a usable flag: 145 teams have a NULL league and they
include non-Negro-League clubs.

## What Changes

- Add a source-derived scope flag to `core.game` (and `core.team`) set by
  `conform`, using Retrosheet's own Negro League club registry
  (`biodata.zip` `teams0.csv`, already used by `retrosheet_box.py`), checked
  against the `negro_league` source archives and Lahman `lgid`.
- Add one view, `core.game_mlb`, that is the regular-season major-league pool;
  model, feature-store and readiness code read it instead of re-filtering.
- Raw tables are not touched. The games stay in `core.game`, flagged, so any
  future Negro League study keeps its data.
- Measure the effect on gold backbone totals, Lahman/Baseball-Reference
  reconciliation and the Retrosheet tie-out before and after; record it.
- Document the rule in the nearest owning DOX (`conform.py.dox.md`) and add an
  ADR.
- Clears most of the #256 readiness blocker; the remaining games (about 44)
  are handled as explained gaps in a follow-up task here.

## Capabilities

### New Capabilities
- `game-scope`: which games count as the major-league regular-season pool, and
  how non-MLB games are flagged without leaving the database.

### Modified Capabilities

## Impact

- `mlb_baseball/conform.py` (+ `conform.py.dox.md`), a migration for the new
  column(s) and view, `mlb_baseball/model/season.py` and the feature store
  readers of `core.game`, `mlb_baseball/readiness.py` coverage wording,
  `docs/DECISIONS.md`.
- No raw-table or ingestion change. Production `mlb` needs the migration
  applied by the owner (the safety filter blocks Claude from doing it).
- Depends on nothing else; independent of `stable-ids-incremental-conform`,
  but both change `conform`, so land one first and rebase the other.
