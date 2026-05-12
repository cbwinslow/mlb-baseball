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

The current repo appears to have Python ingestion modules but not a finalized, visible tracked raw SQL layer for all source families, which is why the next cleanup step should be to promote these starter DDLs into the repo under `sql/030_raw_schemas/` and make the `baseball` CLI bootstrap command execute only those files.[3][1]r,
    po2_fld_cd          integer,
    po3_fld_cd          integer,
    assist1_fld_cd      integer,
    assist2_fld_cd      integer,
    assist3_fld_cd      integer,
    assist4_fld_cd      integer,
    assist5_fld_cd      integer,
    event_raw_json      jsonb,
    created_at_utc      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rawretrosheet_events_bevent_game_id
    ON rawretrosheet.events_bevent (game_id);

CREATE INDEX IF NOT EXISTS idx_rawretrosheet_events_bevent_bat_id
    ON rawretrosheet.events_bevent (bat_id);

CREATE INDEX IF NOT EXISTS idx_rawretrosheet_events_bevent_pit_id
    ON rawretrosheet.events_bevent (pit_id);

CREATE TABLE IF NOT EXISTS rawretrosheet.games_bgame (
    bgame_id            bigserial PRIMARY KEY,
    batch_id            bigint REFERENCES rawretrosheet.import_batches(batch_id),
    game_id             text NOT NULL,
    game_dt             date,
    game_number         integer,
    day_of_week         text,
    visiting_team_id    text,
    league_id_away      text,
    away_game_number    integer,
    home_team_id        text,
    league_id_home      text,
    home_game_number    integer,
    away_score_ct       integer,
    home_score_ct       integer,
    outs_ct             integer,
    daynight_park_cd    text,
    completion_tx       text,
    forfeit_tx          text,
    protest_tx          text,
    park_id             text,
    attendance_ct       integer,
    game_minutes_ct     integer,
    away_line_scores_tx text,
    home_line_scores_tx text,
    away_ab_ct          integer,
    away_h_ct           integer,
    away_d2_ct          integer,
    away_d3_ct          integer,
    away_hr_ct          integer,
    away_bi_ct          integer,
    away_sh_ct          integer,
    away_sf_ct          integer,
    away_hp_ct          integer,
    away_bb_ct          integer,
    away_ib_ct          integer,
    away_so_ct          integer,
    away_sb_ct          integer,
    away_cs_ct          integer,
    away_gdp_ct         integer,
    away_ci_ct          integer,
    away_lob_ct         integer,
    away_pitchers_ct    integer,
    away_er_ct          integer,
    away_ter_ct         integer,
    away_wp_ct          integer,
    away_balk_ct        integer,
    away_po_ct          integer,
    away_a_ct           integer,
    away_e_ct           integer,
    away_pb_ct          integer,
    away_dp_ct          integer,
    away_tp_ct          integer,
    home_ab_ct          integer,
    home_h_ct           integer,
    home_d2_ct          integer,
    home_d3_ct          integer,
    home_hr_ct          integer,
    home_bi_ct          integer,
    home_sh_ct          integer,
    home_sf_ct          integer,
    home_hp_ct          integer,
    home_bb_ct          integer,
    home_ib_ct          integer,
    home_so_ct          integer,
    home_sb_ct          integer,
    home_cs_ct          integer,
    home_gdp_ct         integer,
    home_ci_ct          integer,
    home_lob_ct         integer,
    home_pitchers_ct    integer,
    home_er_ct          integer,
    home_ter_ct         integer,
    home_wp_ct          integer,
    home_balk_ct        integer,
    home_po_ct          integer,
    home_a_ct           integer,
    home_e_ct           integer,
    home_pb_ct          integer,
    home_dp_ct          integer,
    home_tp_ct          integer,
    ump_home_name_tx    text,
    ump_1b_name_tx      text,
    ump_2b_name_tx      text,
    ump_3b_name_tx      text,
    win_pitcher_id      text,
    loss_pitcher_id     text,
    save_pitcher_id     text,
    gw_rbi_batter_id    text,
    created_at_utc      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_rawretrosheet_games_bgame_game_id
    ON rawretrosheet.games_bgame (game_id);
```
