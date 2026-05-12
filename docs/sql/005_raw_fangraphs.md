# FanGraphs Raw DDL Notes

## Source

- **Provider:** FanGraphs via CSV leaderboard exports and `pybaseball` wrappers
- **Authority:** FanGraphs leaderboard export column headers (no official schema doc)
- **Upstream SQL:** None — CSV column headers are the authoritative spec; headers drift across seasons
- **DDL files:** `sql/70_tables_raw/020_raw_fangraphs_batting.sql`, `sql/70_tables_raw/021_raw_fangraphs_pitching.sql`, `sql/70_tables_raw/04_raw_fangraphs.sql`

## Design strategy

FanGraphs data comes from leaderboard CSV exports split by report type (batting, pitching,
fielding, projections). Each leaderboard family gets its own raw table. Column drift is
expected each year — include a `payload` JSONB column alongside extracted scalar fields
so that new columns don't break the load pipeline. Stable scalar identifiers (`playerid`,
`Name`, `Team`, `Season`) are typed and indexed; advanced metrics are loaded as JSONB.

## Key tables

### `raw_fangraphs_batting`

One row per player per season from the batting leaderboard export.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| playerid | integer | FanGraphs player ID |
| Name | text | Player name |
| Team | text | Team abbreviation |
| Season | integer | Season year |
| G | integer | Games played |
| AB | integer | At bats |
| PA | integer | Plate appearances |
| H | integer | Hits |
| HR | integer | Home runs |
| R | integer | Runs |
| RBI | integer | RBI |
| SB | integer | Stolen bases |
| BB_pct | numeric | Walk rate |
| K_pct | numeric | Strikeout rate |
| AVG | numeric | Batting average |
| OBP | numeric | On-base percentage |
| SLG | numeric | Slugging percentage |
| OPS | numeric | OPS |
| wRC_plus | integer | wRC+ |
| WAR | numeric | Wins above replacement |
| wOBA | numeric | wOBA |
| xFIP | numeric | xFIP (if available) |
| BABIP | numeric | BABIP |
| payload | jsonb | Full row as loaded from CSV |
| loaded_at | timestamptz | Load timestamp |

### `raw_fangraphs_pitching`

One row per pitcher per season from the pitching leaderboard export.

| Column | Type | Notes |
|--------|------|-------|
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
| IP | numeric | Innings pitched |
| K_9 | numeric | K/9 |
| BB_9 | numeric | BB/9 |
| HR_9 | numeric | HR/9 |
| BABIP | numeric | BABIP |
| LOB_pct | numeric | Left on base % |
| FIP | numeric | FIP |
| xFIP | numeric | xFIP |
| SIERA | numeric | SIERA |
| WAR | numeric | Wins above replacement |
| K_pct | numeric | Strikeout rate |
| BB_pct | numeric | Walk rate |
| payload | jsonb | Full row as loaded from CSV |
| loaded_at | timestamptz | Load timestamp |

### `raw_fangraphs_fielding`

One row per player per position per season from the fielding leaderboard.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| playerid | integer | FanGraphs player ID |
| Name | text | Player name |
| Team | text | Team abbreviation |
| Season | integer | Season year |
| Pos | text | Position |
| G | integer | Games |
| GS | integer | Games started |
| Inn | numeric | Innings |
| OAA | integer | Outs above average |
| DRS | integer | Defensive runs saved |
| UZR | numeric | UZR |
| Def | numeric | Defensive runs (combined) |
| payload | jsonb | Full row as loaded from CSV |
| loaded_at | timestamptz | Load timestamp |

### `raw_fangraphs_projections`

One row per player per projection system export.

| Column | Type | Notes |
|--------|------|-------|
| load_id | uuid | Batch load identifier |
| playerid | integer | FanGraphs player ID |
| Name | text | Player name |
| Team | text | Team abbreviation |
| projection_system | text | Steamer / ZiPS / DepthCharts / ATC |
| player_type | text | batter / pitcher |
| payload | jsonb | Full projected stats row |
| loaded_at | timestamptz | Load timestamp |

## Load strategy

- Export via `pybaseball.batting_stats()`, `pitching_stats()`, `fielding_stats()` per season
- Always log CSV column headers on load to detect drift
- On column drift: extend table with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` before inserting
- Unique constraint on `(playerid, Season, Team)` for batting/pitching tables

## Schema drift notes

- FanGraphs adds/renames columns frequently (especially advanced metrics, Statcast overlays)
- Do not treat the typed columns as exhaustive — `payload` JSONB preserves full export row
- Projection systems (Steamer, ZiPS) have different column sets — always load as JSONB

## Related docs

- [FanGraphs source notes](../sources/fangraphs-source-notes.md)
- [FanGraphs raw schema guide](../sources/fangraphs-raw-schema-guide.md)
