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

<!-- --8<-- [start:backbone] -->
The complement to `gold.game_feature`: where `game_feature` is *what was
knowable before a game*, the backbone is *what actually happened*, at every
grain a sabermetric researcher expects (game → season → career; player and
team). Built by `mlb report`. **Game-grain rows are 1910–2025 from
`raw.retrosheet_event`** (matching the event-flag handling of the
already-tied-out team stats, `sql/team_woba_retrosheet_update.sql`, ADR-034)
**and 2026 onward from MLB's own official per-game box score**
(`raw.mlb_boxscore_batting` / `raw.mlb_boxscore_pitching`) — Retrosheet
publishes no event file for the in-progress season (ADR-289). Each game row
carries a `source` marker (`retrosheet_event` / `mlb_boxscore`); the two
builders never write the same `(game, player, team)` key. The season / team /
career roll-ups aggregate the game grain and are source-agnostic.

**Authoritative contract:**
[`openspec/specs/statistic-backbone/spec.md`](https://github.com/cbwinslow/mlb-baseball/blob/main/openspec/specs/statistic-backbone/spec.md)
(grain set, source fidelity, null policy, roll-up direction, validation,
export profile). Staged build plan:
[`docs/superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md`](https://github.com/cbwinslow/mlb-baseball/blob/main/docs/superpowers/specs/2026-09-01-grain-complete-stat-backbone-design.md).

**Two season lines, parallel (ADR-281):** `gold.batting_season` /
`gold.pitching_season` here are the *event-derived* line (Retrosheet, 1910+,
per-team stint rows + a combined line, `ra9` not `era`). `gold.player_season`
/ `gold.team_season` (§ elsewhere) are the *Baseball-Reference / Lahman
"official"* line (2008+, carries `era` and other provider fields). They are
distinct sources for distinct purposes — neither is a view over or a writer
into the other.

**Regular season only.** `gold.player_season`, `gold.team_season`,
`gold.batting_season` / `gold.pitching_season`, and every grain below them
count regular-season games only — including the Game 163 tiebreaker, which
counts as regular season (baseball.computer convention; ADR-283). Postseason
batting and pitching live in their own relations, `gold.batting_postseason` /
`gold.pitching_postseason` (§ 3.10). This is enforced by an `mlb doctor`
envelope check (no season row over 163 games).

**Known limitations:**

- **`gold.player_season` / `gold.team_season` included postseason games for
  2021+ until the `separate-postseason-stats` change (ADR-282) — now RESOLVED.**
  `mlb_baseball/connectors/bref.py` pulls a regular-season-only
  Baseball-Reference window and `raw.bref_*` was re-ingested. If a
  `gold.player_season` row still shows more than 163 games, the re-ingest +
  `mlb report` rebuild has not been run yet.
- **Exact tie-out to Baseball-Reference is not achievable at the career grain
  or for seasons much before 2000.** Retrosheet's event record and
  Baseball-Reference's official record have each absorbed decades of
  independent scoring corrections; they differ by small amounts (typically one
  or two on a counting stat per older season). The tie-out gate
  (`scripts/verify_baseball_reference_tie_out.py`) validates 2008–2025
  field-by-field (2020 COVID season excepted) and carries two cited modern
  cases.
- **2026-onward game rows are MLB's scorer-assigned box-score line, not
  event-derived like 1910–2025.** Baseball-Reference has no page for the
  in-progress season, so correctness is checked against an independent
  reconstruction from `raw.mlb_playbyplay`
  (`scripts/verify_mlb_boxscore_tie_out.py`) rather than against
  Baseball-Reference. A researcher comparing a 2025 season to a 2026 season
  is comparing two different pipelines.
- **`era` coverage cliff.** `gold.pitching_game.er` / `gold.pitching_season`
  and `gold.pitching_career` `era` are NULL through 2025 (the event stream
  carries no earned-run data) and populated from 2026 (MLB's box score
  carries scorer-assigned earned runs). `ra9` is the cross-era rate for every
  year; a naive average of `era` across the 2025/2026 boundary is
  meaningless.

### 3.1 `gold.batting_game`

- **Grain**: one batting box-score line per `(game_id, player_id, team_id)`,
  regular season only. `team_id` is in the key (not an inferred attribute) so
  the rare case of a player appearing for both clubs in one `game_id` (a
  suspended game resumed after a trade) gets two rows instead of colliding.
- **Temporal semantics**: the actual game result — not point-in-time.
- **Coverage**: regular season only. **1910–2025** from `raw.retrosheet_event`
  (`source = 'retrosheet_event'`), **2026 onward** from
  `raw.mlb_boxscore_batting` joined to `core.game` on `game_pk`
  (`source = 'mlb_boxscore'`, `sql/batting_game_mlb_build.sql`). The MLB
  builder maps `pa ← plate_appearances`, `ab ← at_bats`, `b2 ← doubles`,
  `b3 ← triples`, `hr ← home_runs`, `tb ← total_bases`, `bb ← base_on_balls`,
  `so ← strike_outs`, `gidp ← ground_into_double_play`, etc.; `b1 = h − b2 −
  b3 − hr`. ~215 2026 regular-season games have no box score yet (ingest
  freshness — an `mlb doctor` join-coverage check, not a builder defect).
  Postseason batting/pitching lives in `gold.batting_postseason` /
  `gold.pitching_postseason` (§ 3.10).
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
| `gidp` | `integer` | Grounded into DP (`dp_fl = 'T'` and grounder ≤ 2025; `ground_into_double_play` 2026+). Undercounts pre-1988 (sparse `battedball_cd`). |
| `source` | `text` | Which builder wrote the row — `retrosheet_event` (≤ 2025) or `mlb_boxscore` (≥ 2026) |
| `_built_at` | `timestamptz` | When `mlb report` last rebuilt this row |

### 3.2 `gold.pitching_game`

- **Grain**: one pitching box-score line per `(game_id, player_id, team_id)`,
  regular season only (same key rationale as `gold.batting_game` above). A
  two-way player also gets a `gold.batting_game` row.
- **Temporal semantics**: the actual game result — not point-in-time.
- **Coverage**: regular season only. **1910–2025** from `raw.retrosheet_event`
  (`source = 'retrosheet_event'`), **2026 onward** from
  `raw.mlb_boxscore_pitching` (`source = 'mlb_boxscore'`,
  `sql/pitching_game_mlb_build.sql`): `gs ← games_started`, `bf ←
  batters_faced`, `outs ← outs`, `er ← earned_runs`, `hbp ← hit_batsmen`,
  `wp ← wild_pitches`, `bk ← balks`, `w/l/sv ← wins/losses/saves` (the
  per-game decision). Postseason lives in `gold.pitching_postseason` (§ 3.10).
- **`er`**: NULL for 1910–2025 — earned runs need reconstructed-inning logic
  that cwevent does not emit; `r` (total runs allowed) and season RA9 are the
  honest event-derived figures. Populated from 2026 (MLB's scorer-assigned
  `earned_runs`). A documented coverage cliff — see § 3 known limitations.

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
| `w`, `l`, `sv` | `integer` | Win / loss / save — from `core.game.{winning,losing,save}_pitcher_id` (≤ 2025) or the box score's per-game decision (≥ 2026) |
| `er` | `integer` | Earned runs — NULL for 1910–2025 (event stream has none), `earned_runs` from 2026 |
| `source` | `text` | Which builder wrote the row — `retrosheet_event` (≤ 2025) or `mlb_boxscore` (≥ 2026) |
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
- **Coverage**: 1910 onward, regular season (inherits `gold.batting_game`;
  1910–2025 event-derived, 2026+ from the MLB box score).
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
- **Coverage**: 1910 onward, regular season (1910–2025 event-derived, 2026+
  from the MLB box score — inherits the game grain, source-agnostic).

### 3.5 `gold.pitching_season`

- **Grain**: same two-row-kind shape as `gold.batting_season` — a stint row
  per `(player_id, season, team_id)` plus one `is_combined` full-season row
  per `(player_id, season)` (`team_id` NULL). Rolled up from
  `gold.pitching_game` by `mlb report`.
- **Coverage**: 1910 onward, regular season (1910–2025 event-derived, 2026+
  from the MLB box score — inherits the game grain, source-agnostic).
- Counting stats are plain sums; rate stats computed from this grain's
  summed components, NULL when the denominator is 0.
- **`era` coverage cliff** — `era` is NULL through 2025 (`gold.pitching_game`
  carries no `er` for the event era) and populated from 2026 as `er × 27 /
  outs`, but only when every contributing game row has a non-NULL `er`
  (`CASE WHEN count(*) = count(er)` — a season straddling the boundary, which
  no real pitcher-season does, reports NULL rather than a partial sum).
  `ra9` (runs allowed per 9) is the cross-era rate for every year; the
  Baseball-Reference "official" ERA remains available per player-season from
  `gold.player_season`.

| Column | Type | Definition |
|---|---|---|
| `id` | `bigserial` | Surrogate primary key |
| `player_id`, `season` | `bigint`, `integer` | Player + season |
| `team_id` | `bigint` | FK `core.team`; NULL iff `is_combined` |
| `is_combined` | `boolean` | `true` = the all-teams full-season line |
| `g`, `gs` | `integer` | Games pitched (distinct `game_id`); games started |
| `bf`, `outs`, `h`, `r`, `bb`, `ibb`, `so`, `hr`, `hbp`, `wp`, `bk`, `w`, `l`, `sv` | `integer` | Summed counting stats (`IP` = `outs` / 3) |
| `er` | `integer` | Summed earned runs — NULL unless every contributing game row has `er` (so NULL through 2025, populated from 2026) |
| `ra9` | `numeric` | R × 27 / outs — runs allowed per 9 IP, the cross-era rate |
| `era` | `numeric` | ER × 27 / outs — NULL through 2025, populated from 2026 (coverage cliff) |
| `whip` | `numeric` | (H + BB) × 3 / outs |
| `k9`, `bb9`, `hr9` | `numeric` | SO / BB / HR × 27 / outs |
| `k_bb` | `numeric` | SO / BB (NULL when BB = 0) |
| `source` | `text` | `retrosheet_event` / `mlb_boxscore` (per contributing game grain) |
| `_built_at` | `timestamptz` | When `mlb report` last rebuilt this row |

### 3.6 `gold.pitching_team`

- **Grain**: one row per `(team_id, season)`, rolled up from
  `gold.pitching_game`. Same columns and rate definitions as
  `gold.pitching_season` (minus `player_id` / `is_combined`), **except `er` /
  `era` are not carried at the team grain** — `ra9` is the team run rate for
  every year; primary key `(team_id, season)`.
- **Coverage**: 1910 onward, regular season (1910–2025 event-derived, 2026+
  from the MLB box score — inherits the game grain, source-agnostic).

### 3.7 `gold.batting_career` / `gold.pitching_career`

- **Grain**: one row per `(player_id)`, summed from each player's per-season
  combined rows (`is_combined = true`) in `gold.batting_season` /
  `gold.pitching_season` — so a traded season is counted once, not per
  stint.
- Extra columns: `seasons` (distinct seasons played), `first_season`,
  `last_season`. All other counting and rate columns match the
  corresponding season table; rate stats are recomputed from the
  career-total components. `gold.pitching_career` carries `ra9` for every
  career; its `er` / `era` follow the same coverage cliff as
  `gold.pitching_season` — `era` exists only for a wholly-2026+ career (NULL
  unless every contributing season has a non-NULL `er`).
- **Coverage**: 1910 onward, regular season (1910–2025 event-derived, 2026+
  from the MLB box score — inherits the game grain, source-agnostic).

### 3.10 `gold.batting_postseason` / `gold.pitching_postseason`

- **Purpose**: postseason batting and pitching totals, kept entirely separate
  from the regular-season backbone above (ADR-282 / ADR-283). Built by
  `mlb report` from **Lahman's own `BattingPost` / `PitchingPost`**
  (`raw.lahman_batting_post` / `raw.lahman_pitching_post`, 1884+) — the direct
  parallel to how `gold.player_season` is built from Lahman. Player ids conform
  via `core.player.bbref_id` (Lahman `playerID` is the Baseball-Reference id),
  falling back to `raw.lahman_people.retroid` → `core.player.retro_id`
  (~99.9% resolve); team ids via `raw.lahman_teams`.
- **Grain**: one table per stat type, three row kinds:
  - **per-round** — `is_combined = false`, `is_career = false`: one per
    `(player_id, season, round, team_id)`. `round` is Lahman's raw value
    (`WS`, `ALCS`, `NLDS1`, `ALWC4`, `NWS` for a Negro League series, …).
  - **combined** — `is_combined = true`: one per `(player_id, season)`, all
    that year's rounds summed; `round` and `team_id` NULL.
  - **career** — `is_career = true`: one per `(player_id)`, every postseason
    season summed; `season`, `round`, `team_id` NULL.
- **Columns** mirror `gold.batting_season` / `gold.pitching_season` (counting
  stats are plain sums, rate stats recomputed at each grain) plus `sb` / `cs`
  on the batting side. `gold.pitching_postseason` has a **real `era`** (Lahman
  `PitchingPost` carries earned runs, unlike the event-derived
  `gold.pitching_season`), alongside `ra9`.
- **Never contains a regular-season game** — the entire source is postseason.
  An `mlb doctor` check verifies every `round` is a recognised postseason round.
- **No postseason team-total relation** yet — it is a `GROUP BY` over the
  combined rows and a noted follow-up (Lahman and baseball.computer both ship
  only player-grain postseason data).
- **Coverage**: 1884–2025.
<!-- --8<-- [end:backbone] -->

### 3.11 `gold.fangraphs_guts` / `gold.fangraphs_park_factors` — FanGraphs reference lookups

> **`local_research` only (FanGraphs, ADR-288 / ADR-290).** Never `public_safe`,
> never in the published `mlb-research` dataset, never a reference-baseline-model
> input. `gold.fangraphs_guts` is a **cross-check / reference**: a publishable
> wOBA / FIP / park-factor is computed from `core.play`, not from these. A
> standing test guards the export registry.

- **Purpose**: two reference lookups conformed from the (shipped-in-#173, ADR-288)
  `raw.fangraphs_*` landing tables. Built by `mlb report`
  (`report._build_backbone_relation`, truncate-and-replace, idempotent); each
  skips cleanly on a database that never ingested FanGraphs. This is
  **fangraphs-conform Beat 1** — projections (`feat.fangraphs_projection`) and
  the full WAR / wOBA / wRC+ / Stuff+ season-line conform are deferred.
- **`gold.fangraphs_guts`**
  - **Grain**: one row per `season` (`season` PK).
  - **Columns**: FanGraphs' Guts! per-season linear-weight constants —
    `woba`, `wobascale`, `wbb`, `whbp`, `w1b`, `w2b`, `w3b`, `whr`, `runsb`,
    `runcs`, `r_pa`, `r_w`, `cfip`, all `numeric`.
  - **Null policy**: source text cast to numeric **verbatim**; no re-derivation,
    no interpolation of missing seasons; an empty source value → `NULL`.
  - **Source**: `raw.fangraphs_guts` (full history 1871+). `mlb doctor` checks
    every `gold.batting_season` season ≥ 2003 has a row.
- **`gold.fangraphs_park_factors`**
  - **Grain**: one row per `(season, team_id)` (composite PK), **`season >= 2003`**
    (pre-2003 park factors are low value with an unstable franchise set and stay
    in `raw`).
  - **Columns**: `basic_5yr`, `pf_3yr`, `pf_1yr` (basic factors) and
    `pf_1b`, `pf_2b`, `pf_3b`, `pf_hr`, `pf_so`, `pf_bb`, `pf_gb`, `pf_fb`,
    `pf_ld`, `pf_iffb`, `pf_fip` (component factors), all `numeric`, kept as
    FanGraphs publishes them.
  - **Identity / null policy**: `raw.fangraphs_park_factors.team` is a FanGraphs
    nickname, resolved to `core.team` through the `'fangraphs'` source block in
    `core.team_alias` (34 aliases; CLE / TBA / WAS carry multiple
    historically-accurate nicknames). A nickname with **no** alias produces **no
    row** and is surfaced by an `mlb doctor` join-coverage check — never a null
    or guessed team.

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

- **`core.player`**: One resolved person per `id`, built by `conform.py` `_build_players` from the Chadwick Bureau Register (`raw.register_people`). Provider IDs (`retro_id`, `mlbam_id`, `bbref_id`, `fangraphs_id`, `chadwick_uuid`) are alternate anchors. A person is admitted when they have a Retrosheet id **or** they have an MLBAM id and appear in MLB's own game record (`raw.mlb_boxscore_batting` / `_pitching` / `raw.mlb_playbyplay`) — the second rule (migration 0103) admits current-season debuts and call-ups; it deliberately excludes the ~100k register people who carry only an MLBAM id and never played an MLB game.
  - `retro_id text` — nullable, UNIQUE across its non-NULL values. NULL for a current-season player admitted on their MLBAM id before Retrosheet has processed that season (Retrosheet assigns `key_retro` months after a season ends). It backfills on the next full `mlb conform` run once `raw.register_people` carries the real id — `core.player` is a truncate-and-rebuild every run, so there is no upsert. Every regular-season game participant resolves to a `core.player` row (`mlb doctor` check `core.player regular-season resolution`, tolerance 0).
- **`core.market`**: One matched Polymarket/Kalshi market row per game/side (`game_id`, `source`, `market_ref`, `team_id`), matched to `core.game` by `conform.py`.
  - `implied_probability numeric` — nullable. The market-implied win probability for `team_id`, taken from the latest `raw.{polymarket,kalshi}_snapshot` row captured strictly before the game's real start time; NULL when no pre-game snapshot exists. Never the settled/current price (ADR-052).
  - `observed_at timestamptz` — nullable. The `captured_at` of the `raw.{polymarket,kalshi}_snapshot` row that `implied_probability` was resolved from; the pre-game moment that price was observed. NULL exactly when `implied_probability` is NULL (issue #107).

---

## 7. Point-in-time feature store (`feat.*` — DuckDB, not PostgreSQL)

The feature layer for model building lives in a **local DuckDB file**, not
PostgreSQL — see [ADR-287](DECISIONS.md) and
[FEATURE_STORE.md](FEATURE_STORE.md). `mlb build` writes it; models read it
through `mlb_research.get_historical_features`. It is a derived, reproducible
artifact: delete the file and rebuild.

- **`feat.player_form`** / **`feat.pitcher_form`**
  - **Grain**: one row per `(player_id, event_ts, feature_version)` — one row
    per appearance, holding that player's form *entering* that game.
  - **Windows are columns, not rows**: `7d`, `30d`, `std` (season-to-date).
    Every rate ships with its numerator(s) and its exposure (`pa_<w>` / `bf_<w>`)
    so a PA/BF-based window is re-derivable.
  - **Clocks**: `event_ts` (game_date + game_number × 3h — fictional absolute
    time, real doubleheader ordering); `available_ts` = `visible_ts` = `event_ts`
    (the value is entering form, knowable at first pitch); `created_ts` = build
    time (audit only in a full rebuild). The 6h box-score lag lives in the
    rolling-window frame, not the row's own clock.
  - **Batting**: `k_pct`, `bb_pct`, `obp`, `slg`, `iso`, `babip` per window
    (NULL when the denominator is 0), plus EB-shrunk `k_pct_shrunk` /
    `bb_pct_shrunk`. **Pitching**: `k_pct`, `bb_pct`, `k_minus_bb_pct`, `ra9`,
    `fip_like` per window, plus the two shrunk rates.
  - **Coverage**: regular season, 1910–2025 (Retrosheet events).
- **`feat.game`**
  - **Grain**: one row per `(game_pk, feature_version)` — the curated wide
    assembly the first notebook and Elo v2 load.
  - Game context + the four clocks + home/away team entering offensive form
    (30d) + both starters' entering form (30d) + the `home_win` label. ~26
    columns. `starter_is_actual = TRUE` in slice 1 (the actual starter, not the
    probable one).
