## Context

See `proposal.md` — Why. Constraints that shape the approach:

- **Two export surfaces already exist and must stay distinct.**
  - `mlb export --preset backbone` — content-based rights review, 8 of 10
    counting-stat tables, Hugging Face `v0.1.0`. Keys are `core.*`
    surrogates. `gold.player_season` / `gold.team_season` excluded
    (`openspec/changes/archive/2026-09-06-delivery-surface/rights-review.md`).
  - `mlb export --profile public_safe` — lineage-strict: every feeding
    source must be Retrosheet. Today: `raw.retrosheet_event`,
    `raw.retrosheet_gameinfo`, `gold.run_expectancy_24`,
    `gold.win_expectancy`, `gold.leverage_index`. Backbone gold tables are
    deliberately `local_research` (`export.py` comments; statistic-backbone
    spec).
- **Issue #89's "already built" tables are the wrong public keys.**
  `gold.player_season` (BRef + WAR), `gold.team_season` (Lahman + BRef WAR),
  `gold.division_standing` (MLB Stats API standings from 1969) are
  local-research. Confirm they stay built and doctored; do not put them
  on the public mart.
- **The public-safe analog of those tables already exists as counting
  stats:** `gold.batting_season` / `gold.pitching_season` /
  `gold.batting_team` / `gold.pitching_team` / game grains (ADR-281
  parallel lines). The mart *projects* that content onto Retrosheet keys
  and *adds* the advanced stats issue #89 names. It does not become a
  second writer into the backbone.
- **2026 backbone rows are MLB box scores** (ADR-289). MLB Stats API is
  not public-safe (`docs/SOURCE_RIGHTS.md`). The mart stops at the last
  Retrosheet event season.
- **FanGraphs Guts! / park factors are `local_research`** (ADR-290). A
  publishable wOBA / FIP is computed from Retrosheet events with a cited
  formula, never selected from `gold.fangraphs_*`.
- **SQL ownership:** named `.sql` under `mlb_baseball/sql/`, run by
  `mlb report`. No SQL strings in Python. Gold stays denormalized
  (ADR-057). SQLMesh is not a requirement of this change.

## Goals / Non-Goals

**Goals**
- Three queryable fact grains a stranger actually uses: player-game,
  player-season, team-season, plus Retrosheet identity tables for
  player / team / game.
- Advanced stats from issue #89 on player-game and player-season: wOBA,
  FIP, RE24, wSB, K%/BB%, GB%/FB%/LD%.
- `mlb export --profile public_safe` writes those tables with a manifest
  and Retrosheet attribution.
- Doctor fails if the mart is empty or if the public dump grows a
  Statcast / BRef / Lahman / FanGraphs / MLB-boxscore column or table.
- Runbook examples that a stranger can paste without touching
  local-research tables.

**Non-Goals**
- Changing `--preset backbone`, Hugging Face, or `mlb_research.BACKBONE_TABLES`.
- Reclassifying `gold.batting_*` / `gold.pitching_*` as `public_safe`.
- Publishing `gold.player_season`, `gold.team_season`,
  `gold.division_standing`, `gold.game_export`, `gold.game_feature`,
  `gold.fangraphs_*`, postseason Lahman tables, or `feat.*`.
- A new hosted SQL endpoint (constitution: $0 hosting, no hosted DB).
- Year-precise FanGraphs Guts! weights or cFIP.
- wRC+ on the mart in this change (needs a public-safe park factor
  contract; `gold.park_factor` currently feeds Engine `game_feature`).
- Career-grain mart tables (out of issue #89; career is already on the
  backbone preset).
- `gold.baserunning_game` as a new statistic-backbone relation.

## Decisions

### D1 — New `gold.mart_*` tables, not a rewrite of the backbone

The mart is an additive reporting surface, same job ADR-057 gave
`gold.player_season` but rights-clean.

| Table | Grain / key | What a stranger gets |
|---|---|---|
| `gold.mart_player` | one row per Retrosheet `retro_id` | name, bats/throws, debut/end years from Retrosheet bio — **not** Chadwick |
| `gold.mart_team` | one row per Retrosheet team-era code | name, league, first/last year from `TEAMABR` / team reference |
| `gold.mart_game` | one row per `retro_game_id` | date, season, home/away team codes, score, park from `raw.retrosheet_gameinfo` (regular season only) |
| `gold.mart_player_game` | `(retro_game_id, retro_id, retro_team_id, role)` | counting line + advanced columns; `role` is `batting` or `pitching` |
| `gold.mart_player_season` | `(retro_id, season, retro_team_id, role)` plus one combined row per `(retro_id, season, role)` (`retro_team_id` NULL, `is_combined = true`) | season roll-up of the game grain; rates recomputed from sums |
| `gold.mart_team_season` | `(retro_team_id, season)` | team batting + pitching counting stats and the same advanced rates, one wide row |

*Why six tables, not three:* identity separate from facts so a stranger
can list players without scanning 12.9M game rows. Batting and pitching
share a table via `role` so the issue's "player / team / game" naming
holds, instead of eight backbone-shaped clones.

*Alternative considered:* views over `gold.batting_game` joining
`core.player.retro_id`. Rejected — that join is exactly why the backbone
is `local_research`. The mart must compile from Retrosheet raw tables so
`--profile public_safe` lineage is mechanical, not a comment.

*Alternative considered:* add wOBA/FIP columns onto `gold.batting_game`.
Rejected — game grain is contracted as counting-stats-only
(`docs/TABLE_CONTRACTS.md`); rates belong on a query surface. Widening
the backbone would also put 2026 `mlb_boxscore` rows next to public
metrics.

### D2 — Build from Retrosheet raw only; filter game type at the source

Builders read `raw.retrosheet_event` + `raw.retrosheet_gameinfo` with
`lower(gametype) = 'regular'` (same pattern as
`sql/team_woba_retrosheet_update.sql`). They SHALL NOT join `core.game` /
`core.player` / `core.team` / `core.play` / `core.pitch`.

Coverage: event-derived **1910 through the last published Retrosheet
event season** (2025 as of this writing). `mart_game` / identity may be
wider where the reference file is wider; fact tables follow the event
file. 2026+ MLB box-score rows that live on the backbone **do not**
appear on the mart.

Regular season only, including Game 163 (ADR-283). No postseason (Lahman
post tables are not public-safe; Retrosheet post events are a later
change if someone wants a public postseason mart).

### D3 — Advanced-stat formulas (cited, Retrosheet inputs, honest nulls)

All rates NULL on a zero denominator. Do not impersonate FanGraphs names
unless the formula matches. Do not ship Statcast `hc_x` / `hc_y` / EV /
LA / xwOBA.

| Metric | Grain | Formula / source | Public-safe input | Null policy |
|---|---|---|---|---|
| **K% / BB%** | season (and team-season); optional on game as a rate of that game's PA | `SO/PA`, `BB/PA` — already on `gold.batting_season` | event `so` / `bb` / `pa` | NULL if `pa = 0` |
| **wOBA** | player-game (components + rate), player-season, team-season | `(0.690·uBB + 0.722·HBP + 0.878·1B + 1.242·2B + 1.569·3B + 2.015·HR) / (AB + uBB + SF + HBP)` — same fixed modern weights already in `mlb_baseball/model/offense.py` (FanGraphs library formula / The Book linear-weight idea; **not** a dump of `gold.fangraphs_guts`) | `raw.retrosheet_event` event_cd 14/16/20–23, `ab_fl`, `sf_fl`, `bat_event_fl` | NULL if denominator 0 |
| **FIP** | pitching rows only | `(13·HR + 3·(BB+HBP) − 2·K) / IP + c` where `c` is a **seasonal Retrosheet constant chosen so league FIP = league RA9** that season | event HR/BB/HBP/K/outs | NULL if `outs = 0`; never FanGraphs `cfip`; never ERA-based (no ER in the event stream through 2025) |
| **RE24** | batting and pitching rows | sum of change in `gold.run_expectancy_24` across the player's charged events (existing `team_leverage_re24_update.sql` pattern, player-charged instead of team) | `gold.run_expectancy_24` (already `public_safe`) + events | NULL if the season has no RE24 matrix row |
| **wSB** | batting rows | linear-weight stolen-base runs from event SB/CS flags (The Book / Tango wSB; weights cited in the table contract). This change **does not** wait on a separate `gold.baserunning_game` | event `sb_fl` / `cs_fl` (or equivalent event_cd) | NULL if the event file has no steal coding for that game |
| **GB% / FB% / LD%** | batting and pitching | `GB / BIP`, etc., from Retrosheet `battedball_cd` | `battedball_cd` | NULL when BIP with a code is 0; **documented undercount / missingness pre-1988** (same caveat as `gidp`) |

Store additive numerators/denominators on the game grain (`woba_num`,
`woba_den`, `re24`, `sb`, `cs`, `gb`, `fb`, `ld`, `bip`) and recompute
rates at season/team. Never average game-level rates.

**Out of this change's advanced set:** WAR (BRef), wRC+ (park factor
lineage), xwOBA / expected stats (Statcast), FanGraphs Stuff+ / PitchingBot,
ERA through 2025 (no ER in events).

### D4 — `public_safe` dump includes the mart; `backbone` preset does not

`mlb export --profile public_safe` allow-list **adds** the six `gold.mart_*`
tables next to the existing five Retrosheet relations.

`mlb export --preset backbone` **does not** gain mart tables and **does
not** gain `player_season` / `team_season`. Hugging Face `v0.1.0` stays
the eight counting-stat files. Publishing the mart to Hugging Face is a
follow-up delivery change after the dump path is proven — not in scope
here (issue #89 asked for a queryable mart and a `public_safe` dump, not
a new publish pipeline).

`packages/mlb-research.load()` stays on `BACKBONE_TABLES`. Do not teach
the loader a second, unpublished table set in this change.

### D5 — Doctor and export guards

`mlb doctor` (or `report.health_check`) SHALL fail when:

1. any `gold.mart_*` fact table has zero rows after a successful
   `mlb report` on a database that has `raw.retrosheet_event` rows;
2. a `gold.mart_*` column name matches a denylist of Statcast / expected
   fields (`hc_x`, `hc_y`, `launch_speed`, `launch_angle`, `estimated_woba`,
   `xwoba`, `barrel`, `spin_rate`, …);
3. a `gold.mart_*` row's documented `source` is anything other than a
   Retrosheet product;
4. `--profile public_safe` would write `gold.player_season`,
   `gold.team_season`, `gold.division_standing`, `gold.game_export`,
   `gold.game_feature`, `gold.fangraphs_*`, `gold.batting_postseason`,
   `gold.pitching_postseason`, or any `source = 'mlb_boxscore'` backbone
   row.

A unit test of the export registry is the standing lock for (4), matching
`tests/unit/test_fangraphs_conform_rights.py`.

### D6 — Runbook is a public-safe document first

`docs/RESEARCH_QUERY_RUNBOOK.md` examples for redistribution / "stranger
query" SHALL use `gold.mart_*`. Existing `gold.player_season` /
`gold.team_season` / `gold.division_standing` / `gold.game_export`
snippets stay only in a clearly headed **local-research (do not
redistribute)** section.

### D7 — SQL placement

Named resources `mlb_baseball/sql/mart_player.sql`, `mart_team.sql`,
`mart_game.sql`, `mart_player_game.sql`, `mart_player_season.sql`,
`mart_team_season.sql` (names may split batting/pitching inserts inside
one file). `mlb report` truncate-and-replace in one transaction, same as
other gold reporting. Python orchestrates; it does not embed SQL.
`docs/SQL_OWNERSHIP.md` gets a row. Not a SQLMesh model in this change
(no incrementality requirement; full rebuild matches `mlb report`).

## Rights review (planning)

Content test: does the **exported column data** originate from a source
`docs/SOURCE_RIGHTS.md` marks yes for public-safe redistribution?

| Candidate | Content source | Verdict |
|---|---|---|
| `gold.mart_*` (this change) | Retrosheet events / gameinfo / bio / TEAMABR | **Yes, with attribution** |
| `gold.batting_*` / `gold.pitching_*` 1910–2025 counting stats | Retrosheet events, but core-keyed | Stay on **backbone preset only**; not `public_safe` |
| 2026 `source='mlb_boxscore'` backbone rows | MLB Stats API | **No** — excluded from mart |
| `gold.player_season` | Baseball-Reference | **No** |
| `gold.team_season` | Lahman + BRef WAR | **No** |
| `gold.division_standing` | MLB standings | **No** |
| `gold.game_export` / `gold.game_feature` | mixed, includes Statcast/MLB API | **No** (Engine) |
| `gold.fangraphs_guts` / `gold.fangraphs_park_factors` | FanGraphs | **No** |
| `gold.batting_postseason` / `gold.pitching_postseason` | Lahman | **No** |
| Chadwick-keyed player directory | Chadwick Register | **No** — `mart_player` uses Retrosheet bio instead |
| `gold.run_expectancy_24` | Retrosheet events | **Yes** (already public_safe; mart RE24 *reads* it) |

Derived relations inherit the most-restrictive source. The mart therefore
must not join a non-Retrosheet table "just for a name."

## Risks / Trade-offs

- **[Risk] Strangers compare mart wOBA to FanGraphs player pages and call
  it a bug.** Fixed modern weights ≠ year-varying Guts! weights. Mitigation:
  table contract + runbook state the formula, the fixed weights, and that
  this is not a FanGraphs scrape.
- **[Risk] FIP centered on RA9 is not FanGraphs FIP (cFIP centers on ERA).**
  Honest: no ER in Retrosheet events through 2025. Mitigation: name the
  constant `fip_constant_ra9` (or similar) and document it; do not label
  the column as matching FanGraphs FIP to three decimals.
- **[Risk] Steal / batted-ball coding is sparse in early events.**
  Mitigation: NULL, never zero-fill; pre-1988 BIP caveat already used for
  `gidp`.
- **[Trade-off] Two public counting-stat copies** (backbone Parquet vs
  mart). Accepted — different keys, different rights bar, different
  advanced columns. Mart builders should reuse event classification
  (`bat_event_fl` / `ab_fl` / `event_cd`) so numbers match the backbone
  on shared seasons, within documented rounding.
- **[Risk] `mlb report` runtime grows.** Mitigation: mart SQL is
  set-based over the same event table already scanned for the backbone;
  measure before splitting to SQLMesh.
- **[Risk] Someone adds the mart to `--preset backbone` "for convenience"
  and ships 2026 MLB rows or duplicates HF.** Mitigation: spec + doctor
  + an explicit non-goal; `BACKBONE_CANDIDATES` is not edited.

## Migration Plan

1. Rights lock: registry tests that list in/out tables (this design's
   table). No data change.
2. Identity tables (`mart_player` / `mart_team` / `mart_game`) from
   Retrosheet reference files.
3. `mart_player_game` counting stats (parity sample vs
   `gold.batting_game` / `gold.pitching_game` where `source =
   'retrosheet_event'`), then advanced columns.
4. Season / team roll-ups from the game grain.
5. Wire `mlb report`, doctor, `--profile public_safe`.
6. Rewrite the runbook; data dictionary; table contracts; SQL ownership;
   ADR.

Rollback: `DROP` the `gold.mart_*` tables; revert the export allow-list.
Backbone and HF are untouched.

## Open Questions

- Exact Retrosheet bio file (`biofile` vs `biodata`) for `mart_player`
  columns — pick the already-ingested table at apply time; do not add a
  source.
- Whether `role` stays one table or splits to `mart_batting_*` /
  `mart_pitching_*` if the wide row is ugly in review. Spec allows either
  physical shape as long as both roles are queryable at each grain.
- Hugging Face mart publish: **out of this change**; record as a delivery
  follow-up on `openspec/project.md` NEXT only after the dump path works.
