# Game-type scope audit (task 1.1)

Every `gold` builder / model aggregation / view that reads game-level data,
and whether it explicitly scopes `game_type` (regular vs postseason vs other).

Method: grep every `mlb_baseball/sql/*.sql` and `mlb_baseball/report.py` /
`mlb_baseball/model/*.py` for reads of `core.game`, `raw.retrosheet_event`,
`raw.retrosheet_gameinfo`, `gold.batting_game` / `gold.pitching_game`,
`gold.game_feature`; verify the scope by reading each hit.

## PASS — explicit regular-season scope, or inherits one

| Relation / file | How it's scoped |
|---|---|
| `gold.batting_game` / `gold.pitching_game` (`{batting,pitching}_game_build.sql`) | `WHERE lower(g.game_type) = 'regular'` on the event read |
| `gold.batting_season` / `_team` / `_career` (`batting_season_build.sql`, `batting_team_build.sql`, career) | roll up from `gold.batting_game` — inherit |
| `gold.pitching_season` / `_team` / `_career` | roll up from `gold.pitching_game` — inherit |
| `gold.game_feature` (`game_feature_rebuild.sql`, legacy rebuilds) | `WHERE ms.game_type = 'R'` / `g.game_type = 'regular'`; verified 100% regular in the DB |
| `report.py` `_build_team_season` | `raw.lahman_teams` is regular-season only; the park-factor / wOBA passes filter `game_type = 'regular'` AND `gi.gametype = 'regular'` |
| `report.py` player-season / team-season health checks | `JOIN core.game ... AND lower(g.game_type) = 'regular'` |
| `win_expectancy_matrix_build.sql` | `JOIN raw.retrosheet_gameinfo gi ON ... AND lower(gi.gametype) = 'regular'` |
| `team_woba_retrosheet_update.sql`, `team_wrc_plus_retrosheet_update.sql`, `team_rate_retrosheet_update.sql`, `team_bsr_retrosheet_update.sql`, `team_bsr_comprehensive_retrosheet_update.sql`, `team_pitch_discipline_retrosheet_update.sql`, `team_pitcher_estimators_retrosheet_update.sql`, `team_bullpen_retrosheet_update.sql`, `team_starter_retrosheet_update.sql`, `starter_workload_retrosheet_update.sql`, `starter_experience_update.sql`, `starter_outs_reconcile.sql`, `starter_strikeouts_reconcile.sql`, `bullpen_outs_reconcile.sql`, `catcher_framing_csae_update.sql`, `statcast_expected_retrosheet_update.sql`, `leverage_index_matrix_build.sql`, `leverage_index_season_partial.sql`, `markov_*` | each carries a `gametype = 'regular'` / `game_type = 'regular'` filter on the event or game read (verified) |
| `team_framing_update.sql`, `team_oaa_update.sql`, `team_speed_update.sql`, `team_war_update.sql`, `platoon_splits_update.sql`, `starter_age_update.sql` | source is a **season-aggregate** Statcast leaderboard (`raw.statcast_framing` / `_oaa` / `_sprint_speed`) or `core.player_war` (from clean `raw.bref_war_*`) — Baseball Savant leaderboards are regular-season by default; joins are to `gold.game_feature` (regular-only). Spot-check the Savant tables during 1.2. |
| `model/total.py`, `model/starter.py`, `model/team_rate.py`, other `model/*.py` | `WHERE game_type = 'regular'` / `gametype = 'regular'` (verified) |

## GAP — reads `raw.retrosheet_event` with no game-type scope → FIX in task 1.2

| File | What it builds | Fix |
|---|---|---|
| `run_expectancy_matrix_build.sql` | `gold.run_expectancy_24` — the leaguewide base-out run-expectancy matrix (feeds RE24 / WPA everywhere) | add a join to `raw.retrosheet_gameinfo` (or `core.game`) with `gametype = 'regular'`; this also excludes All-Star / Negro League / spring plays currently swept in via `_group` |
| `team_leverage_re24_update.sql` | entering-game team RE24 + Leverage Index (`gold.game_feature` columns) | scope the `event_parsed` CTE's `raw.retrosheet_event` read to regular-season games; output rows are already regular-only (final join to `gold.game_feature`), but the `prior_pa` running windows currently accumulate postseason plays |
| `team_batted_ball_retrosheet_update.sql` | entering-game team batted-ball profile rates (`gold.game_feature` columns) | same fix as `team_leverage_re24_update.sql` |

## VERIFY during task 1.2 (likely fine — diagnostics, not builders)

| File | Note |
|---|---|
| `offense_health_check.sql`, `team_bsr_health_check.sql`, `team_rate_health_check.sql` | range-check diagnostics over `gold.game_feature` columns (regular-only); confirm any event-read denominator is also scoped |
| `raw.statcast_framing` / `raw.statcast_oaa` / `raw.statcast_sprint_speed` | confirm pybaseball's Savant leaderboard pull is regular-season only (Savant default) — a quick spot check like the `raw.bref_*` one |

## DB views / SQLMesh

- No materialised view or plain view references `player_season` / `team_season` (checked `pg_class`).
- `transforms/models/park_factor.sql` / `park_factors_weather.sql` reference CTE
  aliases named `team_season_*`, not the gold table; their event/game reads use
  `gametype = 'regular'` (same as the `mlb_baseball/sql` park-factor passes).
  Confirm during 1.2.

## The core contamination (fixed by task 2, not 1.2)

`gold.player_season` / `gold.team_season` season *counting* stats come from
`raw.bref_batting` / `raw.bref_pitching`, which are regular + postseason from
the pybaseball fetch. Not fixable with a `game_type` filter (raw is pre-summed);
fixed by ending the Baseball-Reference query at the regular-season boundary
(task 2) and rebuilding.
