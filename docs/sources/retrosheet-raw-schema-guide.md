# Retrosheet Raw Schema Guide

## Strategy

Retrosheet raw ingestion should be split by source artifact family. Each family maps to a separate raw table or table group. Preserve all source-native identifiers and field names. Do not merge event, game log, roster, and schedule data into a single raw table.

## Raw table families

### raw_retrosheet_events

Derived from BEVENT / Chadwick `cwevent` output. One row per play event.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source .EV* filename |
| game_id | text | Retrosheet game ID (e.g. ANA200304050) |
| away_team_id | text | Away team code |
| inn_ct | integer | Inning number |
| bat_home_id | integer | 0 = away batting, 1 = home batting |
| bat_lineup_id | integer | Batter lineup position (1-9) |
| event_id | integer | Sequential event number within game |
| bat_id | text | Batter Retrosheet player ID |
| pit_id | text | Pitcher Retrosheet player ID |
| base1_run_id | text | Runner on first player ID |
| base2_run_id | text | Runner on second player ID |
| base3_run_id | text | Runner on third player ID |
| event_cd | integer | Event code (see Retrosheet event codes) |
| event_tx | text | Event description text |
| balls_ct | integer | Ball count at event |
| strikes_ct | integer | Strike count at event |
| pitch_seq_tx | text | Pitch sequence string |
| battedball_cd | text | Batted ball type code |
| hit_location | text | Hit location code |
| rbi_ct | integer | RBIs on this play |
| run1_dest_id | integer | Destination base for runner on first |
| run2_dest_id | integer | Destination base for runner on second |
| run3_dest_id | integer | Destination base for runner on third |
| bat_dest_id | integer | Destination base for batter |
| err1_fld_cd | integer | Fielder position for first error |
| err2_fld_cd | integer | Fielder position for second error |
| err3_fld_cd | integer | Fielder position for third error |
| retrieved_at | timestamptz | Load timestamp |

### raw_retrosheet_games

Derived from BGAME / Chadwick `cwgame` output. One row per game.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source .EV* filename |
| game_id | text | Retrosheet game ID |
| date | date | Game date |
| game_number | integer | Doubleheader number (0 = single) |
| away_team_id | text | Away team code |
| home_team_id | text | Home team code |
| park_id | text | Park identifier |
| away_score | integer | Away team final score |
| home_score | integer | Home team final score |
| innings | integer | Innings played |
| wp_id | text | Winning pitcher player ID |
| lp_id | text | Losing pitcher player ID |
| save_id | text | Save pitcher player ID |
| attendance | integer | Game attendance |
| time_of_game | integer | Duration in minutes |
| day_night | text | D = day, N = night |
| retrieved_at | timestamptz | Load timestamp |

### raw_retrosheet_gamelogs

Derived from game log files (.GL). One row per game with full 161-field layout.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source .GL filename |
| date | date | Game date |
| game_number | integer | Doubleheader game number |
| day_of_week | text | Day abbreviation |
| v_team_id | text | Visiting team code |
| v_league | text | Visiting team league |
| v_game_number | integer | Visiting team season game number |
| h_team_id | text | Home team code |
| h_league | text | Home team league |
| h_game_number | integer | Home team season game number |
| v_score | integer | Visiting team score |
| h_score | integer | Home team score |
| length_outs | integer | Game length in outs |
| day_night | text | Day/night indicator |
| completion | text | Completion information if applicable |
| forfeit | text | Forfeit indicator |
| protest | text | Protest indicator |
| park_id | text | Park identifier |
| attendance | integer | Attendance |
| time_of_game | integer | Duration in minutes |
| v_line_score | text | Visiting line score string |
| h_line_score | text | Home line score string |
| v_ab | integer | Visiting at-bats |
| v_h | integer | Visiting hits |
| v_2b | integer | Visiting doubles |
| v_3b | integer | Visiting triples |
| v_hr | integer | Visiting home runs |
| v_rbi | integer | Visiting RBI |
| v_sh | integer | Visiting sacrifice hits |
| v_sf | integer | Visiting sacrifice flies |
| v_hbp | integer | Visiting hit by pitch |
| v_bb | integer | Visiting walks |
| v_ibb | integer | Visiting intentional walks |
| v_so | integer | Visiting strikeouts |
| v_sb | integer | Visiting stolen bases |
| v_cs | integer | Visiting caught stealing |
| v_gidp | integer | Visiting grounded into double play |
| v_ci | integer | Visiting catcher interference |
| v_lob | integer | Visiting left on base |
| v_pitchers_used | integer | Visiting pitchers used |
| v_er | integer | Visiting individual earned runs |
| v_ter | integer | Visiting team earned runs |
| v_wp | integer | Visiting wild pitches |
| v_balks | integer | Visiting balks |
| v_po | integer | Visiting putouts |
| v_a | integer | Visiting assists |
| v_e | integer | Visiting errors |
| v_passed | integer | Visiting passed balls |
| v_dp | integer | Visiting double plays |
| v_tp | integer | Visiting triple plays |
| h_ab | integer | Home at-bats |
| h_h | integer | Home hits |
| h_2b | integer | Home doubles |
| h_3b | integer | Home triples |
| h_hr | integer | Home home runs |
| h_rbi | integer | Home RBI |
| h_sh | integer | Home sacrifice hits |
| h_sf | integer | Home sacrifice flies |
| h_hbp | integer | Home hit by pitch |
| h_bb | integer | Home walks |
| h_ibb | integer | Home intentional walks |
| h_so | integer | Home strikeouts |
| h_sb | integer | Home stolen bases |
| h_cs | integer | Home caught stealing |
| h_gidp | integer | Home grounded into double play |
| h_ci | integer | Home catcher interference |
| h_lob | integer | Home left on base |
| h_pitchers_used | integer | Home pitchers used |
| h_er | integer | Home individual earned runs |
| h_ter | integer | Home team earned runs |
| h_wp | integer | Home wild pitches |
| h_balks | integer | Home balks |
| h_po | integer | Home putouts |
| h_a | integer | Home assists |
| h_e | integer | Home errors |
| h_passed | integer | Home passed balls |
| h_dp | integer | Home double plays |
| h_tp | integer | Home triple plays |
| hp_ump_id | text | Home plate umpire ID |
| hp_ump_name | text | Home plate umpire name |
| b1_ump_id | text | First base umpire ID |
| b1_ump_name | text | First base umpire name |
| b2_ump_id | text | Second base umpire ID |
| b2_ump_name | text | Second base umpire name |
| b3_ump_id | text | Third base umpire ID |
| b3_ump_name | text | Third base umpire name |
| lf_ump_id | text | Left field umpire ID |
| lf_ump_name | text | Left field umpire name |
| rf_ump_id | text | Right field umpire ID |
| rf_ump_name | text | Right field umpire name |
| v_manager_id | text | Visiting manager ID |
| v_manager_name | text | Visiting manager name |
| h_manager_id | text | Home manager ID |
| h_manager_name | text | Home manager name |
| wp_id | text | Winning pitcher ID |
| wp_name | text | Winning pitcher name |
| lp_id | text | Losing pitcher ID |
| lp_name | text | Losing pitcher name |
| save_id | text | Save pitcher ID |
| save_name | text | Save pitcher name |
| gw_rbi_id | text | Game-winning RBI batter ID |
| gw_rbi_name | text | Game-winning RBI batter name |
| retrieved_at | timestamptz | Load timestamp |

### raw_retrosheet_rosters

One row per player per team per season from .ROS files.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source .ROS filename |
| season | integer | Season year |
| player_id | text | Retrosheet player ID |
| last_name | text | Player last name |
| first_name | text | Player first name |
| bats | text | Batting hand (R/L/B) |
| throws | text | Throwing hand (R/L) |
| team_id | text | Team code |
| position | text | Primary position |
| retrieved_at | timestamptz | Load timestamp |

### raw_retrosheet_schedules

One row per scheduled game from .SCH files.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source .SCH filename |
| season | integer | Season year |
| date | date | Scheduled game date |
| game_number | integer | Doubleheader number |
| v_team_id | text | Visiting team code |
| h_team_id | text | Home team code |
| day_of_week | text | Day abbreviation |
| time | text | Scheduled start time |
| retrieved_at | timestamptz | Load timestamp |

### raw_retrosheet_load_batches

Batch metadata table for tracking all Retrosheet ingestion runs.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Unique batch identifier |
| source_family | text | e.g. events, gamelogs, rosters |
| season | integer | Season year |
| source_file | text | Source filename |
| tool_used | text | e.g. cwevent, cwgame, direct |
| tool_version | text | Tool version string |
| rows_loaded | integer | Row count loaded |
| loaded_at | timestamptz | Load timestamp |
| status | text | success / failed / partial |

## Load strategy

- Load raw tables from flat files without transformation.
- Track tool version and source file for every batch.
- Index on game_id and player_id columns after load.
- Do not deduplicate in the raw layer; handle in staging.
- Partition by season year for large event tables.
