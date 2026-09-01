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
expects, built from `raw.retrosheet_event` (1910-2025) with a separate
`raw.mlb_playbyplay` builder for 2026+, each one analysis-ready and exportable
with one `mlb export` command. (Source is `raw.retrosheet_event`, not
`core.play` — see "The interface question" below for why.)

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

New derived grain relations. **Placement: `gold`, not `core`** — a box-score
line is an aggregation of `core.play` / `raw.retrosheet_event`, i.e. a derived
stat, which is what `gold` is for (`docs/ARCHITECTURE.md`). `core` stays
dimensions + facts at their natural grain.

**Source: `raw.retrosheet_event` for 1910-2025, `raw.mlb_playbyplay` for
2026+** — matching *exactly* how the existing tied-out team stats are built
(`sql/team_woba_retrosheet_update.sql` reads `re.bat_event_fl`, `re.ab_fl`,
`re.sf_fl`, `re.h_cd`, `re.event_cd`, `re.rbi_ct`, ...). Building from
`core.play` instead would silently diverge from those numbers, because
`core.play` doesn't carry `bat_event_fl` / `ab_fl` / `sf_fl` / `rbi_ct`
(inventory §4). The historical / live split mirrors `offense.py`'s existing
`compute()` vs `compute_live()` pattern.

| Relation | Grain | Contents |
|---|---|---|
| `gold.batting_game` | (batter, game) | batting box line — PA, AB, R, H, 1B, 2B, 3B, HR, TB, RBI, BB, IBB, HBP, SF, SH, SO, GIDP. SB/CS are baserunning, not batting — deferred to a later `gold.baserunning_game`. |
| `gold.pitching_game` | (pitcher, game) | pitching box line — BF, outs (→IP), H, R, ER, BB, IBB, SO, HR, HBP, WP, BK; W/L/SV/HLD from the decision |
| `gold.batting_season` / `gold.pitching_season` | (player, season, team) | box-line aggregate + AVG/OBP/SLG/OPS/ISO/BABIP/BB%/K%/SB%; ERA/RA9/WHIP/K9/BB9/HR9/K:BB |
| `gold.batting_team` / `gold.pitching_team` | (team, season) | same, team grain |
| `gold.batting_career` / `gold.pitching_career` | (player) | career roll-up |

Names fit `CLAUDE.md`'s one-to-two-word convention. Two-way players get a row
in both the batting and pitching relations.

Every stat is MLB-glossary-defined (unambiguous). Each relation:
- named `.sql` builder in `mlb_baseball/sql/` + a migration. This is not a
  choice against SQLMesh — `docs/SQLMESH_OPERATIONS.md` is explicit that "the
  original `mlb` database is never a SQLMesh target without a separately
  [authorized promotion]", so a named `.sql` + migration is the *only*
  production-ready path today, and it is exactly what ADR-088 prescribes for
  the interim ("port existing ones table-by-table after a full-table tie-out;
  never two writers"). Each builder is one parameterized statement so a
  SQLMesh `INCREMENTAL_BY_TIME_RANGE` model on `season` is a literal drop-in
  once that promotion gate opens.
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
- wOBA, wRC+ at player-season / team-season (from `offense.py` constants).
  wRAA is exposed as a standalone column — today it exists only folded into
  the wRC+ numerator, so this is partly new work, not a pure re-plumb, and
  gets its own fixture.
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
raw.retrosheet_event (1910-2025)  +  raw.mlb_playbyplay (2026+)
  -> sql/batting_game_build.sql    -> gold.batting_game    (per batter per game)
  -> sql/pitching_game_build.sql   -> gold.pitching_game   (per pitcher per game)
gold.batting_game
  -> sql/batting_season_build.sql  -> gold.batting_season
  -> sql/batting_career_build.sql  -> gold.batting_career
gold.pitching_game  -> gold.pitching_season / gold.pitching_team / gold.pitching_career
gold.batting_game   -> gold.batting_team
core.player / core.team / core.game join in for readable names + season keys
```

New CLI: none. `mlb report` gains these builders (it already builds the
existing `gold.*_season` tables); `mlb doctor` gains a check per relation.
`mlb export`'s allow-list gains the new relations.

## Error handling

- A builder run before `raw.retrosheet_event` exists → skips that relation
  with a logged message and returns 0, leaving the other `mlb report` builders
  to run (matches `_build_player_season`'s posture with `raw.bref_*`). It
  pre-checks the source table's existence rather than TRUNCATE-then-catch, so
  a missing *source* skips cleanly while a missing *target* table (migrations
  not run) still fails loudly. The 2026+ live path degrades the same way when
  `raw.mlb_playbyplay` is absent.
- Retrosheet and MLB-API play-by-play have different completeness (neither
  carries runner-destination detail today, per `docs/RESEARCH.md`) — stats
  needing data we don't have are left NULL with a documented reason, never
  guessed. `bat_event_fl` / `ab_fl` / `sh_fl` / `sf_fl` / `h_cd` / `rbi_ct`
  handling follows the Retrosheet event spec and the precedent already set in
  `sql/team_woba_retrosheet_update.sql` (ADR-034's `bat_event_fl` finding).
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

- `gold.batting_game`, `gold.pitching_game`, and the season / team / career
  roll-ups all build, idempotent, doctor-checked, in the `mlb export`
  allow-list.
- Each has a passing tie-out test against a real published player-season
  (batting: a documented Aaron Judge season vs Baseball-Reference; pitching: a
  documented Gerrit Cole season).
- `docs/DATA_DICTIONARY.md` + `docs/TABLE_CONTRACTS.md` document every column
  and grain.
- The existing `gold.player_season` / `gold.team_season` (BRef/Lahman-sourced,
  2008+) either become views over the new Retrosheet-backed tables or are
  clearly documented as the "official-source" alternative — one deliberate
  choice, recorded in an ADR, no two-writer ambiguity.

## Workstreams

1. **WS1 — Stage 1 grain tables.** `gold.batting_game` first (cleanest —
   every stat is a direct cwevent field), as the reference implementation.
   Then `gold.pitching_game` (earned-run attribution is the hard part), then
   the season / team / career roll-ups. The batting-game build establishes
   the pattern; subsequent relations are delegatable to Agy against it.
2. **WS2 — `gold.linear_weights`** from `gold.run_expectancy_24`. Small,
   foundational for Stage 2. Claude.
3. **WS3 — Stage 2 advanced re-plumb.** After WS1. Per-metric, reusing
   `model/*.py` constants.
4. **WS4 — docs** (data dictionary, table contracts, stat catalog stub).
