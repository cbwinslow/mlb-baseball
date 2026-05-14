# Statcast / Baseball Savant Source Notes

## Overview

Statcast is MLB's player tracking system, installed in all 30 MLB parks since 2015. It uses high-speed cameras and radar to capture granular ball and player movement data. Baseball Savant (https://baseballsavant.mlb.com) is the public portal for Statcast data and provides a searchable interface with CSV export capability.

- **Website**: https://baseballsavant.mlb.com
- **License**: No formal license; public access
- **Access pattern**: CSV export via Statcast Search; also accessible via pybaseball and similar wrappers
- **Coverage**: 2015 to present for pitch tracking; some metrics available from 2008

## Upstream documentation

| Document | URL |
|----------|-----|
| Statcast Search | https://baseballsavant.mlb.com/statcast_search |
| CSV field documentation | https://baseballsavant.mlb.com/csv-docs |
| pybaseball library | https://github.com/jldbc/pybaseball |
| Baseball Savant leaderboards | https://baseballsavant.mlb.com/leaderboard |

## Available data families

### Pitch-level data (Statcast Search CSV export)

The core Statcast export is pitch-level data from the Statcast Search interface. Each row is one pitch.

#### Pitch identification and game context

| Field | Description |
|-------|-------------|
| pitch_type | Pitch type classification (FF, SL, CH, CU, etc.) |
| game_date | Date of game |
| release_speed | Pitch velocity at release (mph) |
| release_pos_x | Horizontal release position (ft) |
| release_pos_z | Vertical release position (ft) |
| player_name | Pitcher name |
| batter | MLB batter ID |
| pitcher | MLB pitcher ID |
| events | Plate appearance outcome |
| description | Pitch description (called_strike, ball, foul, etc.) |
| spin_dir | Spin direction (deprecated) |
| spin_rate_deprecated | Spin rate deprecated field |
| break_angle_deprecated | Break angle deprecated field |
| break_length_deprecated | Break length deprecated field |
| zone | Strike zone location (1-14) |
| des | Play description text |
| game_type | R/F/D/L/W/S |
| stand | Batter stance (L/R) |
| p_throws | Pitcher hand (L/R) |
| home_team | Home team abbreviation |
| away_team | Away team abbreviation |
| type | Pitch result category (S/B/X) |
| hit_location | Fielder position for ball in play |
| bb_type | Batted ball type (ground_ball, fly_ball, line_drive, popup) |
| balls | Ball count |
| strikes | Strike count |
| game_year | Season year |
| pfx_x | Horizontal movement (ft, catcher perspective) |
| pfx_z | Vertical movement (ft) |
| plate_x | Horizontal position at plate (ft) |
| plate_z | Vertical position at plate (ft) |
| on_3b | Runner on third MLB player ID |
| on_2b | Runner on second MLB player ID |
| on_1b | Runner on first MLB player ID |
| outs_when_up | Outs when batter came up |
| inning | Inning number |
| inning_topbot | Top/Bot |
| hc_x | Hit coordinate X |
| hc_y | Hit coordinate Y |
| tfs_deprecated | Deprecated time field |
| tfs_zulu_deprecated | Deprecated time field |
| fielder_2 | Catcher MLB player ID |
| umpire | Umpire (rarely populated) |
| sv_id | Savant video ID |
| vx0 | Velocity in x direction at y=50ft |
| vy0 | Velocity in y direction at y=50ft |
| vz0 | Velocity in z direction at y=50ft |
| ax | Acceleration in x direction |
| ay | Acceleration in y direction |
| az | Acceleration in z direction |
| sz_top | Top of batter strike zone |
| sz_bot | Bottom of batter strike zone |
| hit_distance_sc | Projected hit distance (ft) |
| launch_speed | Exit velocity (mph) |
| launch_angle | Launch angle (degrees) |
| effective_speed | Perceived velocity |
| release_spin_rate | Spin rate at release (rpm) |
| release_extension | Release extension (ft) |
| game_pk | MLB game primary key |
| pitcher_1 | Fielder at 1B |
| fielder_2_1 | Fielder at C (duplicate key variant) |
| fielder_3 | Fielder at 1B |
| fielder_4 | Fielder at 2B |
| fielder_5 | Fielder at 3B |
| fielder_6 | Fielder at SS |
| fielder_7 | Fielder at LF |
| fielder_8 | Fielder at CF |
| fielder_9 | Fielder at RF |
| release_pos_y | Release position depth (ft) |
| estimated_ba_using_speedangle | xBA based on exit velocity and launch angle |
| estimated_woba_using_speedangle | xwOBA |
| woba_value | wOBA value of outcome |
| woba_denom | wOBA denominator |
| babip_value | BABIP value |
| iso_value | ISO value |
| launch_speed_angle | Launch speed/angle combined code |
| at_bat_number | At-bat number within game |
| pitch_number | Pitch number within at-bat |
| pitch_name | Full pitch name |
| home_score | Home team score at time of pitch |
| away_score | Away team score at time of pitch |
| bat_score | Batting team score |
| fld_score | Fielding team score |
| post_away_score | Away team score after play |
| post_home_score | Home team score after play |
| post_bat_score | Batting team score after play |
| post_fld_score | Fielding team score after play |
| if_fielding_alignment | Infield alignment |
| of_fielding_alignment | Outfield alignment |
| spin_axis | Spin axis (degrees, Hawk-Eye) |
| delta_home_win_exp | Change in home win expectancy |
| delta_run_exp | Change in run expectancy |

### Sprint speed leaderboard

Available from Baseball Savant leaderboards. One row per player per season.

| Field | Description |
|-------|-------------|
| player_id | MLB player ID |
| player_name | Player name |
| season | Season year |
| sprint_speed | Average sprint speed (ft/sec) |
| attempts | Sprint attempts counted |
| competitive_runs | Competitive runs counted |
| percent_rank | Percentile rank |

### Outs above average (OAA)

Fielding metric from Baseball Savant. One row per player per season.

| Field | Description |
|-------|-------------|
| player_id | MLB player ID |
| player_name | Player name |
| season | Season year |
| pos | Fielding position |
| oaa | Outs above average |
| runs_saved | Runs saved |
| attempts | Fielding attempts |

### Expected stats leaderboard

| Field | Description |
|-------|-------------|
| player_id | MLB player ID |
| player_name | Player name |
| year | Season year |
| pa | Plate appearances |
| bip | Balls in play |
| ba | Actual batting average |
| xba | Expected batting average |
| slg | Actual slugging |
| xslg | Expected slugging |
| woba | Actual wOBA |
| xwoba | Expected wOBA |
| xobp | Expected OBP |
| xiso | Expected ISO |
| wobadiff | wOBA minus xwOBA |
| xbadiff | BA minus xBA |

## Stable identifiers

| Identifier | Description |
|------------|-------------|
| game_pk | MLB game primary key (joins to MLB Stats API) |
| batter | MLB player ID for batter |
| pitcher | MLB player ID for pitcher |
| game_date | Game date |
| at_bat_number | At-bat number within game |
| pitch_number | Pitch number within at-bat |

## Schema drift and stability notes

- Statcast columns are added frequently as new tracking metrics are introduced; expect column additions each season.
- Several deprecated fields exist in exports; prefix tracking them as `deprecated_*` in raw schema is prudent.
- Coverage begins in 2015 for most fields; pre-2015 data is unavailable from Statcast.
- Exit velocity and launch angle are available from approximately 2015; spin data from approximately 2017.
- Fielding alignment fields (`if_fielding_alignment`, `of_fielding_alignment`) added in 2023.

## Open questions

- Is this project pulling Statcast via direct CSV download, pybaseball, or direct API calls?
- Which export columns are required for the project versus which are optional?
- Is sprint speed, OAA, or expected stats data being ingested alongside pitch-level data?
- What is the update cadence for current-season data?
