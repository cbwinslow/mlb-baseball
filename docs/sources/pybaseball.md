# pybaseball function audit

Audited 2026-10-07 against pybaseball 2.2.7 (88 public functions), by reading our code for calls to each function. pybaseball is a client library, not a source: each function scrapes a source we already list (Statcast/Savant, Baseball-Reference, FanGraphs, Lahman, Chadwick). Rights follow the underlying source in [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md). The `mlb coverage --source bref` and `--source statcast` reports say what we hold.

Status: `used` = a project connector calls it; `replaced` = our own connector or file loader holds the same data; `unneeded` = covered by a source we hold (Retrosheet, Lahman, MLB API) or plotting only. "Works today" is claimed only for `used` functions that run in the nightly; nothing else was executed in this audit.

| Group | Functions | Status | Owner / reason |
|---|---|---|---|
| Statcast pitches | `statcast`, `statcast_batter`, `statcast_pitcher`, `statcast_single_game` | `statcast` used (`connectors/statcast.py`); the rest unneeded | the date-range call returns every pitch; per-player and single-game calls are subsets |
| Statcast leaderboards | `statcast_batter_exitvelo_barrels`, `_expected_stats`, `_percentile_ranks`, `_pitch_arsenal`, `statcast_pitcher_*` (same set plus `_arsenal_stats`, `_spin_dir_comp`), `statcast_catcher_framing`, `_poptime`, `statcast_outfield_catch_prob`, `_directional_oaa`, `statcast_outfielder_jump`, `statcast_outs_above_average`, `statcast_running_splits`, `statcast_sprint_speed` | used | `connectors/statcast_leaderboard.py` |
| Baseball-Reference | `batting_stats_bref`, `pitching_stats_bref`, `batting_stats_range`, `pitching_stats_range`, `team_batting_bref`, `team_pitching_bref`, `bwar_bat`, `bwar_pitch`, `get_splits`, `top_prospects` | used | `connectors/bref.py` |
| Baseball-Reference, not called | `team_fielding_bref`, `schedule_and_record`, `season_game_logs`, `team_game_logs`, `all_star_game_logs`, `world_series_logs`, `lcs_logs`, `division_series_logs`, `wild_card_logs`, `series_post`-style logs | unneeded | game logs and postseason series come from Retrosheet (event data to 2025) and the MLB schedule; team fielding is derivable from Retrosheet |
| Chadwick / ids | `chadwick_register`, `playerid_lookup`, `playerid_reverse_lookup`, `player_search_list` | `chadwick_register` used (`connectors/chadwick_register.py`); lookups replaced | we load the whole register file; per-name lookups are not needed |
| Lahman | `download_lahman`, `people`, `master`, `batting`, `pitching`, `fielding`, `appearances`, `managers`, `parks`, `teams_core`, `teams_franchises`, `salaries`, `schools`, `hall_of_fame`, `awards_*`, `all_star_full`, `home_games`, `*_post`, and the rest of the Lahman table readers | replaced | `connectors/lahman.py` loads the Lahman files directly; pybaseball is only a fallback |
| Schedules and standings | `schedules`, `standings` | `schedules` used for the Retrosheet schedule; `standings` unneeded | MLB API holds the schedule and standings (`raw.mlb_schedule`, `raw.mlb_standing`) |
| Misc | `rosters`, `team_ids`, `events`, `fangraphs_teams`, `park_codes`, `teams_half`, `teams_upstream` | unneeded | rosters and teams come from MLB API and Lahman; `events` is a Retrosheet reader |
| Plotting | `plot_stadium`, `plot_strike_zone`, `plot_teams`, `spraychart` | unneeded | charts, no data |

## The four things the owner asked about

| Data | In pybaseball? | Where we get it |
|---|---|---|
| Transactions and trades | no function | `raw.mlb_transaction` from the MLB API (2000 on); `raw.retrosheet_transaction` (frozen 2021-11-26). Trades are transaction rows of type "Trade". |
| Umpires | no function | `raw.mlb_umpire` (MLB API box score `officials`, 2026 on) and Retrosheet umpire data to 2025 |
| Stadium / park factors | `parks` (Lahman park list only) | FanGraphs park factors (`park_factors`, loaded by the FanGraphs connector) and Lahman parks |
| Salaries | `salaries` | Lahman salaries (to the last Lahman release) |

Result: no pybaseball function offers transactions, trades, umpires or park factors that we do not already hold from a better source. Functions marked `unneeded` stay unused unless a coverage gap names one; add a row here when that happens.
