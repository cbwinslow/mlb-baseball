# Statcast Raw Schema Guide

## Strategy

Statcast raw ingestion is CSV-family-based. The raw layer should closely mirror the Statcast Search CSV export column structure, because that export is the most stable and complete field reference. Add typed normalization only where necessary for ingestion robustness. Track query parameters with each load batch.

## Raw table families

### raw_statcast_pitches

One row per pitch from Statcast Search CSV export.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| pitch_type | text | Pitch type code (FF, SL, CH, etc.) |
| pitch_name | text | Full pitch name |
| game_date | date | Game date |
| game_pk | bigint | MLB game primary key |
| game_year | integer | Season year |
| game_type | text | Game type (R/F/D/L/W/S) |
| at_bat_number | integer | At-bat number within game |
| pitch_number | integer | Pitch number within at-bat |
| inning | integer | Inning number |
| inning_topbot | text | Top or Bot |
| batter | integer | MLB batter player ID |
| pitcher | integer | MLB pitcher player ID |
| player_name | text | Pitcher name |
| stand | text | Batter stance (L/R) |
| p_throws | text | Pitcher hand (L/R) |
| home_team | text | Home team abbreviation |
| away_team | text | Away team abbreviation |
| balls | integer | Ball count |
| strikes | integer | Strike count |
| outs_when_up | integer | Outs when batter came up |
| on_1b | integer | Runner on first player ID |
| on_2b | integer | Runner on second player ID |
| on_3b | integer | Runner on third player ID |
| events | text | Plate appearance outcome |
| description | text | Pitch outcome description |
| type | text | Pitch category (S/B/X) |
| zone | integer | Strike zone region (1-14) |
| bb_type | text | Batted ball type |
| hit_location | integer | Fielder position for BIP |
| des | text | Play description text |
| release_speed | numeric | Velocity at release (mph) |
| release_pos_x | numeric | Horizontal release position (ft) |
| release_pos_y | numeric | Release depth (ft) |
| release_pos_z | numeric | Vertical release position (ft) |
| release_spin_rate | numeric | Spin rate (rpm) |
| release_extension | numeric | Release extension (ft) |
| spin_axis | numeric | Spin axis degrees (Hawk-Eye) |
| pfx_x | numeric | Horizontal movement (ft) |
| pfx_z | numeric | Vertical movement (ft) |
| plate_x | numeric | Horizontal plate position (ft) |
| plate_z | numeric | Vertical plate position (ft) |
| sz_top | numeric | Strike zone top |
| sz_bot | numeric | Strike zone bottom |
| vx0 | numeric | X velocity at y=50ft |
| vy0 | numeric | Y velocity at y=50ft |
| vz0 | numeric | Z velocity at y=50ft |
| ax | numeric | X acceleration |
| ay | numeric | Y acceleration |
| az | numeric | Z acceleration |
| effective_speed | numeric | Perceived velocity (mph) |
| launch_speed | numeric | Exit velocity (mph) |
| launch_angle | numeric | Launch angle (degrees) |
| launch_speed_angle | integer | Launch speed/angle combined code |
| hit_distance_sc | numeric | Projected hit distance (ft) |
| hc_x | numeric | Hit coordinate X |
| hc_y | numeric | Hit coordinate Y |
| estimated_ba_using_speedangle | numeric | xBA |
| estimated_woba_using_speedangle | numeric | xwOBA |
| woba_value | numeric | wOBA value of outcome |
| woba_denom | integer | wOBA denominator |
| babip_value | integer | BABIP value |
| iso_value | integer | ISO value |
| delta_home_win_exp | numeric | Win expectancy change |
| delta_run_exp | numeric | Run expectancy change |
| bat_score | integer | Batting team score |
| fld_score | integer | Fielding team score |
| post_bat_score | integer | Batting team score after play |
| post_fld_score | integer | Fielding team score after play |
| home_score | integer | Home team score |
| away_score | integer | Away team score |
| post_home_score | integer | Home team score after play |
| post_away_score | integer | Away team score after play |
| if_fielding_alignment | text | Infield alignment |
| of_fielding_alignment | text | Outfield alignment |
| sv_id | text | Savant video identifier |
| fielder_2 | integer | Catcher player ID |
| fielder_3 | integer | 1B player ID |
| fielder_4 | integer | 2B player ID |
| fielder_5 | integer | 3B player ID |
| fielder_6 | integer | SS player ID |
| fielder_7 | integer | LF player ID |
| fielder_8 | integer | CF player ID |
| fielder_9 | integer | RF player ID |
| spin_dir | numeric | Spin direction (deprecated) |
| spin_rate_deprecated | numeric | Deprecated spin rate |
| break_angle_deprecated | numeric | Deprecated break angle |
| break_length_deprecated | numeric | Deprecated break length |
| tfs_deprecated | text | Deprecated time field |
| tfs_zulu_deprecated | text | Deprecated time field UTC |
| retrieved_at | timestamptz | Load timestamp |

### raw_statcast_sprint_speed

One row per player per season from sprint speed leaderboard.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| player_id | integer | MLB player ID |
| player_name | text | Player name |
| season | integer | Season year |
| sprint_speed | numeric | Sprint speed (ft/sec) |
| attempts | integer | Sprint attempts |
| competitive_runs | integer | Competitive runs |
| percent_rank | numeric | Percentile rank |
| retrieved_at | timestamptz | Load timestamp |

### raw_statcast_outs_above_average

One row per player per position per season from OAA leaderboard.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| player_id | integer | MLB player ID |
| player_name | text | Player name |
| season | integer | Season year |
| position | text | Fielding position |
| oaa | integer | Outs above average |
| runs_saved | integer | Estimated runs saved |
| attempts | integer | Fielding attempts |
| retrieved_at | timestamptz | Load timestamp |

### raw_statcast_expected_stats

One row per player per season from expected stats leaderboard.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| player_id | integer | MLB player ID |
| player_name | text | Player name |
| year | integer | Season year |
| pa | integer | Plate appearances |
| bip | integer | Balls in play |
| ba | numeric | Batting average |
| xba | numeric | Expected batting average |
| slg | numeric | Slugging percentage |
| xslg | numeric | Expected slugging |
| woba | numeric | wOBA |
| xwoba | numeric | Expected wOBA |
| xobp | numeric | Expected OBP |
| xiso | numeric | Expected ISO |
| wobadiff | numeric | wOBA minus xwOBA |
| xbadiff | numeric | BA minus xBA |
| retrieved_at | timestamptz | Load timestamp |

### raw_statcast_load_batches

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Unique batch identifier |
| data_family | text | pitches / sprint_speed / oaa / expected_stats |
| query_start_date | date | Query start date |
| query_end_date | date | Query end date |
| player_type | text | batter / pitcher (for pitch queries) |
| rows_loaded | integer | Rows inserted |
| loaded_at | timestamptz | Load timestamp |
| status | text | success / failed / partial |
| error_message | text | Error detail if failed |

## Load strategy

- Load pitch data directly from CSV export fields without transformation.
- Preserve all deprecated fields in raw table; do not drop them.
- Index on game_pk, batter, pitcher, and game_date after load.
- Partition by game_year for the pitches table.
- Track query parameters per batch including start/end dates and player type.
