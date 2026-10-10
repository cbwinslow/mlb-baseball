# Core coverage plan (task 6.1) — DRAFT, owner to confirm

Rule (ADR-305): carry every measured raw field into `core` at the finest grain; exact
cross-source duplicates stay in `raw` as tie-out checks. Counts are 2026-10-10 estimates.
`conform` reads 30 of 150 raw tables today. Left out entirely: `news`.

| Group | Raw tables | Core grain | In core today | Tie-out partner |
| --- | --- | --- | --- | --- |
| Pitch detail | `statcast_pitch` (122 cols, 13.6M) | pitch | 19 cols | MLB play-by-play pitch counts |
| Play detail | `retrosheet_event` (168), `retrosheet_plays` (179), `mlb_playbyplay` (22), `mlb_win_prob` (12.6M) | plate appearance / event | 19 cols | box-score totals |
| Game context | `retrosheet_gameinfo`, `retrosheet_game`, `mlb_game_context`, `mlb_game_pace`, `mlb_linescore`, `mlb_live_game`, `mlb_attendance`, `mlb_probable` | game | partial | schedule, gamelog |
| Box scores, lineups | `retrosheet_batting/pitching/fielding`, `retrosheet_box_*`, `mlb_boxscore_*`, `mlb_roster` | player-game | no | play roll-up |
| People | `register_people`, `retrosheet_biofile`, `lahman_people`, `mlb_person`, `mlb_draft`, `mlb_alumni`, `lahman_college_playing` | player | partial | cross-ID agreement |
| Officials | `retrosheet_umpire`, `mlb_umpire`, `mlb_umpire_directory`, `mlb_official_scorer`, `statcast_framing` | game-official | no | each other |
| Moves, availability | `mlb_transaction`, `retrosheet_transaction`, `mlb_free_agent`, `mlb_roster` | transaction / roster-day | no | each other |
| Parks, environment | `fangraphs_park_factors*`, `retrosheet_park`, `lahman_parks`, `mlb_venue` | park-season | venue only | each other |
| Season stats | `fangraphs_batting/pitching/fielding`, both split tables, `bref_batting/pitching`, `lahman_batting/pitching/fielding` | player-season (+splits) | WAR only | play/box roll-up |
| Tracking, skill | 17 `statcast_*` summary tables | player-season | no | `statcast_pitch` roll-up |
| Normalizers (gold) | `fangraphs_guts`, `bref_war_*`, `lahman_teams` | league-year, replacement level | partial | published values |
| Forecasts | `fangraphs_projection`, `fangraphs_prospects` | player-season (as-of date) | no | outcomes |
| Pay, honors, staff | `lahman_salaries`, `lahman_awards_*`, `lahman_hall_of_fame`, `lahman_managers`, `mlb_coach`, `retrosheet_manager` | player/team-season | no | each other |
| Team history | `mlb_team_history`, `lahman_teams*`, `retrosheet_team`, `mlb_sport/league/division/conference` (20/15/6/2 rows, loaded) | team-season league/division | franchise only | each other |
| Markets | `kalshi_*`, `polymarket_*` (price history 604M + 213M rows unused) | market, price at a time | thin | settlement results |

Market types seen (design target, not a limit): winner, spread, total, first-5, first-inning
run, extra innings, per-inning winner, player hits/HR/total bases/H+R+RBI/strikeouts/outs/
walks/earned runs/stolen bases.

## Review additions (2026-10-10)

Checked every raw table name against the table above; these were missing or only implied.

### Raw tables not yet assigned to a group (add to the groups shown)

- Game/team logs: `retrosheet_teamstats` (113 cols), `retrosheet_gamelog`, `retrosheet_gamelog_post`, `retrosheet_schedule`, `mlb_schedule`, `mlb_standing`, `mlb_season` -> game / team-game / team-season.
- Team and league stats: `mlb_team_stat`, `mlb_team_leader`, `mlb_stat_leader`, `mlb_player_stat`, `lahman_teams_half`, `lahman_home_games` -> team-season / leaderboard.
- Postseason and honors: `lahman_*_post`, `lahman_series_post`, `lahman_allstar_full`, `mlb_award`, `mlb_datacaster` -> game/series/player-season. Postseason and All-Star must be a flag on every game and stat row.
- Player-season detail: `lahman_appearances`, `lahman_fielding*`, `lahman_pitching`, `fangraphs_fielding`, `fangraphs_pitching`, `fangraphs_split_*`, `bref_pitching`.
- People and staff: `mlb_player_pool`, `mlb_personnel`, `lahman_managers_half`, `lahman_schools`, `retrosheet_allplayers`, `retrosheet_relative`, `retrosheet_coach*`, `retrosheet_roster`, `retrosheet_biofile0`, `register_names/links/countries` (the ID crosswalk becomes a first-class `core` table).
- Minor leagues and parks: `mlb_affiliate`, `retrosheet_ballpark`, `retrosheet_team0`.
- Retrosheet `*0` tables look like older copies of the same data; they stay tie-out inputs until compared.

### Gaps that are not raw-table carry-forward

- **Era and rule dimension:** a reference table of rule and environment changes (mound height 1969, DH by league/year, expansions, strike zone, pitch clock 2023, shift limits, ball changes, 2020 short season). Needed for the multi-era research the owner described.
- **Measurement provenance on pitch rows:** `statcast_pitch` starts 2008-03-25. Tracking systems changed over time, so each pitch row records which system and season-era measured it. Missing earlier measurements are NULL.
- **Weather:** only Retrosheet game info (temp, wind, sky, precipitation, field condition) exists; coverage is uneven. A better weather source needs owner approval (no new sources without it).
- **Sportsbook lines:** the only odds sources are Kalshi and Polymarket. Closing lines from sportsbooks would be a stronger market benchmark; needs owner approval.
- **Researcher use:** a per-column data dictionary generated from the database, release snapshots with version stamps so published results can be reproduced, a read-only researcher role, and exports (rights-filtered).
- **Validation visibility:** tie-out results live in `meta`, readable by researchers, so a user can see which numbers are verified.

### Corrections to my earlier statements

- I said the four MLB organization tables were empty. They are not (20/15/6/2 rows); I read stale row estimates.
- I said only `news` was left out. That was wrong: about 50 tables were not named (listed above).
- The "In core today" column is verified only for pitch, play and team; the rest comes from the `conform` read list and must be confirmed in task 6.1.
