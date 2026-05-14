# FanGraphs Source Notes

## Overview

FanGraphs is a baseball statistics and analysis website that provides leaderboard data, advanced metrics, projections, and player valuation tools. It does not offer a formal public API, but provides CSV export from its leaderboard pages. FanGraphs is the primary source for advanced metrics such as WAR, FIP, wRC+, and UZR in this project.

- **Website**: https://www.fangraphs.com
- **License**: No formal license; public access with attribution expected
- **Access pattern**: CSV export from leaderboard pages; accessible via pybaseball wrapper
- **Coverage**: 1871 to present for some stats; advanced metrics from approximately 2002

## Upstream documentation

| Document | URL |
|----------|-----|
| FanGraphs leaderboards | https://www.fangraphs.com/leaders.aspx |
| FanGraphs glossary | https://library.fangraphs.com/ |
| pybaseball FanGraphs module | https://github.com/jldbc/pybaseball |
| FanGraphs API (community) | https://github.com/WebucatorTraining/fangraphs-api |

## Available data families

### Batting leaderboard

One row per player per season. Available at https://www.fangraphs.com/leaders.aspx?pos=all&stats=bat

#### Standard batting fields

| Field | Description |
|-------|-------------|
| playerid | FanGraphs player ID |
| Name | Player name |
| Team | Team abbreviation |
| G | Games |
| AB | At-bats |
| PA | Plate appearances |
| H | Hits |
| 1B | Singles |
| 2B | Doubles |
| 3B | Triples |
| HR | Home runs |
| R | Runs |
| RBI | RBI |
| BB | Walks |
| IBB | Intentional walks |
| SO | Strikeouts |
| HBP | Hit by pitch |
| SF | Sacrifice flies |
| SH | Sacrifice hits |
| GDP | Grounded into double play |
| SB | Stolen bases |
| CS | Caught stealing |
| AVG | Batting average |

#### Advanced batting fields

| Field | Description |
|-------|-------------|
| BB% | Walk rate |
| K% | Strikeout rate |
| BB/K | Walk to strikeout ratio |
| OBP | On-base percentage |
| SLG | Slugging percentage |
| OPS | OBP + SLG |
| ISO | Isolated power |
| BABIP | Batting average on balls in play |
| wRC | Weighted runs created |
| wRAA | Weighted runs above average |
| wOBA | Weighted on-base average |
| wRC+ | Weighted runs created plus (park/league adjusted) |
| Spd | Speed score |
| UBR | Ultimate base running |
| wSB | Weighted stolen base runs |
| wBsR | Weighted base running |

#### Batted ball fields

| Field | Description |
|-------|-------------|
| GB% | Ground ball percentage |
| FB% | Fly ball percentage |
| LD% | Line drive percentage |
| IFFB% | Infield fly ball percentage |
| HR/FB | Home run per fly ball ratio |
| IFH% | Infield hit percentage |
| BUH% | Bunt hit percentage |
| Pull% | Pull percentage |
| Cent% | Center percentage |
| Oppo% | Opposite field percentage |
| Soft% | Soft contact percentage |
| Med% | Medium contact percentage |
| Hard% | Hard contact percentage |

#### Win value fields

| Field | Description |
|-------|-------------|
| Bat | Batting runs above average |
| BsR | Base running runs above average |
| Fld | Fielding runs above average |
| Pos | Positional adjustment |
| RAR | Runs above replacement |
| WAR | Wins above replacement |
| Dol | Dollar value |
| Dollars | Dollar value (alternate) |

### Pitching leaderboard

One row per pitcher per season. Available at https://www.fangraphs.com/leaders.aspx?pos=all&stats=pit

#### Standard pitching fields

| Field | Description |
|-------|-------------|
| playerid | FanGraphs player ID |
| Name | Player name |
| Team | Team abbreviation |
| W | Wins |
| L | Losses |
| ERA | Earned run average |
| G | Games |
| GS | Games started |
| QS | Quality starts |
| CG | Complete games |
| ShO | Shutouts |
| SV | Saves |
| BS | Blown saves |
| HLD | Holds |
| IP | Innings pitched |
| TBF | Total batters faced |
| H | Hits allowed |
| R | Runs allowed |
| ER | Earned runs |
| HR | Home runs allowed |
| BB | Walks |
| IBB | Intentional walks |
| HBP | Hit batters |
| WP | Wild pitches |
| BK | Balks |
| SO | Strikeouts |

#### Advanced pitching fields

| Field | Description |
|-------|-------------|
| K/9 | Strikeouts per 9 innings |
| BB/9 | Walks per 9 innings |
| K/BB | Strikeout to walk ratio |
| H/9 | Hits per 9 innings |
| HR/9 | Home runs per 9 innings |
| K% | Strikeout rate |
| BB% | Walk rate |
| K-BB% | K minus BB rate |
| AVG | Opponent batting average |
| WHIP | Walks + hits per inning pitched |
| BABIP | Batting average on balls in play against |
| LOB% | Left on base percentage |
| ERA- | ERA minus (park/league adjusted) |
| FIP | Fielding independent pitching |
| FIP- | FIP minus (park/league adjusted) |
| xFIP | Expected FIP |
| xFIP- | xFIP minus |
| SIERA | Skill-interactive ERA |
| tERA | True ERA |
| RS/9 | Run support per 9 |
| E-F | ERA minus FIP |

#### Batted ball pitching fields

| Field | Description |
|-------|-------------|
| GB% | Ground ball percentage against |
| FB% | Fly ball percentage against |
| LD% | Line drive percentage against |
| IFFB% | Infield fly ball percentage |
| HR/FB | HR per fly ball ratio |
| IFH% | Infield hit percentage |
| Pull% | Pull percentage |
| Cent% | Center percentage |
| Oppo% | Opposite field percentage |
| Soft% | Soft contact percentage |
| Med% | Medium contact percentage |
| Hard% | Hard contact percentage |

#### Win value pitching fields

| Field | Description |
|-------|-------------|
| RAR | Runs above replacement |
| WAR | Wins above replacement |
| Dol | Dollar value |

### Fielding leaderboard

| Field | Description |
|-------|-------------|
| playerid | FanGraphs player ID |
| Name | Player name |
| Team | Team |
| Pos | Position |
| Inn | Innings at position |
| GS | Games started |
| DRS | Defensive runs saved |
| BIZ | Balls in zone |
| Plays | Total plays |
| RZR | Revised zone rating |
| OOZ | Out of zone plays |
| UZR | Ultimate zone rating |
| UZR/150 | UZR per 150 games |
| Def | Total defense runs |
| ARM | Outfield arm runs |
| DPR | Double play runs |
| RngR | Range runs |
| ErrR | Error runs |

### Projections

FanGraphs hosts multiple projection systems including Steamer, ZiPS, ATC, THE BAT, and Depth Charts composite.

| Field | Description |
|-------|-------------|
| playerid | FanGraphs player ID |
| Name | Player name |
| Team | Team |
| All standard stat fields | Per projection system |

### Splits leaderboards

FanGraphs provides leaderboards split by:
- Home/Away
- vs LHP / vs RHP
- By month
- By count
- By inning

## Stable identifiers

| Identifier | Description |
|------------|-------------|
| playerid | FanGraphs integer player ID |
| Name | Player name (use with playerid for joins) |
| Season | Season year |

## Schema drift and stability notes

- FanGraphs leaderboard column sets change based on the selected stat group and custom column selections; the project should pin to specific leaderboard export profiles.
- The playerid is stable and can be used to link FanGraphs data to MLBAM IDs via a crosswalk.
- Projection system availability and naming changes year to year; track which system was used.
- Some advanced metrics (e.g., DRS, UZR) are sourced from Baseball Info Solutions (BIS) and may update retroactively.

## Open questions

- Which FanGraphs leaderboards does this project plan to ingest (batting, pitching, fielding, projections)?
- Is pybaseball used to pull FanGraphs data, or direct CSV download?
- Which projection system is the project standard?
- How are FanGraphs playerids mapped to Retrosheet/MLB IDs in the crosswalk layer?
