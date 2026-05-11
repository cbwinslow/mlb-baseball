# 50 — Core Tables

SQL DDL for the canonical production tables. These mirror the SQLAlchemy ORM models
in `baseball/db/models.py` and must stay in sync.

## Tables (to be added in Phase 2)

| File | Table | Description |
|---|---|---|
| `01_player.sql` | `core.player` | Canonical player records |
| `02_player_xwalk.sql` | `core.player_xwalk` | Player ID crosswalks (MLBAM, Retrosheet, Lahman, FanGraphs, BBRef) |
| `03_team.sql` | `core.team` | Canonical team records |
| `04_team_xwalk.sql` | `core.team_xwalk` | Team ID crosswalks |
| `05_park.sql` | `core.park` | Stadium/park records |
| `06_park_xwalk.sql` | `core.park_xwalk` | Park ID crosswalks |
| `07_schedule.sql` | `core.schedule` | Season schedule |
| `08_game.sql` | `core.game` | Game-level records |
| `09_play_by_play.sql` | `core.play_by_play` | Play-by-play events |
| `10_pitch.sql` | `core.pitch` | Pitch-level StatCast data |
| `11_player_season.sql` | `core.player_season` | Season batting/fielding stats |
| `12_pitcher_season.sql` | `core.pitcher_season` | Season pitching stats |

## Status

⚠️ **Pending** — tracked in [Phase 2 milestone](https://github.com/cbwinslow/mlb-baseball/milestones).
