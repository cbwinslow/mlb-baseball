# Audit: what the existing Retrosheet ingestion tests prove

Task 1.1 of `raw-source-tieout`. Written 2026-09-27 from the code and tests as
they stand on branch `docs/raw-source-tieout` (plus its build branch). Nothing
here was run against production; the table list comes from
`information_schema` on production `mlb` (36 `raw.retrosheet_*` tables) and the
loader for each table comes from `mlb_baseball/connectors/retrosheet*.py`.

## How to read this

Five behaviors, one letter each:

| Letter | Behavior | "Proven" means |
| --- | --- | --- |
| **L** | Landing | Rows load into the table and the count is checked |
| **R** | Reload scope | Running the load again replaces its own scope without touching other rows |
| **M** | Missing / failed input | A missing or broken input is handled and does not lose other data |
| **C** | Column names pinned | A test fails if the table's columns drift from the source contract |
| **X** | Content correct | Values are compared with an independent truth (a second source or a known fact) |

Marks: **yes** = proven by a test; **part** = proven for part of the table, one
table of a shared code path, or one row; **no** = no test proves it.

Almost every "yes" in **L, R, M** comes from tests that use a small fixture and
check counts or a few columns. **X is the behavior that catches wrong data**, and
it is the weakest column throughout. The findings are at the bottom.

## Table matrix

Test file abbreviations: `load` = `tests/integration/test_retrosheet_load.py`,
`event` = `test_retrosheet_event_load.py`, `box` = `test_retrosheet_box_load.py`,
`gamelog` = `test_retrosheet_gamelog_load.py`, `ref` = `test_retrosheet_reference_load.py`,
`roster` / `schedule` / `trans` = the matching `test_retrosheet_*_load.py`,
`larsen` = `tests/integration/test_larsen_perfect_game.py`,
`extract` = `tests/unit/test_retrosheet_extract.py`,
`gl-fields` = `tests/unit/test_retrosheet_gamelog_fields.py`,
`chadwick` = `tests/unit/test_chadwick_tools.py`.

### CSV product (`connectors/retrosheet.py`, loaded per year)

| Table | L | R | M | C | X | Evidence and gap |
| --- | --- | --- | --- | --- | --- | --- |
| `retrosheet_plays` | yes | part | yes | part | no | `load` lands all seven tables and reads `gid, batter`; `extract` asserts six column names exist (`gid, batter, pitcher, single, double, hr`). Columns genuinely differ by year (1899 has 161, 1898 and 2024 have 177); `load` proves a narrower year loads with NULLs using a synthetic two-column frame. No count or value is compared to anything. |
| `retrosheet_gameinfo` | yes | yes | yes | no | part | `load` reload test uses this table to prove year scope. `larsen` checks one game's teams, score, pitchers, attendance, park. `test_conform.py` checks `gametype` casing. |
| `retrosheet_batting` | yes | part | yes | no | no | Only "count > 0". Reload scope is proven for `gameinfo` on the same code path, not for this table. |
| `retrosheet_pitching` | yes | part | yes | no | no | Same as batting. |
| `retrosheet_fielding` | yes | part | yes | no | no | Same as batting. |
| `retrosheet_teamstats` | yes | part | yes | no | no | Same as batting. |
| `retrosheet_allplayers` | yes | part | yes | no | no | Same as batting. |

### Event files parsed by Chadwick (`connectors/retrosheet_event.py`)

| Table | L | R | M | C | X | Evidence and gap |
| --- | --- | --- | --- | --- | --- | --- |
| `retrosheet_event` | yes | yes | yes | no | part | `event` proves both tables land for two seasons, reload replaces its own years only, a second archive for the same season does not wipe the first (`_scope` regression), an already-loaded archive is skipped, one year's `cwevent` failure does not lose the others. `chadwick` asserts four columns (`GAME_ID, BAT_ID, PIT_ID, EVENT_TX`) and the game ids of a two-game fixture. The field request (`CWEVENT_FIELDS = "0-96"`, `CWEVENT_EXTENDED_FIELDS = "0-63"`, `chadwick_tools.py:28,38`) is not pinned by any test against the resulting 168 columns. `larsen` checks 56 plays, 0 hits and no runner on first in one game. |
| `retrosheet_game` | yes | yes | yes | no | part | Same tests as above; `larsen` checks one game row. `chadwick` asserts three columns. |

### Box scores (`connectors/retrosheet_box.py`, 1871–1961 only)

| Table | L | R | M | C | X | Evidence and gap |
| --- | --- | --- | --- | --- | --- | --- |
| `retrosheet_box_game` | yes | yes | yes | no | part | `box`: two games land; visitor, home and (for the constructed team file) team names checked for those two games. Reload scope, already-loaded skip, missing archive, an authoritatively empty year (1871) and a known-unparseable Negro League year are all tested. |
| `retrosheet_box_batting` | part | yes | yes | no | no | Count > 0 only. No value compared. |
| `retrosheet_box_pitching` | part | yes | yes | no | no | Count > 0 only. |
| `retrosheet_box_fielding` | part | yes | yes | no | no | Count > 0 only. |
| `retrosheet_box_double` | yes | yes | yes | no | no | `box`: the table exists, has a row, and its `game_id` is one of the two games. |
| `retrosheet_box_triple` | part | yes | yes | no | no | Only "key present in the counts". A zero-row table passes. |
| `retrosheet_box_homerun` | part | yes | yes | no | no | Same as triple. |
| `retrosheet_box_stolenbase` | part | yes | yes | no | no | Same as triple. |
| `retrosheet_box_doubleplay` | part | yes | yes | no | no | Same as triple. |
| `retrosheet_box_tripleplay` | part | yes | yes | no | no | Same as triple. |
| `retrosheet_box_sacbunt` | part | yes | yes | no | no | Same as triple. |

### Game logs (`connectors/retrosheet_gamelog.py`)

| Table | L | R | M | C | X | Evidence and gap |
| --- | --- | --- | --- | --- | --- | --- |
| `retrosheet_gamelog` | yes | yes | yes | yes | part | `gamelog` lands 20 rows and asserts 163 columns (161 fields + `_season` + `_loaded_at`); `gl-fields` pins the 161-field list length, uniqueness and positions 0, 3, 9, 16, 159, 160. Missing year handled. One row's four columns checked non-null. |
| `retrosheet_gamelog_post` | yes | yes | no | part | part | Lands 3 rows and replaces only its own game type. Shares the field list; its column count is not asserted. No test for a missing post-season archive. `larsen` checks the 1956 World Series game. |

### Reference tables (`connectors/retrosheet_reference.py`)

| Table | L | R | M | C | X | Evidence and gap |
| --- | --- | --- | --- | --- | --- | --- |
| `retrosheet_park` | yes | yes | no | no | no | `ref` lands all eleven tables from hand-written fixtures and asserts park has 1 row after a rerun. |
| `retrosheet_team` | yes | part | no | no | no | Count > 0 only. |
| `retrosheet_biofile` | yes | part | no | no | no | Count > 0 only. |
| `retrosheet_biofile0` | yes | part | no | no | no | Count > 0 only. |
| `retrosheet_coach` | yes | part | no | no | no | Count > 0 only. |
| `retrosheet_relative` | yes | part | no | no | no | Count > 0 only. |
| `retrosheet_ballpark` | yes | part | no | no | no | Count > 0 only. |
| `retrosheet_coach0` | yes | part | no | no | no | Count > 0 only. |
| `retrosheet_manager` | yes | part | no | no | no | Count > 0 only. |
| `retrosheet_team0` | yes | part | no | no | no | Count > 0 only. `test_conform.py` uses a hand-made version to test supplemental team identities. |
| `retrosheet_umpire` | yes | part | no | no | part | Fixture asserts exactly 3 rows. |

### Rosters, schedule, transactions

| Table | L | R | M | C | X | Evidence and gap |
| --- | --- | --- | --- | --- | --- | --- |
| `retrosheet_roster` | yes | yes | no | no | part | `roster`: team and season are taken from the file name (ANA, BOS, 2024); one row read. Rerun count equals first count. |
| `retrosheet_schedule` | yes | yes | no | part | part | `schedule`: 2 rows; the league/game columns that would otherwise collide are checked on one 1877 row. |
| `retrosheet_transaction` | yes | yes | no | part | part | `trans`: 2 rows and 17 columns; one row read. Names are not pinned. |

**All 36 tables appear above** (7 CSV + 2 event + 11 box + 2 game log + 11
reference + roster + schedule + transaction).

## Other tests that touch Retrosheet

- **`larsen`** (`tests/integration/test_larsen_perfect_game.py`): the only test
  that compares two sources. It loads one real, trimmed game (1956 World Series
  Game 5) through the CSV product, the event files and the post-season game log
  and asserts the same eight facts from each. This is the model the gate
  generalizes; it covers one game, not a season.
- **`chadwick`** and `tests/unit/test_retrosheet_event_split.py`: prove the
  Chadwick wrappers, year splitting, team-file writing and `cwbox` XML parsing.
  They prove parsing mechanics, not that counts equal the source.
- **`test_conform.py`**: proves the `core.game` and `core.play` builders work
  (`test_build_games_normalizes_gametype_casing`, `test_run_populates_team_player_and_game`,
  `test_build_plays_and_pitches_unify_both_sources`, current-season fill). These
  tests create `raw.retrosheet_*` tables by hand with a handful of rows, so they
  prove SQL logic, not that real loaded Retrosheet data survives conformance.
- **Health check** `core.play retrosheet coverage` (`conform.py:1943-1950`):
  compares `core.play` rows with distinct (game, event) raw rows, but only for
  games already present in `core.game` (see G7).

## Findings (gaps)

"Could hide wrong data" means a wrong value or a dropped row would pass every
current test. **Closure** names where this change deals with it. Status is
updated in task 3.2.

| ID | Gap | Could hide wrong data? | Closure | Status |
| --- | --- | --- | --- | --- |
| G1 | No test compares two sources for a whole season; `larsen` covers one game. Event, CSV plays, CSV batting and game logs could disagree without any test failing. | **Yes** | The gate itself (tasks 2.3, 2.4) | open |
| G2 | `retrosheet_event`: the Chadwick field request is not pinned to the resulting columns; only 4 columns are asserted. A `cwevent` change that shifts or drops fields would load successfully. | **Yes** | Pinned column contract (3.1) and production schema check (2.6) | open |
| G3 | No test loads a real (small) event fixture and checks known counts beyond `larsen`'s one game (plate appearances, strikeouts, home runs for a fixture with known totals). | **Yes** | Integration test with known counts (3.2) | open |
| G4 | The six box supplementary tables (triple, homerun, stolenbase, doubleplay, tripleplay, sacbunt) pass with zero rows; box batting, pitching and fielding are count > 0 only. | Yes for box, but box covers 1871–1961 only and is used only as a cross-check | Issue, unless a cheap known-count assertion is added in 3.2 | open |
| G5 | CSV `batting`, `pitching`, `fielding`, `teamstats`, `allplayers` and `plays` have no value or column check; reload scope is proven on `gameinfo` only. | **Yes** (`plays` and `batting` feed the gate; the others do not) | Season tie-out for `plays`/`batting` (2.3); the rest via issue | open |
| G6 | Reference, roster, schedule and transaction tables: no missing-input test and no column pin; roster feeds identity checks. | Partly (identities) | Roster identity check (2.4); the rest via issue | open |
| G7 | `core.play` from `raw.retrosheet_event` is an inner join to `core.game` (`conform.py:1094`), and `core.game` is built from the CSV `gameinfo` table (`conform.py:480`). An event game with no `gameinfo` row is silently dropped from `core.play`, and the existing coverage check is scoped to games in `core.game` (`conform.py:1946-1949`, GitHub #184), so it cannot see the loss. It is a known, documented case (an Oct-1900 Pittsburgh series), but nothing counts them. | **Yes** | The `core` completeness check reports event games absent from `core.game` as their own line (2.5) | open |
| G8 | No test builds `core.game` or `core.play` from real loaded Retrosheet rows (only hand-made tables); no test compares `core` counts with raw. | **Yes** | The `core` completeness check (2.5) | open |
| G9 | CSV `plays` legitimately has fewer columns in early years (161 vs 177). A pinned column contract for that table cannot be one exact list. | Design detail, not a data gap | Decide the rule when doing 2.6/3.1: a per-era allowed set, with missing early-era columns listed in the register. Recorded here so the design text (which says "fails on any column missing") is corrected then. | open |

## What this changes about earlier notes

The session handoff said "nothing compares two sources". More precisely: `larsen`
compares three sources for one game; no test compares them for a season, or for
any other game. G1 stands.
