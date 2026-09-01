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

## 3. Grain-Complete Statistic Backbone (`gold.batting_game`, …)

The complement to `gold.game_feature`: where `game_feature` is *what was
knowable before a game*, the backbone is *what actually happened*, at every
grain a sabermetric researcher expects (game → season → career; player and
team). Built by `mlb report` from `raw.retrosheet_event`, matching the
event-flag handling of the already-tied-out team stats
(`sql/team_woba_retrosheet_update.sql`, ADR-034). See
[`superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md`](superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md)
for the staged plan.

### 3.1 `gold.batting_game`

- **Grain**: one batting box-score line per `(game_id, player_id, team_id)`,
  regular season only. `team_id` is in the key (not an inferred attribute) so
  the rare case of a player appearing for both clubs in one `game_id` (a
  suspended game resumed after a trade) gets two rows instead of colliding.
- **Temporal semantics**: the actual game result — not point-in-time.
- **Coverage**: 1910–2025 (Retrosheet events). 2026+ and postseason are
  separate follow-up builders.
- **Counting stats only** — rate stats (AVG/OBP/SLG/…) live in the season and
  career roll-ups where the denominators are meaningful.

| Column | Type | Definition |
|---|---|---|
| `game_id`, `player_id`, `team_id` | `bigint` | FKs to `core.game` / `core.player` / `core.team` |
| `season`, `game_date` | `integer`, `date` | From `core.game` |
| `pa` | `integer` | Plate appearances (`bat_event_fl = 'T'`) |
| `ab` | `integer` | At bats (`ab_fl = 'T'`) |
| `r` | `integer` | Runs scored by this player, as batter or baserunner |
| `h`, `b1`, `b2`, `b3`, `hr` | `integer` | Hits and hit types (`event_cd` 20/21/22/23) |
| `tb` | `integer` | Total bases (`b1 + 2·b2 + 3·b3 + 4·hr`) |
| `rbi` | `integer` | Runs batted in (`sum(rbi_ct)`) |
| `bb`, `ibb` | `integer` | Walks (`event_cd` 14–15); intentional (`15`) |
| `hbp` | `integer` | Hit by pitch (`event_cd` 16) |
| `sf`, `sh` | `integer` | Sacrifice flies (`sf_fl`); sac bunts (`sh_fl`) |
| `so` | `integer` | Strikeouts (`event_cd` 3) |
| `gidp` | `integer` | Grounded into DP (`dp_fl = 'T'` and grounder). Undercounts pre-1988 (sparse `battedball_cd`). |
| `source` | `text` | Origin of the row — `retrosheet_event` today |
| `_built_at` | `timestamptz` | When `mlb report` last rebuilt this row |

### 3.2 `gold.pitching_game`

- **Grain**: one pitching box-score line per `(game_id, player_id, team_id)`,
  regular season only (same key rationale as `gold.batting_game` above). A
  two-way player also gets a `gold.batting_game` row.
- **Temporal semantics**: the actual game result — not point-in-time.
- **Coverage**: 1910–2025 (Retrosheet events). 2026+ and postseason are
  separate follow-up builders.
- **`er` / `era` are not produced** — earned runs need reconstructed-inning
  logic that cwevent does not emit. `r` (total runs allowed) and season RA9
  are the honest event-derived figures; ERA is per-player-season from
  Baseball-Reference (`gold.player_season`).

| Column | Type | Definition |
|---|---|---|
| `game_id`, `player_id`, `team_id` | `bigint` | FKs to `core.game` / `core.player` / `core.team` |
| `season`, `game_date` | `integer`, `date` | From `core.game` |
| `gs` | `integer` | 1 if this pitcher started the game |
| `bf` | `integer` | Batters faced (`bat_event_fl = 'T'`, this pitcher charged via `resp_pit_id`) |
| `outs` | `integer` | Outs recorded (`sum(event_outs_ct)`); IP = `outs / 3.0` |
| `h`, `hr` | `integer` | Hits / home runs allowed (`event_cd` 20–23 / 23) |
| `r` | `integer` | Runs allowed — charged per responsible pitcher (`resp_pit_id` for the batter-runner, `run{1,2,3}_resp_pit_id` for inherited runners) |
| `bb`, `ibb` | `integer` | Walks allowed (`event_cd` 14–15); intentional (`15`) |
| `so` | `integer` | Strikeouts (`event_cd` 3) |
| `hbp` | `integer` | Hit batters (`event_cd` 16) |
| `wp` | `integer` | Wild pitches (`wp_fl = 'T'`) |
| `bk` | `integer` | Balks (`event_cd` 11) |
| `w`, `l`, `sv` | `integer` | Win / loss / save from `core.game.{winning,losing,save}_pitcher_id` |
| `source` | `text` | Origin of the row — `retrosheet_event` today |
| `_built_at` | `timestamptz` | When `mlb report` last rebuilt this row |

### 3.3 `gold.batting_season`

- **Grain**: one `is_combined = false` stint row per `(player_id, season,
  team_id)`, plus one `is_combined = true` combined row per `(player_id,
  season)` with `team_id` NULL. For a one-team player the combined row
  equals the single stint, so `WHERE is_combined` always yields exactly one
  full-season line per player. Matches Baseball-Reference's per-team lines +
  "2TM"/"3TM" combined line.
- **Source**: rolled up from `gold.batting_game` by `mlb report`.
- **Temporal semantics**: the actual season result — not point-in-time.
- **Coverage**: 1910–2025, regular season (inherits `gold.batting_game`).
- Counting stats are plain sums. Rate stats are computed from this grain's
  summed components — a season AVG is total H / total AB, never the mean of
  game AVGs. Every rate is NULL when its denominator is 0.
- **SB / CS / SB% absent**: `gold.batting_game` has no steals (baserunning,
  deferred to a later `gold.baserunning_game`).

| Column | Type | Definition |
|---|---|---|
| `id` | `bigserial` | Surrogate primary key |
| `player_id`, `season` | `bigint`, `integer` | Player + season |
| `team_id` | `bigint` | FK `core.team`; NULL iff `is_combined` |
| `is_combined` | `boolean` | `true` = the all-teams full-season line |
| `g` | `integer` | Games played (distinct `game_id`) |
| `pa`, `ab`, `r`, `h`, `b1`, `b2`, `b3`, `hr`, `tb`, `rbi`, `bb`, `ibb`, `hbp`, `sf`, `sh`, `so`, `gidp` | `integer` | Summed counting stats |
| `avg` | `numeric` | H / AB |
| `obp` | `numeric` | (H + BB + HBP) / (AB + BB + HBP + SF) |
| `slg` | `numeric` | TB / AB |
| `ops` | `numeric` | OBP + SLG |
| `iso` | `numeric` | SLG − AVG = (TB − H) / AB |
| `babip` | `numeric` | (H − HR) / (AB − SO − HR + SF) |
| `bb_pct` | `numeric` | BB / PA |
| `k_pct` | `numeric` | SO / PA |
| `source` | `text` | `retrosheet_event` today |
| `_built_at` | `timestamptz` | When `mlb report` last rebuilt this row |

### 3.4 `gold.batting_team`

- **Grain**: one row per `(team_id, season)`, rolled up from
  `gold.batting_game`. Same columns and rate-stat definitions as
  `gold.batting_season` (minus `player_id` / `is_combined`); primary key is
  `(team_id, season)`.
- **Coverage**: 1910–2025, regular season.

---

## 4. Raw Data Landing Tables (`raw.*`)

- **`raw.statcast_pitch`**: Every tracked pitch in Statcast era (pitch type, velocity, spin rate, release coordinates, `pfx_x`, `pfx_z`, plate coordinates, zone 1-14, exit velocity, launch angle, hit distance, xBA, xwOBA).
- **`raw.statcast_pitcher_arsenal_stat`**: Pitcher pitch-type repertoire (usage%, run value/100, wOBA against, whiff%).
- **`raw.statcast_batter_arsenal`**: Batter performance vs specific pitch types (pitches seen, run value/100, wOBA, whiff%).
- **`raw.retrosheet_event`**: Play-by-play events from 1910-2025 (pre-outs, post-outs, runners on base, runner destination codes, event codes).
- **`raw.retrosheet_gameinfo`**: Game metadata, official box scores, starting pitchers, attendance, game times, umpires.
- **`raw.odds_historical`**: Time-stamped sportsbook market odds, moneylines, run lines, totals, and closing lines.

---

## 5. Serving Marts (`serve.*`)

- **`serve.daily_betting_grid`**: Live and historical games with starting pitchers, market consensus odds, model predicted win probability, fair price, and $+EV$ edge.
- **`serve.pitcher_card`**: Comprehensive pitcher profile (SIERA, xFIP, CSW%, IVB, Curve Drop, Vertical Separation, 4-tier attack zone breakdown).
- **`serve.matchup_preview`**: Complete head-to-head comparison table showing all 17 symmetric difference terms.

---

## 6. Core Relational Tables (`core.*`)

Catalogued as the tables this repo's changes have needed documented; not yet an exhaustive `core.*` listing.

- **`core.market`**: One matched Polymarket/Kalshi market row per game/side (`game_id`, `source`, `market_ref`, `team_id`), matched to `core.game` by `conform.py`.
  - `implied_probability numeric` — nullable. The market-implied win probability for `team_id`, taken from the latest `raw.{polymarket,kalshi}_snapshot` row captured strictly before the game's real start time; NULL when no pre-game snapshot exists. Never the settled/current price (ADR-052).
  - `observed_at timestamptz` — nullable. The `captured_at` of the `raw.{polymarket,kalshi}_snapshot` row that `implied_probability` was resolved from; the pre-game moment that price was observed. NULL exactly when `implied_probability` is NULL (issue #107).
