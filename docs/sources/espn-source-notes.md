# ESPN Source Notes

## Overview

ESPN does not offer a formally documented public API for baseball data, but its internal API endpoints are publicly accessible and widely used by the community. These endpoints power the ESPN website and app and provide schedule, game summary, standings, team, and player data in JSON format. They require no authentication for most endpoints but may change without notice.

- **Base URL**: https://site.api.espn.com/apis/site/v2/sports/baseball/mlb
- **License**: No formal license; unofficial public access
- **Access pattern**: HTTP GET requests returning JSON
- **Coverage**: Current season primarily; limited historical data

## Upstream documentation

| Document | URL |
|----------|-----|
| ESPN API community reference | https://gist.github.com/akeaswaran/b48b02f170221d191564b57caa8a3f5e |
| Hidden ESPN API (community) | https://github.com/pseudo-r/Public-ESPN-API |
| espn-api Python library | https://github.com/cwendt94/espn-api |

## Available endpoint families

### Scoreboard

Returns games for a given date.

**Endpoint**: `GET /scoreboard?dates=YYYYMMDD`

Key response fields:

| Field | Description |
|-------|-------------|
| id | ESPN event ID |
| uid | Unique identifier string |
| date | Game date/time (ISO8601) |
| name | Game name string |
| shortName | Short name (e.g. NYY @ BOS) |
| season.year | Season year |
| season.type | 1=preseason, 2=regular, 3=postseason |
| week.number | Week number |
| status.type.id | Status ID |
| status.type.name | STATUS_IN_PROGRESS / STATUS_FINAL / etc |
| status.period | Current inning |
| status.displayClock | Inning display string |
| competitions[].venue | Venue name and location |
| competitions[].competitors | Array of home/away team with score |
| competitions[].situation | Current game situation (bases, outs, count) |
| competitions[].broadcasts | Broadcast network info |

### Game Summary

Returns detailed game data including boxscore, play-by-play, and game info.

**Endpoint**: `GET /summary?event={eventId}`

Key response sections:

| Section | Description |
|---------|-------------|
| header | Game header info (teams, score, status) |
| boxscore | Team and player stats |
| plays | Play-by-play array |
| leaders | Stat leaders for game |
| winProbability | Win probability over time |
| article | Associated article |
| standings | Standings context |
| news | Related news |

Key boxscore fields:

| Field | Description |
|-------|-------------|
| teams[].team.id | ESPN team ID |
| teams[].team.abbreviation | Team abbreviation |
| teams[].statistics | Array of stat name/value pairs |
| players[].statistics | Player-level stat arrays |
| players[].athletes | Array of player stat rows |

### Teams

**Endpoint**: `GET /teams`
**Endpoint**: `GET /teams/{teamId}`

Key response fields:

| Field | Description |
|-------|-------------|
| id | ESPN team ID |
| uid | Unique identifier |
| slug | URL slug |
| location | City name |
| name | Nickname |
| abbreviation | Team abbreviation |
| displayName | Full team name |
| shortDisplayName | Short name |
| color | Primary color hex |
| alternateColor | Alternate color hex |
| logos | Array of logo image URLs |
| record.items | Season record entries |

### Team Roster

**Endpoint**: `GET /teams/{teamId}/roster`

Key response fields:

| Field | Description |
|-------|-------------|
| athletes[].id | ESPN player ID |
| athletes[].uid | Unique identifier |
| athletes[].displayName | Player name |
| athletes[].jersey | Jersey number |
| athletes[].position.abbreviation | Position code |
| athletes[].status.type | Active/Injured/etc |
| athletes[].birthDate | Birth date |
| athletes[].birthPlace | Birth location |
| athletes[].weight | Weight |
| athletes[].height | Height |

### Players

**Endpoint**: `GET /athletes/{athleteId}`

Key response fields:

| Field | Description |
|-------|-------------|
| id | ESPN athlete ID |
| uid | Unique identifier |
| displayName | Full name |
| shortName | Short name |
| weight | Weight |
| height | Height |
| age | Age |
| dateOfBirth | Birth date |
| birthPlace | Birth location |
| college | College attended |
| debut | MLB debut year |
| position | Position object |
| experience | Years of experience |
| active | Active status |
| statistics | Career stat arrays |

### Standings

**Endpoint**: `GET /standings`

Key response fields:

| Field | Description |
|-------|-------------|
| standings.entries[].team.id | ESPN team ID |
| standings.entries[].team.abbreviation | Team abbreviation |
| standings.entries[].stats | Array of stat name/value/displayValue |

Stat names in standings: wins, losses, winPercent, gamesBehind, gamesPlayed, divisionGamesBehind, leagueGamesBehind, streak

### News

**Endpoint**: `GET /news`

Key response fields:

| Field | Description |
|-------|-------------|
| articles[].id | Article ID |
| articles[].headline | Headline text |
| articles[].description | Article description |
| articles[].published | Published timestamp |
| articles[].lastModified | Last modified timestamp |
| articles[].links.web.href | Article URL |
| articles[].categories | Tag and team/player associations |

## Stable identifiers

| Identifier | Description |
|------------|-------------|
| ESPN event ID | Integer game identifier for scoreboard/summary endpoints |
| ESPN team ID | Integer team identifier |
| ESPN athlete ID | Integer player identifier |

## ID crosswalk notes

ESPN IDs do not directly match MLB Stats API IDs (gamePk, personId, teamId). A crosswalk table mapping ESPN IDs to MLB IDs is required for cross-source joins. Community resources like the chadwick register or sportsreference provide some of these mappings.

## Schema drift and stability notes

- ESPN API endpoints are unofficial and can change or disappear without notice.
- Response structure can vary between regular season, postseason, and spring training.
- Some fields are only present in certain game states (e.g. situation fields only during live games).
- Player stat array indices vary by stat type; use stat name keys rather than positional indexing.
- Broadcast and media fields are frequently absent or null for older games.

## Open questions

- Which specific ESPN endpoints does this project use?
- Is ESPN data used for live/real-time ingestion or only supplemental historical context?
- What is the mapping strategy from ESPN IDs to MLB Stats API IDs?
- Is the espn-api Python library used, or direct HTTP calls?
