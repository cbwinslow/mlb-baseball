# Raw DDL source matrix for `baseball`

This document defines the most defensible raw SQL DDL strategy for the `retrosheet` / `mlb-baseball` project.

## Governing rule

Use official upstream SQL when it truly exists. When upstream publishes field layouts or CSV column documentation instead of executable SQL, author project SQL directly from those official specs. When the source is API-first, preserve source-native JSON payloads in raw tables and defer strong typing to staging and core layers.[1][2]

## What the current repo implies

The current workspace already contains source-specific Python modules such as `retrosheet.py`, `lahman.py`, `mlb.py`, `fangraphs.py`, and `espn.py`, which supports a source-isolated raw-layer design rather than a single mixed schema.[3] The prior planning notes in the space also converge on a split raw layer with separate files for Retrosheet, Chadwick, Lahman, Savant, FanGraphs, MLB Stats API, ESPN, Baseball Reference, DraftKings, and Polymarket.[1][4]

## Source matrix

| Source family | Upstream authority | Official executable SQL? | Recommended raw design | Decision |
|---|---|---:|---|---|
| Retrosheet | Event file docs, BEVENT/BGAME field definitions | No | Source-faithful typed raw tables mirroring official field layouts | Author from spec [1] |
| Chadwick / register | `cwevent` docs and Chadwick register docs | No universal Postgres package | Typed raw tables compatible with Chadwick outputs | Author from spec [1] |
| Lahman / Databank | Official Lahman table structure plus community SQL mirrors | Sometimes community SQL, not one universal upstream package | Mirror Lahman-compatible table structure in Postgres SQL files | Adapt from structure [1] |
| Baseball Savant / Statcast | Official CSV docs | No | Typed raw CSV landing tables by export family | Author from docs [1] |
| FanGraphs | Export headers and leaderboard families | No | Report-family raw tables, not one master schema | Author by export family [1] |
| MLB Stats API | API endpoint/payload docs | No | `jsonb` request and payload landing tables plus optional extracted helpers | JSON-first [1] |
| ESPN MLB | Community endpoint docs | No | `jsonb` request and payload landing tables | JSON-first [1] |
| Baseball Reference / pybaseball outputs | Scraper-facing tables, not official SQL | No | Report-family raw tables matching extractor outputs | Author by output family [1] |
| DraftKings | Unofficial reverse-engineered API docs | No | `jsonb` request and payload tables plus extracted event/market snapshots | JSON-first [1] |
| Polymarket | Official API market/event model | No universal warehouse SQL | `jsonb` raw tables plus extracted market/event helpers close to API model | JSON-first + helper tables [1] |

## Recommended raw file layout

```text
sql/
  030_raw_schemas/
    001_raw_retrosheet.sql
    002_raw_chadwick.sql
    003_raw_lahman.sql
    004_raw_savant.sql
    005_raw_fangraphs.sql
    006_raw_mlb_stats_api.sql
    007_raw_espn.sql
    008_raw_baseball_reference.sql
    009_raw_draftkings.sql
    010_raw_polymarket.sql
```

## Rules for every raw SQL file

- Include a header comment with upstream authority, URL, access date, and whether the file is copied, adapted, or authored.[1]
- Preserve upstream names where practical; avoid warehouse-style renaming in the raw layer.[2]
- Keep raw ingestion tables separate from normalized and analytical tables.[2]
- Use typed relational tables for stable file/CSV sources and `jsonb` landing tables for API-first sources.[1]
- Keep all SQL in tracked files instead of Python string literals, which aligns with the repo direction discussed in the attached planning material.[3][1]

## What to fix in the current project

The current repo appears to have Python ingestion modules but not a finalized, visible tracked raw SQL layer for all source families, which is why the next cleanup step should be to promote these starter DDLs into the repo under `sql/030_raw_schemas/` and make the `baseball` CLI bootstrap command execute only those files.[3][1]


---

## Resolution Status (Updated 2026-05-12)

The legacy `0N_` prefix conflict in `sql/70_tables_raw/` has been resolved:

| Old filename | Action | New filename | Reason |
|---|---|---|---|
| `03_raw_statcast.sql` | **Deleted** | — | True duplicate of `001_raw_statcast_pitches.sql` (same `raw.statcast_pitches` table, new file is more complete) |
| `01_raw_mlbstatsapi.sql` | **Renamed** | `027_raw_mlbstatsapi.sql` | Unique content (7 MLB StatsAPI tables). No `NNN_` equivalent existed. |
| `02_raw_retrosheet.sql` | **Renamed** | `028_raw_retrosheet_legacy.sql` | Different schema from `002–004` (uses `raw.retro_*` not `raw.retrosheet_*`). Kept for lookup tables not in new files. |
| `04_raw_fangraphs.sql` | **Renamed** | `029_raw_fangraphs_legacy.sql` | Different column names from `020/021` (uses `raw.fg_batting` not `raw.fangraphs_batting`). Kept for reference. |

All files in `sql/70_tables_raw/` now use the `NNN_` (3-digit) prefix scheme and sort correctly. The bootstrap runner (`baseball/db/bootstrap.py`) will process them in the correct order: `001_` → `029_`.

### Remaining note on legacy schemas

`028_raw_retrosheet_legacy.sql` and `029_raw_fangraphs_legacy.sql` use different table names (`raw.retro_*`, `raw.fg_*`) compared to the new files (`raw.retrosheet_*`, `raw.fangraphs_*`). Both schemas are preserved intentionally until the ingestion layer is updated to use a single canonical naming convention. The `_legacy` suffix makes this ambiguity visible.
