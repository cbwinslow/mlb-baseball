# SQL Resources & SQLMesh Transformation Guide

This guide catalogs all package-owned SQL resources (`mlb_baseball/sql/*.sql`) and SQLMesh transformation models (`transforms/models/*.sql`), explaining their purpose, dependency lineage, input tables, output schemas, and health check validations.

---

## 1. SQL Ownership & Architectural Doctrine

Per `AGENTS.md` and `docs/SQL_OWNERSHIP.md`:
1. **Named SQLMesh Models** (`transforms/models/`): Own all deterministic, set-based feature family derivations, rolling statistics, and analytical marts.
2. **Numbered Migrations** (`migrations/`): Own all DDL statements (table creation, schema extensions, indexes, views).
3. **Named SQL Resources** (`mlb_baseball/sql/`): Own all operational database interactions, live pipeline enrichments, and dynamic queries that cannot be SQLMesh models.
4. **No Arbitrary Inline SQL**: Mutating queries must be declared in named resource files with strict parameter validation.

---

## 2. SQLMesh Transformation Models (`transforms/models/`)

| Model File | Model Name | Materialization | Upstream Dependencies | Core Output Columns |
|---|---|---|---|---|
| `pitch_movement.sql` | `gold.pitch_movement` | Incremental by `game_date` | `raw.statcast_pitch`, `gold.game_feature` | `fastball_ivb_in`, `curve_drop_in`, `vert_separation_in`, `spin_rate_rpm`, `batting_chase_pct`, `batting_heart_swing_pct` |
| `pitcher_command.sql` | `gold.pitcher_command` | Incremental by `game_date` | `raw.statcast_pitch`, `gold.game_feature` | `shadow_pct`, `heart_pct`, `waste_pct`, `command_index` |
| `pitcher_estimators.sql` | `gold.pitcher_estimators` | Incremental by `game_date` | `raw.retrosheet_event`, `gold.game_feature` | `fip`, `xfip`, `siera`, `csw_pct`, `whiff_pct`, `k_bb_pct` |
| `catcher_framing_csae.sql` | `gold.catcher_framing_csae` | Incremental by `game_date` | `raw.statcast_pitch`, `gold.game_feature` | `catcher_csae_pct`, `catcher_framing_runs` |
| `team_bsr_comprehensive.sql` | `gold.team_bsr` | Incremental by `game_date` | `raw.retrosheet_event`, `gold.game_feature` | `wsb`, `ubr`, `bsr_total` |
| `statcast_expected.sql` | `gold.statcast_expected` | Incremental by `game_date` | `raw.statcast_pitch`, `gold.game_feature` | `offense_hard_hit_pct`, `offense_barrel_pct`, `offense_xwoba`, `starter_xwoba` |
| `batted_ball.sql` | `gold.batted_ball` | Incremental by `game_date` | `raw.retrosheet_event`, `gold.game_feature` | `gb_pct`, `fb_pct`, `ld_pct`, `pu_pct`, `hr_fb_ratio` |
| `pitch_discipline.sql` | `gold.pitch_discipline` | Incremental by `game_date` | `raw.retrosheet_event`, `gold.game_feature` | `o_swing_pct`, `z_swing_pct`, `swing_pct`, `o_contact_pct`, `z_contact_pct` |
| `team_woba.sql` | `gold.team_woba` | Incremental by `game_date` | `raw.retrosheet_event`, `gold.game_feature` | `woba`, `wrc_plus`, `wraa` |
| `park_factors_weather.sql` | `gold.park_factors_weather` | Incremental by `game_date` | `raw.retrosheet_gameinfo`, `gold.game_feature` | `park_run_factor`, `temperature_f`, `wind_speed_mph`, `wind_dir_factor` |
| `run_expectancy.sql` | `gold.run_expectancy` | Materialized table | `raw.retrosheet_event` | 24-state RE24 run expectancy table |
| `venue.sql` | `core.venue` | Materialized dimension | `raw.retrosheet_gameinfo` | Venue dimensions, altitude, surface type, orientation |

---

## 3. Named SQL Resource Catalog (`mlb_baseball/sql/`)

### 3.1 Feature Updates & Mathematical Calculations
- **`pitch_movement_update.sql`**: Aggregates pitch-level `pfx_z` and release spin from `raw.statcast_pitch` into pitcher-game records, then computes strictly backward-looking rolling 30-day starter metrics and 14-day bullpen metrics.
- **`pitcher_command_update.sql`**: Maps pitch coordinates to Statcast 4-tier attack zones (Heart: 5; Shadow: 1-9 borders; Chase: 11-14; Waste: outside) and updates `gold.game_feature`.
- **`team_pitcher_estimators_retrosheet_update.sql`**: Vectorized calculation of FIP, cFIP, xFIP, and SIERA across starters and bullpens from Retrosheet events.
- **`catcher_framing_csae_update.sql`**: Computes shadow-zone Called Strike Above Expected (CSAE%) and framing runs per catcher.
- **`team_bsr_comprehensive_retrosheet_update.sql`**: Computes weighted stolen base runs (wSB) and ultimate base running (UBR) into total BsR.
- **`int_diff_update.sql`**: Vectorized single-pass algebraic update calculating all 23 symmetric home-minus-away difference columns.
- **`statcast_expected_retrosheet_update.sql`**: Computes Barrels/PA, Hard-Hit%, and xwOBA for batters, starters, and relief units.

### 3.2 Markov Chain & Simulation Queries
- **`markov_transition_counts.sql`**: Groups Retrosheet play-by-play events by pre-state `(outs, b1, b2, b3)` and post-state `(post_outs, post_b1, post_b2, post_b3, runs)` to estimate base/out transition probability matrices.
- **`markov_half_inning_runs.sql`**: Extracts historical per-half-inning run totals for Monte Carlo calibration checks.
- **`markov_game_scores.sql`**: Extracts real game final scores for game simulation validation.
- **`pitcher_arsenal_select.sql`**: Selects pitch-mix usage, run values/100, wOBA against, and whiff rates for a specified pitcher and season from `raw.statcast_pitcher_arsenal_stat`.
- **`batter_arsenal_select.sql`**: Selects pitch counts, run values/100, wOBA, and whiff rates for a specified batter and season from `raw.statcast_batter_arsenal`.

### 3.3 Data Conformance & Identity Resolution
- **`conform_player_insert.sql`**: Reconciles player identities across Retrosheet, MLBAM, FanGraphs, and Baseball-Reference IDs into `core.player`.
- **`conform_team_insert.sql`**: Normalizes franchise relocations and 3-letter team codes into `core.team`.
- **`conform_venue_insert.sql` / `conform_venue_enrich.sql`**: Conforms ballpark identities, historical park names, and physical dimensions into `core.venue`.

### 3.4 Automated Health Check Queries
- **`pitch_movement_health_check.sql`**: Asserts physical domain bounds on IVB ($-30$ to $+30$ in), curve drop ($-35$ to $+10$ in), and spin rate ($500$ to $4000$ RPM).
- **`pitcher_command_health_check.sql`**: Asserts zone percentages are within $[0, 1]$ and non-null on completed Statcast games.
- **`team_pitcher_estimators_health_check.sql`**: Asserts SIERA, xFIP, and FIP bounds ($0.5$ to $15.00$).
- **`catcher_framing_csae_health_check.sql`**: Asserts CSAE% is within $[-0.30, +0.30]$.
- **`team_bsr_comprehensive_health_check.sql`**: Asserts BsR total bounds ($-30$ to $+30$ runs).
