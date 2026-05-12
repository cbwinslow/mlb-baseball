# SQL Notes

This directory contains documentation notes for each raw DDL source family.
Each file describes the design strategy, key tables, column reference, load strategy,
and schema drift notes for its corresponding `sql/70_tables_raw/` SQL DDL file.

## Raw DDL notes by source

| File | Source | DDL file(s) |
|------|--------|-------------|
| [001_raw_retrosheet.md](./001_raw_retrosheet.md) | Retrosheet event files | `002_raw_retrosheet_events.sql`, `003_raw_retrosheet_games.sql`, `004_raw_retrosheet_rosters.sql` |
| [002_raw_statcast.md](./002_raw_statcast.md) | Baseball Savant / Statcast | `001_raw_statcast_pitches.sql`, `03_raw_statcast.sql` |
| [003_raw_lahman.md](./003_raw_lahman.md) | Lahman Database | `005_raw_lahman_batting.sql` through `019_raw_lahman_parks.sql` |
| [004_raw_mlbstatsapi.md](./004_raw_mlbstatsapi.md) | MLB Stats API | `01_raw_mlbstatsapi.sql` |
| [005_raw_fangraphs.md](./005_raw_fangraphs.md) | FanGraphs leaderboards | `020_raw_fangraphs_batting.sql`, `021_raw_fangraphs_pitching.sql`, `04_raw_fangraphs.sql` |
| [006_raw_espn.md](./006_raw_espn.md) | ESPN (unofficial API) | `026_raw_espn.sql` |
| [007_raw_bbref.md](./007_raw_bbref.md) | Baseball Reference / pybaseball | `022_raw_bbref_batting.sql`, `023_raw_bbref_pitching.sql`, `024_raw_bbref_schedule.sql` |

## Reference docs

- [raw-ddl-source-matrix.md](./raw-ddl-source-matrix.md) — governing design rules and source authority matrix
- [raw-ddl-next-steps.md](./raw-ddl-next-steps.md) — outstanding DDL tasks and migration next steps

## DDL file layout

All raw SQL DDL files live in `sql/70_tables_raw/`. The naming convention is:

```
NNN_raw_{source}_{table}.sql
```

Where `NNN` is a zero-padded sequence number that controls execution order.
Files prefixed `0N_` (e.g. `01_raw_mlbstatsapi.sql`) are legacy files pending rename.

## Schema design principles

1. **Typed tables for file/CSV sources** — Retrosheet, Lahman, Statcast, FanGraphs, bbref
2. **JSONB-first for API sources** — MLB StatsAPI and ESPN store full payloads as JSONB alongside extracted scalar identifiers
3. **Preserve upstream IDs** — never rename source-native keys at the raw layer
4. **Load batch tracking** — each source family has a `*_load_batches` companion table
5. **No strong typing on API responses** — promote to staging/core layers for typed extraction

## Cross-source join keys

| Key | Sources |
|-----|---------|
| `game_pk` (MLB integer) | Retrosheet, Statcast, MLB StatsAPI |
| `playerid` (FanGraphs integer) | FanGraphs batting, pitching, fielding |
| `bbref_id` (text, e.g. `troutmi01`) | Baseball Reference |
| `athlete_id` (ESPN text) | ESPN rosters, athletes |
| `retro_id` (text) | Retrosheet events, rosters |

See `sql/60_tables_xwalk/` for cross-source player ID mapping tables.

## Related docs

- [Sources index](../sources/README.md)
- [Architecture overview](../architecture/architecture-overview.md)
