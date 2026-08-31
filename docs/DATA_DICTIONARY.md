# MLB Data Dictionary & Schema Catalog

This catalog documents the schemas, grains, business keys, temporal semantics, and field definitions across all layers of the MLB Research & Forecasting Platform: `raw`, `core`, `gold`, `meta`, and `serve`.

---

## 1. Schema Architecture & Layer Taxonomy

| Schema | Role | Mutability | Granularity | Retention |
|---|---|---|---|---|
| `raw` | Source-faithful immutable landing data | Append-only / Truncate-and-load | Source grain (e.g. pitch, event, gameinfo) | Permanent historical |
| `core` | Canonical identities & conformed facts | Slowly Changing Dimensions / Conformed Facts | Player, Team, Venue, Game | Permanent historical |
| `gold` | Analysis-ready features, marts, and exports | Materialized / Incremental / Replayable | Game-level, Player-Game, Team-Game | Full historical coverage |
| `meta` | Lineage, audit trails, and run logs | Append-only | Pipeline execution run | Operational audit |
| `serve` | Slim read-only serving views for website/API | Views over `gold` / Materialized cache | Matchup, Player Card, Betting Grid | Dynamic / Live |

---

## 2. Core Feature Tables (`gold.game_feature` & `gold.game_export`)

- **Table**: `gold.game_feature`
- **View**: `gold.game_export` (all feature columns plus scheduled game metadata)
- **Grain**: One row per scheduled game instance (`game_instance_key`).
- **Temporal Semantics**: Point-in-time strictly prior to game first-pitch (`ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING`).

### 2.1 Game & Team Identification
| Column Name | Type | Description |
|---|---|---|
| `season` | `integer` | Championship season year (e.g. 2024). |
| `game_date` | `date` | Scheduled date of the game. |
| `home_team_id` | `text` | Canonical 3-letter abbreviation of home team (e.g. `LAD`, `NYY`). |
| `away_team_id` | `text` | Canonical 3-letter abbreviation of away team. |
| `game_instance_key` | `text` | Natural unique business key (`YYYYMMDD-AWAY-HOME-NUM`). |
| `venue_id` | `text` | Conformed venue identifier. |
| `home_starter_id` | `text` | MLBAM/Retrosheet conformed ID for home starting pitcher. |
| `away_starter_id` | `text` | MLBAM/Retrosheet conformed ID for away starting pitcher. |

### 2.2 Classical & Standings Features
| Column Name | Type | Formula / Origin |
|---|---|---|
| `home_win_pct`, `away_win_pct` | `numeric` | Season-to-date entering win percentage. |
| `home_win_pct_10`, `away_win_pct_10` | `numeric` | Rolling 10-game entering win percentage. |
| `home_pyth_wpct`, `away_pyth_wpct` | `numeric` | Bill James Pythagorean expectation: $\frac{R^{1.83}}{R^{1.83} + RA^{1.83}}$. |
| `home_elo`, `away_elo` | `numeric` | Entering FiveThirtyEight-style dynamic team Elo rating. |
| `elo_diff` | `numeric` | $\text{home\_elo} - \text{away\_elo}$. |
| `rest_days_diff` | `numeric` | $\text{home\_rest\_days} - \text{away\_rest\_days}$. |

### 2.3 Offensive & Batted Ball Features
| Column Name | Type | Formula / Origin |
|---|---|---|
| `home_woba`, `away_woba` | `numeric` | Linear weights entering weighted On-Base Average. |
| `home_wrc_plus`, `away_wrc_plus` | `numeric` | Era- and park-adjusted entering Weighted Runs Created Plus. |
| `home_offense_hard_hit_pct`, `away_offense_hard_hit_pct` | `numeric` | Statcast hard-hit rate ($\ge 95$ mph exit velocity). |
| `home_offense_barrel_pct`, `away_offense_barrel_pct` | `numeric` | Statcast barrels per plate appearance. |
| `home_offense_xwoba`, `away_offense_xwoba` | `numeric` | Expected wOBA from exit velocity and launch angle vectors. |
| `home_batting_chase_pct`, `away_batting_chase_pct` | `numeric` | Lineup swing rate on pitches in Chase attack zones (11-14). |
| `home_batting_heart_swing_pct`, `away_batting_heart_swing_pct` | `numeric` | Lineup swing rate on pitches in Heart attack zone (5). |

### 2.4 Starting Pitcher Advanced Metrics
| Column Name | Type | Formula / Origin |
|---|---|---|
| `home_starter_fip`, `away_starter_fip` | `numeric` | Fielding Independent Pitching: $\frac{13\text{HR} + 3(\text{BB}+\text{HBP}) - 2\text{K}}{\text{IP}} + \text{cFIP}$. |
| `home_starter_xfip`, `away_starter_xfip` | `numeric` | Expected FIP using in-season normalized HR/FB rates. |
| `home_starter_siera`, `away_starter_siera` | `numeric` | Skill-Interactive ERA with non-linear strikeout/groundball interaction. |
| `home_starter_csw_pct`, `away_starter_csw_pct` | `numeric` | Called Strike + Whiff percentage ($\frac{\text{Called} + \text{Whiff}}{\text{Total Pitches}}$). |
| `home_starter_whiff_pct`, `away_starter_whiff_pct` | `numeric` | Swinging strike rate per swing ($\frac{\text{Whiffs}}{\text{Total Swings}}$). |
| `home_starter_xwoba`, `away_starter_xwoba` | `numeric` | Statcast expected wOBA allowed on contact + K/BB. |
| `home_starter_fastball_velo`, `away_starter_fastball_velo` | `numeric` | Average 4-Seam/Sinker release velocity (mph). |
| `home_starter_fastball_ivb_in`, `away_starter_fastball_ivb_in` | `numeric` | Fastball Induced Vertical Break (ride) in inches ($pfx\_z \times 12$). |
| `home_starter_curve_drop_in`, `away_starter_curve_drop_in` | `numeric` | Breaking ball downward Magnus drop in inches ($pfx\_z \times 12$). |
| `home_starter_vert_separation_in`, `away_starter_vert_separation_in` | `numeric` | Vertical Movement Separation ($\text{IVB}_{\text{Fastball}} - \text{IVB}_{\text{Breaking}}$). |
| `home_starter_spin_rate_rpm`, `away_starter_spin_rate_rpm` | `numeric` | Average breaking pitch release spin rate (RPM). |
| `home_starter_shadow_pct`, `away_starter_shadow_pct` | `numeric` | Percentage of pitches hitting the 3.3-inch strike zone shadow border. |
| `home_starter_heart_pct`, `away_starter_heart_pct` | `numeric` | Percentage of pitches thrown into the middle-middle heart zone. |
| `home_starter_waste_pct`, `away_starter_waste_pct` | `numeric` | Percentage of non-competitive waste pitches. |

### 2.5 Bullpen & Relief Unit Metrics
| Column Name | Type | Formula / Origin |
|---|---|---|
| `home_bullpen_fip`, `away_bullpen_fip` | `numeric` | Rolling 14-day relief unit FIP. |
| `home_bullpen_xfip`, `away_bullpen_xfip` | `numeric` | Rolling 14-day relief unit xFIP. |
| `home_bullpen_siera`, `away_bullpen_siera` | `numeric` | Rolling 14-day relief unit SIERA. |
| `home_bullpen_csw_pct`, `away_bullpen_csw_pct` | `numeric` | Rolling 14-day relief unit CSW%. |
| `home_bullpen_whiff_pct`, `away_bullpen_whiff_pct` | `numeric` | Rolling 14-day relief unit Whiff%. |
| `home_bullpen_xwoba`, `away_bullpen_xwoba` | `numeric` | Rolling 14-day relief unit xwOBA allowed. |
| `home_bullpen_vert_separation_in`, `away_bullpen_vert_separation_in` | `numeric` | Rolling bullpen vertical movement separation (inches). |

### 2.6 Baserunning & Catcher Framing
| Column Name | Type | Formula / Origin |
|---|---|---|
| `home_bsr_total`, `away_bsr_total` | `numeric` | Total Baserunning Runs ($\text{wSB} + \text{UBR}$). |
| `home_catcher_csae_pct`, `away_catcher_csae_pct` | `numeric` | Catcher Called Strike Above Expected in shadow zone. |
| `home_catcher_framing_runs`, `away_catcher_framing_runs` | `numeric` | Net runs saved via pitch framing ($\text{CSAE} \times 0.125$). |

### 2.7 Symmetric Matchup Difference Vectors ($\Delta = \text{Home} - \text{Away}$)
| Column Name | Type | Parity Formula |
|---|---|---|
| `starter_siera_diff` | `numeric` | `home_starter_siera - away_starter_siera` |
| `starter_xfip_diff` | `numeric` | `home_starter_xfip - away_starter_xfip` |
| `starter_csw_diff` | `numeric` | `home_starter_csw_pct - away_starter_csw_pct` |
| `starter_whiff_diff` | `numeric` | `home_starter_whiff_pct - away_starter_whiff_pct` |
| `starter_xwoba_diff` | `numeric` | `home_starter_xwoba - away_starter_xwoba` |
| `starter_fastball_velo_diff` | `numeric` | `home_starter_fastball_velo - away_starter_fastball_velo` |
| `starter_vert_sep_diff` | `numeric` | `home_starter_vert_separation_in - away_starter_vert_separation_in` |
| `bullpen_siera_diff` | `numeric` | `home_bullpen_siera - away_bullpen_siera` |
| `bullpen_xfip_diff` | `numeric` | `home_bullpen_xfip - away_bullpen_xfip` |
| `bullpen_csw_diff` | `numeric` | `home_bullpen_csw_pct - away_bullpen_csw_pct` |
| `bullpen_whiff_diff` | `numeric` | `home_bullpen_whiff_pct - away_bullpen_whiff_pct` |
| `bullpen_xwoba_diff` | `numeric` | `home_bullpen_xwoba - away_bullpen_xwoba` |
| `offense_hard_hit_diff` | `numeric` | `home_offense_hard_hit_pct - away_offense_hard_hit_pct` |
| `offense_barrel_diff` | `numeric` | `home_offense_barrel_pct - away_offense_barrel_pct` |
| `offense_xwoba_diff` | `numeric` | `home_offense_xwoba - away_offense_xwoba` |
| `bsr_total_diff` | `numeric` | `home_bsr_total - away_bsr_total` |
| `catcher_framing_diff` | `numeric` | `home_catcher_framing_runs - away_catcher_framing_runs` |

---

## 3. Raw Data Landing Tables (`raw.*`)

- **`raw.statcast_pitch`**: Every tracked pitch in Statcast era (pitch type, velocity, spin rate, release coordinates, `pfx_x`, `pfx_z`, plate coordinates, zone 1-14, exit velocity, launch angle, hit distance, xBA, xwOBA).
- **`raw.statcast_pitcher_arsenal_stat`**: Pitcher pitch-type repertoire (usage%, run value/100, wOBA against, whiff%).
- **`raw.statcast_batter_arsenal`**: Batter performance vs specific pitch types (pitches seen, run value/100, wOBA, whiff%).
- **`raw.retrosheet_event`**: Play-by-play events from 1910-2025 (pre-outs, post-outs, runners on base, runner destination codes, event codes).
- **`raw.retrosheet_gameinfo`**: Game metadata, official box scores, starting pitchers, attendance, game times, umpires.
- **`raw.odds_historical`**: Time-stamped sportsbook market odds, moneylines, run lines, totals, and closing lines.

---

## 4. Serving Marts (`serve.*`)

- **`serve.daily_betting_grid`**: Live and historical games with starting pitchers, market consensus odds, model predicted win probability, fair price, and $+EV$ edge.
- **`serve.pitcher_card`**: Comprehensive pitcher profile (SIERA, xFIP, CSW%, IVB, Curve Drop, Vertical Separation, 4-tier attack zone breakdown).
- **`serve.matchup_preview`**: Complete head-to-head comparison table showing all 17 symmetric difference terms.

---

## 5. Core Relational Tables (`core.*`)

- **`core.market`**: One matched Polymarket/Kalshi market row per game/side (`game_id`, `source`, `market_ref`, `team_id`), matched to `core.game` by `conform.py`.
  - `implied_probability numeric` — nullable. The market-implied win probability for `team_id`, taken from the latest `raw.{polymarket,kalshi}_snapshot` row captured strictly before the game's real start time; NULL when no pre-game snapshot exists. Never the settled/current price (ADR-052).
  - `observed_at timestamptz` — nullable. The `captured_at` of the `raw.{polymarket,kalshi}_snapshot` row that `implied_probability` was resolved from; the pre-game moment that price was observed. NULL exactly when `implied_probability` is NULL (issue #107).
