# MLB Stats API Source Notes

## Overview

The MLB Stats API is the official MLB data platform. It powers MLB.com and the Gameday application and exposes schedule, game, player, team, standings, and statistical data. There is no formal public developer portal, but the API is widely documented by the community and is freely accessible without authentication for most endpoints.

- **Base URL**: https://statsapi.mlb.com/api/v1
- **License**: No formal license; public access, no authentication required for most endpoints
- **Access pattern**: JSON REST API
- **Coverage**: Current and historical MLB seasons; some historical data is limited

## Upstream documentation

| Document | URL |
|----------|-----|
| Community API reference | https://github.com/toddrob99/MLB-StatsAPI |
| Swagger/OpenAPI community doc | https://statsapi.mlb.com/docs/ |
| toddrob99 Python wrapper | https://github.com/toddrob99/MLB-StatsAPI/wiki |

## Available endpoint families

### Schedule

Returns games scheduled or played for a given date range, season, or team.

| Parameter | Description |
|-----------|-------------|
| sportId | Sport identifier (1 = MLB) |
| season | Season year |
| startDate | Start date (YYYY-MM-DD) |
| endDate | End date (YYYY-MM-DD) |
| teamId | Filter by team |
| gameType | R = regular season, P = postseason, S = spring training |
| hydrate | Comma-separated list of additional data to include |

Key response fields: gamePk, gameDate, status, teams (home/away with team info and score), venue, seriesDescription

### Games

Returns detailed game data by game primary key (gamePk).

Endpoints:
- `/game/{gamePk}/feed/live` — full live feed with plays, linescore, boxscore
- `/game/{gamePk}/boxscore` — boxscore only
- `/game/{gamePk}/linescore` — linescore only
- `/game/{gamePk}/playByPlay` — play-by-play events

Key response fields: gamePk, gameDate, status, teams, linescore (innings, runs/hits/errors), plays (allPlays array with play-level data), decisions

### Players

Returns player bio, biographical, and career data.

Endpoints:
- `/people/{personId}` — individual player
- `/people?personIds=x,y,z` — multiple players
- `/sports/{sportId}/players?season=YYYY` — all players in a season

Key response fields: id, fullName, firstName, lastName, primaryNumber, birthDate, birthCity, birthCountry, height, weight, active, primaryPosition (code, name, type), batSide, pitchHand, mlbDebutDate, currentTeam

### Teams

Returns team information including franchise history.

Endpoints:
- `/teams` — all teams
- `/teams/{teamId}` — single team
- `/teams/{teamId}/roster?season=YYYY` — team roster
- `/teams/{teamId}/stats?season=YYYY&group=hitting` — team stats

Key response fields: id, name, teamCode, fileCode, abbreviation, teamName, locationName, firstYearOfPlay, league (id, name), division (id, name), venue (id, name), active

### Standings

Returns standings for a league and season.

Endpoints:
- `/standings?leagueId=103,104&season=YYYY`

Key response fields: standingsType, league, division, teamRecords (team, wins, losses, pct, gamesBack, streakCode, divisionRank, leagueRank, wildCardRank)

### Stats

Returns statistical data by player, team, or league.

Endpoints:
- `/people/{personId}/stats?stats=season&group=hitting&season=YYYY`
- `/teams/{teamId}/stats?stats=season&group=pitching&season=YYYY`

Stat groups: hitting, pitching, fielding, catching, running

Stat types: season, career, yearByYear, gameLog, vsPlayer, vsTeam, winLoss, homeAndAway, byMonth, byDayOfWeek

Key hitting stat fields: gamesPlayed, atBats, runs, hits, doubles, triples, homeRuns, rbi, stolenBases, caughtStealing, walks, strikeOuts, avg, obp, slg, ops, babip

Key pitching stat fields: gamesPlayed, gamesStarted, wins, losses, era, inningsPitched, hits, runs, earnedRuns, walks, strikeOuts, homeRuns, whip, strikeoutsPer9Inn, walksPer9Inn

### Venues

Returns ballpark and venue data.

Endpoints:
- `/venues` — all venues
- `/venues/{venueId}` — single venue

Key response fields: id, name, link, active, season, location (address, city, state, country, defaultCoordinates), timeZone, fieldInfo (capacity, turfType, roofType, leftLine, leftCenter, center, rightCenter, rightLine)

### Leagues

Endpoints:
- `/league` — all leagues
- `/league/{leagueId}` — single league

Key response fields: id, name, link, abbreviation, nameShort, seasonState, hasWildCard, hasSplitSeason, numGames, hasPlayoffPoints, numTeams, numWildcardTeams, seasonDateInfo

### Divisions

Endpoints:
- `/divisions` — all divisions
- `/divisions/{divisionId}` — single division

### Transactions

Returns roster transactions (trades, signings, releases, DL moves).

Endpoints:
- `/transactions?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD`
- `/transactions?teamId=xxx&season=YYYY`

Key response fields: id, date, effectiveDate, resolutionDate, typeCode, typeDesc, person (id, fullName), fromTeam, toTeam, description

### Draft

Endpoints:
- `/draft/{year}` — draft results for a year

Key response fields: round, pickNumber, pickRound, rank, pickValue, signingBonus, home (city, state, country), school, person (id, fullName, primaryPosition)

### Awards

Endpoints:
- `/awards/{awardId}/recipients?season=YYYY`

### Attendance

Endpoints:
- `/attendance?teamId=xxx&season=YYYY`

## Stable identifiers

| Identifier | Description |
|------------|-------------|
| gamePk | Unique integer game primary key |
| personId | Unique integer player identifier |
| teamId | Unique integer team identifier |
| venueId | Unique integer venue identifier |
| leagueId | 103 = AL, 104 = NL |
| divisionId | Integer division identifier |

## Schema drift and stability notes

- The MLB Stats API does not publish changelogs; endpoint shapes can change without notice.
- The `hydrate` parameter significantly changes response shape; document which hydrations are used.
- Historical data coverage is uneven before approximately 2008.
- gamePk is the most stable cross-reference key across all game-related endpoints.

## Open questions

- Which hydrations does this project use for schedule and game endpoints?
- Is the live feed endpoint used for real-time ingestion or only historical backfill?
- What authentication is used if private endpoints are needed in future?
- What is the retry and rate-limit strategy for bulk historical pulls?
