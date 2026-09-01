# Grain-complete statistic backbone — design

**Date:** 2026-09-01
**Status:** proposed — owner reviewing
**Executes:** `plans/03-research-statistics-and-features.md` §03B/03C, and
`docs/PRODUCT_DIRECTION.md` "Research database (better than baseball.computer /
baseballr)". Fast-follow to Research Database v1.

## The finding

We inventoried baseball.computer's published surface and our own. The result
is the opposite of what you'd expect:

**We are ahead on the hard part and behind on the easy part.**

- **Ahead:** we already compute wOBA, wRC+, wRAA, FIP, xFIP, SIERA, RE24, WPA,
  Leverage Index, Win Expectancy, BsR (wSB + UBR + wGDP), park factors,
  catcher framing, pitch discipline (CSW%/whiff%/F-strike%), batted-ball
  rates, platoon splits, Statcast pitch-movement and command metrics — every
  one with a cited formula, a hand-calculated fixture, and (for FIP, wOBA,
  RE24, park factors, framing) an external tie-out. baseball.computer ships
  none of wOBA/FIP/WAR as headline stats; they give you the ingredients and
  stop.
- **Behind:** all of that lives on **one table at one grain** —
  `gold.game_feature`, pregame, `home_*`/`away_*` paired columns, keyed to a
  single game instance. A researcher who wants "Gerrit Cole's rolling CSW% by
  start", "team wOBA by game", or "player-season FIP" **cannot query it** —
  they'd have to rebuild from `raw`. baseball.computer's whole value is the
  clean grain ladder: event → player-game → player-season → career;
  team-game → team-season.

So the work here is **mostly re-plumbing validated formulas to new grains**,
not inventing or re-validating metrics. That is what makes this safe to do —
and it is the exact opposite of the ~110 un-cited "Engine" packages, which
stay frozen.

## What we're building

A stable, documented statistic table at every grain a sabermetric researcher
expects, built from `core.play` (Retrosheet 1910-2025 + MLB API 2026) and
`core.pitch` (Statcast 2008+), each one analysis-ready and exportable with one
`mlb export` command.

### The innovation (why anyone would use this over the alternatives)

| Tool | What it is | Gap we fill |
|---|---|---|
| baseball.computer | Retrosheet-only, classical stats, all history, meticulous | no Statcast, no advanced stats, no live/market data, no bulk export |
| baseballr (R pkg) | one function per stat, formula in the help page | not a queryable warehouse; you assemble it yourself |
| FanGraphs | the reference website | no bulk export, no history-completeness honesty, closed |

**Nobody offers a single queryable Postgres warehouse with classical +
Statcast + advanced sabermetrics + prediction-market data, at a stable grain
for every table, with every formula's citation and tie-out status shipped
alongside it as data, exportable to CSV/Parquet/Excel in one command.** That
is the product.

## Scope — staged

### Stage 1 — classical counting/rate backbone (foundation)

New canonical grain relations, built from `core.play`:

| Relation | Grain | Contents |
|---|---|---|
| `core.player_game` | (player, game, role) | batting **or** pitching box line per player per game — PA, AB, H, 1B/2B/3B/HR, TB, BB, IBB, HBP, SF, SH, K, RBI, GIDP, R; IP, BF, ER, R, H, BB, K, HR for pitchers |
| `core.team_game` | (team, game) | team box line per game (same columns, team totals) + the real final score |
| `gold.player_season_batting` / `_pitching` | (player, season, team) | season aggregates + AVG/OBP/SLG/OPS/ISO/BABIP/BB%/K%/SB%; ERA/RA9/WHIP/K9/BB9/HR9/K:BB/FIP-peripheral rates |
| `gold.team_season_batting` / `_pitching` | (team, season) | same, team grain |
| `gold.player_career_batting` / `_pitching` | (player) | career roll-up |

The relation names above are illustrative. Final names are set in the plan and
must fit `CLAUDE.md`'s naming convention (one word, two at most) — likely
`core.player_game` / `core.team_game` and 2-word `gold.*` names, not the
3-word placeholders here.

Every stat is MLB-glossary-defined (unambiguous). Each relation:
- named `.sql` builder in `mlb_baseball/sql/` + a migration (the proven
  one-writer-per-table production path). Designed so a SQLMesh
  `INCREMENTAL_BY_TIME_RANGE` model on `season` is a drop-in replacement once
  ADR-088's promotion path is open (`docs/SQL_OWNERSHIP.md`,
  `SQLMESH_OPERATIONS.md`).
- hand-calculated fixture + tie-out against a real published player-season
  (e.g. 2023 Aaron Judge batting, 2023 Gerrit Cole pitching) within a stated
  tolerance — a unit test feeding defaults is **not** a tie-out
  (`docs/NORTH_STAR.md` validation bar).
- idempotency test (rebuild twice, identical rows).
- `mlb doctor` check (row counts, null rates, join coverage vs `core.game`).

### Stage 2 — advanced layer at the new grains

Re-plumb the **already-tied-out** formulas from `mlb_baseball/model/*.py` to
emit at player-game / player-season / team-season. Reuse the exact constants
already in those modules — only the `GROUP BY` changes.

- `gold.linear_weights` — (season) run values for BB/HBP/1B/2B/3B/HR, derived
  from our own `gold.run_expectancy_24`. This is the wOBA/wRAA foundation and
  the one genuinely-new build in this stage; baseball.computer ships the
  equivalent (`linear_weights`).
- wOBA, wRC+, wRAA at player-season / team-season (from `offense.py`).
- FIP, xFIP, SIERA at player-game / player-season (from `starter.py`,
  `pitcher_estimators.py` — FIP has the strongest tie-out in the repo).
- RE24, WPA per plate appearance (from `run_expectancy.py` +
  `gold.run_expectancy_24` + `gold.win_expectancy`).
- BsR / wSB / UBR / wGDP at player-season / team-season (from `bsr.py`).
- Batted-ball rates, pitch discipline at player-game / player-season.

Lower risk than Stage 1: the formulas are validated; only the aggregation
grain is new. Each still gets its own fixture + tie-out at the new grain.

### Stage 3 — historical-completeness honesty  *(roadmap)*

baseball.computer's real methodological contribution: `trajectory_unknown`,
`known_trajectory_out_hit_ratio`, `coverage_weighted_*` — corrects the
selection bias in pre-1988 batted-ball data (scorekeepers recorded trajectory
for outs far more often than for hits). Genuinely useful for historical
research and distinctive. Build after Stages 1-2 prove out.

### Stage 4 — parameterized rolling windows  *(roadmap)*

One parameterized view/function: any stat, trailing N games / N days /
season-to-date / career, point-in-time-safe. `PRODUCT_DIRECTION.md` and Agy's
catalog both asked for trailing 10/30/season/custom. One parameterized
builder, never 12 copies of every stat.

### Stage 5 — export & catalog polish  *(roadmap)*

- The `public_safe` Parquet bundle (the deferred v1 follow-up) — now with a
  real per-relation source-lineage review.
- A machine-readable **stat catalog** relation: every view → formula,
  citation, tie-out status, grain, rights profile. "baseballr's help page, as
  queryable data."
- A `duckdb`-ready quickstart: point DuckDB at the Parquet bundle, zero setup.

### Explicitly out of scope

- **WAR.** Many contentious components; both fWAR and bWAR are proprietary
  blends. We keep ingesting BRef's `core.player_war`, and ship "our WAR,
  method fully documented" as its own separate later effort — never "matches
  FanGraphs".
- The ~110 frozen "Engine" packages. Untouched.
- Copying any baseball.computer SQL, schema, or prose. Their repo is
  CC BY-NC-SA (`docs/ROADMAP.md` L85-107). We reference the *concept* of a
  grain ladder; the formulas are public sabermetric research implemented here
  from primary sources (FanGraphs glossary, *The Book*, MLB glossary).

## Data-flow (Stage 1)

```
core.play (PA grain, Retrosheet + MLB API)
  -> sql/player_game_build.sql   -> core.player_game   (per player per game)
  -> sql/team_game_build.sql     -> core.team_game     (per team per game)
core.player_game
  -> sql/player_season_build.sql -> gold.player_season_batting / _pitching
  -> sql/player_career_build.sql -> gold.player_career_batting / _pitching
core.team_game
  -> sql/team_season_build.sql   -> gold.team_season_batting / _pitching
```

New CLI: none. `mlb report` gains these builders (it already builds the
existing `gold.*_season` tables); `mlb doctor` gains a check per relation.
`mlb export`'s allow-list gains the new relations.

## Error handling

- A builder run before `core.play` is populated → clear error naming the
  prerequisite, non-zero exit (matches `conform.py::_check_prerequisites`).
- Retrosheet vs MLB-API `core.play` rows have different completeness (no
  runner-destination columns in either today, per `docs/RESEARCH.md`) — stats
  that need data we don't have are left NULL with a documented reason, never
  guessed. Batting-out and GIDP handling follows the Retrosheet event spec.
- Rebuild is truncate-and-replace, transactional, idempotent.

## Testing

Per relation:
- `tests/integration/` against `mlb_test`: seed a known player's game log,
  build, assert every counting stat and rate against hand math.
- **Tie-out test**: load one real player-season's Retrosheet events, build,
  assert the season line matches the published figure (Baseball-Reference /
  FanGraphs) within tolerance. Skipped with a clear marker if the fixture
  data isn't present, never silently passing.
- Idempotency: build twice, assert identical.
- `tests/unit/`: the rate-stat formulas (AVG/OBP/SLG/wOBA/FIP/…) as pure
  functions with hand-checked inputs.
- `mlb doctor` check has its own test.

## Acceptance (Stage 1)

- `core.player_game`, `core.team_game`, `gold.player_season_batting`/
  `_pitching`, `gold.team_season_batting`/`_pitching`, `gold.player_career_*`
  all build, idempotent, doctor-checked, in the `mlb export` allow-list.
- Each has a passing tie-out test against a real published player-season.
- `docs/DATA_DICTIONARY.md` + `docs/TABLE_CONTRACTS.md` document every column
  and grain.
- The existing `gold.player_season` / `gold.team_season` (BRef/Lahman-sourced,
  2008+) either become views over the new Retrosheet-backed tables or are
  clearly documented as the "official-source" alternative — one deliberate
  choice, recorded in an ADR, no two-writer ambiguity.

## Workstreams

1. **WS1 — Stage 1 grain tables.** `core.player_game` + `core.team_game`
   first (they feed everything), then the season/career roll-ups. Largest;
   delegatable to Agy against a per-relation spec once the `core.player_game`
   column contract is nailed and reviewed.
2. **WS2 — `gold.linear_weights`** from `gold.run_expectancy_24`. Small,
   foundational for Stage 2. Claude.
3. **WS3 — Stage 2 advanced re-plumb.** After WS1. Per-metric, reusing
   `model/*.py` constants.
4. **WS4 — docs** (data dictionary, table contracts, stat catalog stub).
