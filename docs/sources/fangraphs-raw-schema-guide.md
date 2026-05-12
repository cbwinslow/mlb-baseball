# FanGraphs Raw Schema Guide

## Strategy

FanGraphs raw ingestion should be split by leaderboard export family. Each leaderboard type (batting, pitching, fielding, projections) maps to a separate raw table. Column drift is expected over time; add a raw payload JSONB column to each table alongside typed columns extracted from the most stable core fields.

## Raw table families

### raw_fangraphs_batting

One row per player per season from the batting leaderboard export.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| playerid | integer | FanGraphs player ID |
| Name | text | Player name |
| Team | text | Team abbreviation |
| Season | integer | Season year |
| G | integer | Games |
| AB | integer | At-bats |
| PA | integer | Plate appearances |
| H | integer | Hits |
| H1B | integer | Singles (source: 1B) |
| H2B | integer | Doubles (source: 2B) |
| H3B | integer | Triples (source: 3B) |
| HR | integer | Home runs |
| R | integer | Runs |
| RBI | integer | RBI |
| BB | integer | Walks |
| IBB | integer | Intentional walks |
| SO | integer | Strikeouts |
| HBP | integer | Hit by pitch |
| SF | integer | Sacrifice flies |
| SH | integer | Sacrifice hits |
| GDP | integer | Grounded into double play |
| SB | integer | Stolen bases |
| CS | integer | Caught stealing |
| AVG | numeric | Batting average |
| BB_pct | numeric | Walk rate |
| K_pct | numeric | Strikeout rate |
| OBP | numeric | On-base percentage |
| SLG | numeric | Slugging percentage |
| OPS | numeric | OPS |
| ISO | numeric | Isolated power |
| BABIP | numeric | BABIP |
| wOBA | numeric | wOBA |
| wRC_plus | numeric | wRC+ |
| WAR | numeric | Wins above replacement |
| GB_pct | numeric | Ground ball rate |
| FB_pct | numeric | Fly ball rate |
| LD_pct | numeric | Line drive rate |
| Hard_pct | numeric | Hard contact rate |
| pull_pct | numeric | Pull rate |
| extra_fields | jsonb | Additional exported columns |
| leaderboard_type | text | e.g. standard / advanced / batted_ball |
| retrieved_at | timestamptz | Load timestamp |

### raw_fangraphs_pitching

One row per pitcher per season from the pitching leaderboard export.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| playerid | integer | FanGraphs player ID |
| Name | text | Player name |
| Team | text | Team abbreviation |
| Season | integer | Season year |
| W | integer | Wins |
| L | integer | Losses |
| ERA | numeric | ERA |
| G | integer | Games |
| GS | integer | Games started |
| SV | integer | Saves |
| HLD | integer | Holds |
| IP | numeric | Innings pitched |
| TBF | integer | Total batters faced |
| H | integer | Hits allowed |
| HR | integer | Home runs allowed |
| BB | integer | Walks |
| SO | integer | Strikeouts |
| WHIP | numeric | WHIP |
| K_9 | numeric | K/9 |
| BB_9 | numeric | BB/9 |
| FIP | numeric | FIP |
| xFIP | numeric | xFIP |
| SIERA | numeric | SIERA |
| LOB_pct | numeric | LOB% |
| BABIP | numeric | BABIP against |
| GB_pct | numeric | Ground ball rate |
| FB_pct | numeric | Fly ball rate |
| HR_FB | numeric | HR/FB rate |
| WAR | numeric | Wins above replacement |
| extra_fields | jsonb | Additional exported columns |
| leaderboard_type | text | e.g. standard / advanced / batted_ball |
| retrieved_at | timestamptz | Load timestamp |

### raw_fangraphs_fielding

One row per player per position per season from fielding leaderboard.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| playerid | integer | FanGraphs player ID |
| Name | text | Player name |
| Team | text | Team abbreviation |
| Season | integer | Season year |
| Pos | text | Position |
| Inn | numeric | Innings at position |
| GS | integer | Games started |
| DRS | integer | Defensive runs saved |
| UZR | numeric | Ultimate zone rating |
| UZR_150 | numeric | UZR per 150 games |
| Def | numeric | Total defense runs |
| ARM | numeric | Arm runs (outfield) |
| RngR | numeric | Range runs |
| ErrR | numeric | Error runs |
| extra_fields | jsonb | Additional exported columns |
| retrieved_at | timestamptz | Load timestamp |

### raw_fangraphs_projections

One row per player per projection system per season.

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| playerid | integer | FanGraphs player ID |
| Name | text | Player name |
| Team | text | Team abbreviation |
| Season | integer | Projection season year |
| proj_system | text | Steamer / ZiPS / ATC / THE_BAT / DepthCharts |
| player_type | text | batter / pitcher |
| payload | jsonb | Full projection row from export |
| retrieved_at | timestamptz | Load timestamp |

### raw_fangraphs_load_batches

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Unique batch identifier |
| leaderboard | text | batting / pitching / fielding / projections |
| season | integer | Season year |
| stat_group | text | standard / advanced / batted_ball / splits |
| split_type | text | null / home_away / vs_hand / by_month |
| proj_system | text | Projection system if applicable |
| rows_loaded | integer | Rows inserted |
| loaded_at | timestamptz | Load timestamp |
| status | text | success / failed / partial |
| error_message | text | Error detail |

## Load strategy

- Store core typed columns plus extra_fields JSONB for column drift tolerance.
- Track leaderboard type and stat group per batch.
- Rename columns starting with digits (1B, 2B, 3B) to H1B, H2B, H3B in database.
- Rename rate columns with special characters (BB%, K%, K/9) to snake_case equivalents.
- Index on playerid and Season after load.
- Pin to a documented FanGraphs export profile to ensure consistent column sets.
