# Lahman Raw Schema Guide

## Strategy

Lahman raw ingestion should mirror the Lahman table structure as closely as possible. Because Lahman is already a relational dataset with a well-defined schema, raw tables should closely match source CSV column names and types. The primary adjustment is adding load tracking columns (load_id, source_file, retrieved_at) to each table.

## Raw table families

### raw_lahman_people

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
| playerID | text | Lahman player ID |
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
| bats | text | Batting hand |
| throws | text | Throwing hand |
| debut | date | MLB debut date |
| finalGame | date | Final game date |
| retroID | text | Retrosheet player ID |
| bbrefID | text | Baseball Reference player ID |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_batting

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
| playerID | text | Lahman player ID |
| yearID | integer | Season year |
| stint | integer | Stint within season |
| teamID | text | Team code |
| lgID | text | League |
| G | integer | Games |
| AB | integer | At-bats |
| R | integer | Runs |
| H | integer | Hits |
| H2B | integer | Doubles (source: 2B) |
| H3B | integer | Triples (source: 3B) |
| HR | integer | Home runs |
| RBI | integer | RBI |
| SB | integer | Stolen bases |
| CS | integer | Caught stealing |
| BB | integer | Walks |
| SO | integer | Strikeouts |
| IBB | integer | Intentional walks |
| HBP | integer | Hit by pitch |
| SH | integer | Sacrifice hits |
| SF | integer | Sacrifice flies |
| GIDP | integer | Grounded into double play |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_pitching

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
| playerID | text | Lahman player ID |
| yearID | integer | Season year |
| stint | integer | Stint within season |
| teamID | text | Team code |
| lgID | text | League |
| W | integer | Wins |
| L | integer | Losses |
| G | integer | Games |
| GS | integer | Games started |
| CG | integer | Complete games |
| SHO | integer | Shutouts |
| SV | integer | Saves |
| IPouts | integer | Outs pitched |
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
| SH | integer | Sac hits allowed |
| SF | integer | Sac flies allowed |
| GIDP | integer | GIDP induced |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_fielding

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
| playerID | text | Lahman player ID |
| yearID | integer | Season year |
| stint | integer | Stint within season |
| teamID | text | Team code |
| lgID | text | League |
| POS | text | Position |
| G | integer | Games |
| GS | integer | Games started |
| InnOuts | integer | Innings (outs) |
| PO | integer | Putouts |
| A | integer | Assists |
| E | integer | Errors |
| DP | integer | Double plays |
| PB | integer | Passed balls |
| WP | integer | Wild pitches allowed |
| SB | integer | Stolen bases allowed |
| CS | integer | Caught stealing |
| ZR | numeric | Zone rating |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_teams

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
| yearID | integer | Season year |
| lgID | text | League |
| teamID | text | Team code |
| franchID | text | Franchise code |
| divID | text | Division |
| Rank | integer | Finish rank |
| G | integer | Games |
| Ghome | integer | Home games |
| W | integer | Wins |
| L | integer | Losses |
| DivWin | text | Division winner |
| WCWin | text | Wild card winner |
| LgWin | text | League champion |
| WSWin | text | World Series winner |
| R | integer | Runs scored |
| AB | integer | At-bats |
| H | integer | Hits |
| HR | integer | Home runs |
| BB | integer | Walks |
| SO | integer | Strikeouts |
| SB | integer | Stolen bases |
| RA | integer | Runs allowed |
| ER | integer | Earned runs |
| ERA | numeric | Team ERA |
| CG | integer | Complete games |
| SHO | integer | Shutouts |
| SV | integer | Saves |
| E | integer | Errors |
| DP | integer | Double plays |
| FP | numeric | Fielding percentage |
| name | text | Team name |
| park | text | Ballpark name |
| attendance | integer | Home attendance |
| BPF | integer | Batter park factor |
| PPF | integer | Pitcher park factor |
| teamIDBR | text | Baseball Reference ID |
| teamIDretro | text | Retrosheet team ID |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_appearances

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
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
| G_of | integer | Games in OF |
| G_dh | integer | Games as DH |
| G_ph | integer | Games as PH |
| G_pr | integer | Games as PR |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_salaries

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
| yearID | integer | Season year |
| teamID | text | Team code |
| lgID | text | League |
| playerID | text | Lahman player ID |
| salary | integer | Salary in dollars |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_halloffame

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
| playerID | text | Lahman player ID |
| yearid | integer | Voting year |
| votedBy | text | Voting body |
| ballots | integer | Ballots cast |
| needed | integer | Votes needed |
| votes | integer | Votes received |
| inducted | text | Y/N |
| category | text | Category |
| needed_note | text | Notes |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_parks

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Batch load identifier |
| source_file | text | Source CSV filename |
| park_key | text | Park key |
| park_name | text | Park name |
| park_alias | text | Park aliases |
| city | text | City |
| state | text | State |
| country | text | Country |
| retrieved_at | timestamptz | Load timestamp |

### raw_lahman_load_batches

| Column | Type | Description |
|--------|------|-------------|
| load_id | uuid | Unique batch identifier |
| table_name | text | Lahman table name loaded |
| source_file | text | Source CSV filename |
| lahman_version | text | Lahman release version |
| rows_loaded | integer | Rows inserted |
| loaded_at | timestamptz | Load timestamp |
| status | text | success / failed / partial |
| error_message | text | Error detail |

## Load strategy

- Mirror Lahman CSV structure directly with minimal transformation.
- Rename columns starting with digits (2B, 3B) to H2B, H3B in the database.
- Preserve all source field names in comments or column descriptions.
- Index on playerID, teamID, yearID after load.
- Track Lahman release version in load batch metadata.
