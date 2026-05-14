# Retrosheet Source Notes

## Overview

Retrosheet is a volunteer-driven organization that digitizes historical baseball play-by-play data. It is the primary source for historical event-level and game-level data in this project. Data is distributed as flat text files in documented formats and is freely available for non-commercial use.

- **Website**: https://www.retrosheet.org
- **License**: Non-commercial use with attribution required
- **Access pattern**: File download (season/league-based flat text files)
- **Coverage**: 1871 to present (completeness varies by era)

## Upstream documentation

| Document | URL |
|----------|-----|
| Event file format | https://www.retrosheet.org/eventfile.htm |
| Game log field list | https://www.retrosheet.org/gamelogs/glfields.txt |
| Box score file format | https://www.retrosheet.org/boxfile.txt |
| BEVENT tool docs | https://www.retrosheet.org/tools.htm |
| Chadwick Bureau tools | https://github.com/chadwickbureau/chadwick |
| Retrosheet file downloads | https://www.retrosheet.org/game.htm |

## Available data families

### Event files (.EVA, .EVN, .EV*)

Play-by-play event files are the core Retrosheet artifact. Each file covers one season and one team or league. Record types within event files:

| Record type | Description |
|-------------|-------------|
| `id` | Game identifier (e.g. ANA200304050) |
| `version` | File version indicator |
| `info` | Game-level metadata (site, date, start time, umpires, attendance, weather, etc.) |
| `start` | Starting lineup entries (player ID, name, team, batting order, fielding position) |
| `sub` | Substitution records (player ID, name, team, batting order, fielding position) |
| `play` | Play-by-play records (inning, team, batter ID, count, pitches, event string) |
| `com` | Comment records |
| `data` | Post-game data (earned runs per pitcher) |
| `badj` | Batter handedness adjustment |
| `padj` | Pitcher handedness adjustment |
| `ladj` | Lineup adjustment |

### Game log files (.GL)

Game log files provide one row per game with 161 fields covering teams, scores, lines, pitchers, and umpires. Key field groups:

| Field group | Description |
|-------------|-------------|
| Game identifiers | Date, game number, day of week |
| Team identifiers | Home team, visiting team, league codes |
| Line scores | Runs per inning for both teams |
| Totals | Runs, hits, errors, left on base |
| Pitchers | Winning, losing, saving pitchers and stats |
| Umpires | Home plate and base umpire IDs and names |
| Attendance | Park ID, attendance figure |
| Game duration | Time of game, day/night indicator |

### Roster files (.ROS)

Season roster files list all players on each team roster with their player ID, name, batting and throwing hand, and position.

| Field | Description |
|-------|-------------|
| Player ID | Retrosheet player identifier |
| Last name | Player last name |
| First name | Player first name |
| Bats | Batting handedness (R/L/B) |
| Throws | Throwing handedness (R/L) |
| Team | Team code |
| Position | Primary position |

### Schedule files (.SCH)

Schedule files list games as originally scheduled for each season, not as played. Useful for detecting postponements and makeups.

### BEVENT / Chadwick cwevent output fields

When Retrosheet event files are processed through BEVENT or the Chadwick `cwevent` tool, the output produces up to 97 derived fields per play. Key field groups:

| Field group | Examples |
|-------------|----------|
| Game identifiers | game_id, away_team_id, inn_ct, bat_home_id |
| Batter/pitcher | bat_id, pit_id, pos2_fld_id |
| Count/pitches | balls_ct, strikes_ct, pitch_seq_tx |
| Hit location | hit_val, battedball_cd, hit_location |
| Baserunners | base1_run_id, base2_run_id, base3_run_id |
| Play outcomes | event_cd, event_tx, rbi_ct, run_scored |
| Fielding | fielded_by, assist fields, error fields |

### BGAME / Chadwick cwgame output fields

The `cwgame` tool produces one row per game with up to 83 fields covering game-level aggregates derived from event files.

## Stable identifiers

| Identifier | Description |
|------------|-------------|
| Game ID | 12-character string: team + date + game number (e.g. ANA200304050) |
| Player ID | 8-character string: first 4 of last name + first 2 of first name + sequence (e.g. aaroh101) |
| Team code | 3-character team abbreviation used consistently within Retrosheet |
| Park ID | 5-character park identifier |

## Schema drift and stability notes

- Event file format has been stable for many years but new record types can be added.
- BEVENT/cwevent field numbering is positional and can shift when new fields are inserted; always pin to a known tool version.
- Older seasons (pre-1950) have varying completeness; pitch sequence data is often absent.
- Game logs are more complete than event files for very old seasons.

## Open questions

- Which Chadwick tool version is pinned for this project?
- Are box score files used in addition to event files, or only as fallback?
- Is schedule data used for scheduling gap detection or game alignment?
- What is the expected update cadence for current-season event files?
