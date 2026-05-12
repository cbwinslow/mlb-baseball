# Lahman Baseball Database Source Notes

## Overview

The Lahman Baseball Database is the most comprehensive freely available historical baseball statistics database. It is maintained by Sean Lahman and covers seasons from 1871 to the present. The database is distributed in multiple formats including CSV, SQL dumps, and R packages. It provides aggregate season-level statistics for players and teams.

- **Website**: http://www.seanlahman.com/baseball-archive/statistics/
- **GitHub**: https://github.com/chadwickbureau/baseballdatabank (Chadwick Bureau fork, updated regularly)
- **License**: Creative Commons Attribution-ShareAlike 3.0 Unported
- **Access pattern**: File download (CSV or SQL dump)
- **Coverage**: 1871 to present (updated annually)

## Upstream documentation

| Document | URL |
|----------|-----|
| Official site | http://www.seanlahman.com/baseball-archive/statistics/ |
| Chadwick Bureau fork | https://github.com/chadwickbureau/baseballdatabank |
| Lahman R package | https://github.com/cdalzell/Lahman |
| R package documentation | https://cran.r-project.org/web/packages/Lahman/Lahman.pdf |

## Available tables

### People

Player biographical data. One row per player.

| Field | Type | Description |
|-------|------|-------------|
| playerID | text | Lahman player identifier |
| birthYear | integer | Birth year |
| birthMonth | integer | Birth month |
| birthDay | integer | Birth day |
| birthCountry | text | Birth country |
| birthState | text | Birth state |
| birthCity | text | Birth city |
| deathYear | integer | Death year |
| deathMonth | integer | Death month |
| deathDay | integer | Death day |
| deathCountry | text | Death country |
| deathState | text | Death state |
| deathCity | text | Death city |
| nameFirst | text | First name |
| nameLast | text | Last name |
| nameGiven | text | Given name |
| weight | integer | Weight (lbs) |
| height | integer | Height (inches) |
| bats | text | Batting hand (R/L/B) |
| throws | text | Throwing hand (R/L) |
| debut | date | MLB debut date |
| finalGame | date | Final game date |
| retroID | text | Retrosheet player ID |
| bbrefID | text | Baseball Reference player ID |

### Batting

Batting statistics. One row per player per team per year.

| Field | Type | Description |
|-------|------|-------------|
| playerID | text | Lahman player ID |
| yearID | integer | Season year |
| stint | integer | Order within season (for mid-season trades) |
| teamID | text | Team code |
| lgID | text | League (AL/NL) |
| G | integer | Games |
| AB | integer | At-bats |
| R | integer | Runs |
| H | integer | Hits |
| 2B | integer | Doubles |
| 3B | integer | Triples |
| HR | integer | Home runs |
| RBI | integer | Runs batted in |
| SB | integer | Stolen bases |
| CS | integer | Caught stealing |
| BB | integer | Walks |
| SO | integer | Strikeouts |
| IBB | integer | Intentional walks |
| HBP | integer | Hit by pitch |
| SH | integer | Sacrifice hits |
| SF | integer | Sacrifice flies |
| GIDP | integer | Grounded into double play |

### Pitching

Pitching statistics. One row per player per team per year.

| Field | Type | Description |
|-------|------|-------------|
| playerID | text | Lahman player ID |
| yearID | integer | Season year |
| stint | integer | Order within season |
| teamID | text | Team code |
| lgID | text | League |
| W | integer | Wins |
| L | integer | Losses |
| G | integer | Games |
| GS | integer | Games started |
| CG | integer | Complete games |
| SHO | integer | Shutouts |
| SV | integer | Saves |
| IPouts | integer | Outs pitched (IP * 3) |
| H | integer | Hits allowed |
| ER | integer | Earned runs |
| HR | integer | Home runs allowed |
| BB | integer | Walks |
| SO | integer | Strikeouts |
| BAOpp | numeric | Opponent batting average |
| ERA | numeric | Earned run average |
| IBB | integer | Intentional walks |
| WP | integer | Wild pitches |
| HBP | integer | Hit batters |
| BK | integer | Balks |
| BFP | integer | Batters faced |
| GF | integer | Games finished |
| R | integer | Runs allowed |
| SH | integer | Sacrifice hits allowed |
| SF | integer | Sacrifice flies allowed |
| GIDP | integer | Grounded into double plays |

### Fielding

Fielding statistics. One row per player per position per team per year.

| Field | Type | Description |
|-------|------|-------------|
| playerID | text | Lahman player ID |
| yearID | integer | Season year |
| stint | integer | Order within season |
| teamID | text | Team code |
| lgID | text | League |
| POS | text | Position |
| G | integer | Games at position |
| GS | integer | Games started at position |
| InnOuts | integer | Innings played (outs) |
| PO | integer | Putouts |
| A | integer | Assists |
| E | integer | Errors |
| DP | integer | Double plays |
| PB | integer | Passed balls (catchers) |
| WP | integer | Wild pitches (catchers) |
| SB | integer | Stolen bases allowed (catchers) |
| CS | integer | Runners caught stealing (catchers) |
| ZR | numeric | Zone rating |

### Teams

Team season statistics. One row per team per year.

| Field | Type | Description |
|-------|------|-------------|
| yearID | integer | Season year |
| lgID | text | League |
| teamID | text | Team code |
| franchID | text | Franchise code |
| divID | text | Division |
| Rank | integer | Final division rank |
| G | integer | Games played |
| Ghome | integer | Home games |
| W | integer | Wins |
| L | integer | Losses |
| DivWin | text | Division winner (Y/N) |
| WCWin | text | Wild card winner (Y/N) |
| LgWin | text | League winner (Y/N) |
| WSWin | text | World Series winner (Y/N) |
| R | integer | Runs scored |
| AB | integer | At-bats |
| H | integer | Hits |
| 2B | integer | Doubles |
| 3B | integer | Triples |
| HR | integer | Home runs |
| BB | integer | Walks |
| SO | integer | Strikeouts |
| SB | integer | Stolen bases |
| CS | integer | Caught stealing |
| HBP | integer | Hit by pitch |
| SF | integer | Sacrifice flies |
| RA | integer | Runs allowed |
| ER | integer | Earned runs |
| ERA | numeric | Team ERA |
| CG | integer | Complete games |
| SHO | integer | Shutouts |
| SV | integer | Saves |
| IPouts | integer | Outs pitched |
| HA | integer | Hits allowed |
| HRA | integer | Home runs allowed |
| BBA | integer | Walks allowed |
| SOA | integer | Strikeouts by pitchers |
| E | integer | Errors |
| DP | integer | Double plays |
| FP | numeric | Fielding percentage |
| name | text | Team name |
| park | text | Ballpark name |
| attendance | integer | Home attendance |
| BPF | integer | Ballpark factor (batters) |
| PPF | integer | Ballpark factor (pitchers) |
| teamIDBR | text | Baseball Reference team ID |
| teamIDlahman45 | text | Lahman 4.5 team ID |
| teamIDretro | text | Retrosheet team ID |

### Appearances

Player appearances by position per team per year.

| Field | Type | Description |
|-------|------|-------------|
| yearID | integer | Season year |
| teamID | text | Team code |
| lgID | text | League |
| playerID | text | Lahman player ID |
| G_all | integer | Total games |
| GS | integer | Games started |
| G_batting | integer | Games batting |
| G_defense | integer | Games in field |
| G_p | integer | Games as pitcher |
| G_c | integer | Games as catcher |
| G_1b | integer | Games at 1B |
| G_2b | integer | Games at 2B |
| G_3b | integer | Games at 3B |
| G_ss | integer | Games at SS |
| G_lf | integer | Games in LF |
| G_cf | integer | Games in CF |
| G_rf | integer | Games in RF |
| G_of | integer | Games in OF total |
| G_dh | integer | Games as DH |
| G_ph | integer | Games as PH |
| G_pr | integer | Games as PR |

### Salaries

Player salary data.

| Field | Type | Description |
|-------|------|-------------|
| yearID | integer | Season year |
| teamID | text | Team code |
| lgID | text | League |
| playerID | text | Lahman player ID |
| salary | integer | Salary in dollars |

### AllstarFull

All-Star game appearances.

| Field | Type | Description |
|-------|------|-------------|
| playerID | text | Lahman player ID |
| yearID | integer | Season year |
| gameNum | integer | Game number in year |
| gameID | text | All-Star game ID |
| teamID | text | Team code |
| lgID | text | League |
| GP | integer | Games played |
| startingPos | integer | Starting position |

### HallOfFame

Hall of Fame voting history.

| Field | Type | Description |
|-------|------|-------------|
| playerID | text | Lahman player ID |
| yearid | integer | Voting year |
| votedBy | text | Voting body |
| ballots | integer | Total ballots cast |
| needed | integer | Votes needed |
| votes | integer | Votes received |
| inducted | text | Y/N inducted |
| category | text | Player/Manager/Pioneer |
| needed_note | text | Notes on threshold |

### Managers

Managerial records per team per year.

| Field | Type | Description |
|-------|------|-------------|
| playerID | text | Lahman player ID |
| yearID | integer | Season year |
| teamID | text | Team code |
| lgID | text | League |
| inseason | integer | Order within season |
| G | integer | Games managed |
| W | integer | Wins |
| L | integer | Losses |
| rank | integer | Finish rank |
| plyrMgr | text | Player/manager flag |

### Parks

Ballpark data.

| Field | Type | Description |
|-------|------|-------------|
| parkalias | text | Park aliases |
| parkname | text | Park name |
| park.key | text | Park key |
| city | text | City |
| state | text | State |
| country | text | Country |

### SeriesPost

Postseason series results.

| Field | Type | Description |
|-------|------|-------------|
| yearID | integer | Season year |
| round | text | Series round |
| teamIDwinner | text | Winning team |
| lgIDwinner | text | Winner league |
| teamIDloser | text | Losing team |
| lgIDloser | text | Loser league |
| wins | integer | Series wins |
| losses | integer | Series losses |
| ties | integer | Series ties |

## Stable identifiers

| Identifier | Description |
|------------|-------------|
| playerID | Lahman player key (8 chars, same as Retrosheet for most players) |
| teamID | 3-character team code |
| yearID | Season year |
| stint | Sequence within season for multi-team players |
| retroID | Retrosheet player ID (in People table) |
| bbrefID | Baseball Reference player ID (in People table) |

## Schema drift and stability notes

- Lahman schema is very stable; major changes are rare.
- New fields are occasionally added to existing tables (e.g., SF, IBB added for older seasons over time).
- Some fields are null for older seasons where data was not tracked.
- playerID is consistent with Retrosheet IDs for most modern players but may differ for 19th century players.
- The Chadwick Bureau fork is updated more frequently than the official Lahman releases.

## Open questions

- Is the project using the official Lahman CSV release or the Chadwick Bureau fork?
- What is the current version/season coverage of the local Lahman data?
- Are Salaries and HallOfFame data planned for ingestion?
- Is Parks data being used for crosswalk/canonical park identification?
