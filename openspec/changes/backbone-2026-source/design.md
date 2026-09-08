## Context

See `proposal.md` — Why. The game-grain builders (`sql/batting_game_build.sql`,
`sql/pitching_game_build.sql`) read `raw.retrosheet_event` and are wired into
`report.run()` through `_build_backbone_relation(conn, table, build_sql,
source=...)`, which pre-checks the source table, `TRUNCATE`s the target, runs
one build statement, and returns the row count. The season / team / career
relations already aggregate from `gold.batting_game` / `gold.pitching_game`
and are source-agnostic.

Relevant current state:

- `gold.batting_game` / `gold.pitching_game` **already carry a `source` text
  column** (added with the grain backbone). No migration needed for it.
- `gold.batting_game` columns line up almost 1:1 with
  `raw.mlb_boxscore_batting`: `pa←plate_appearances`, `ab←at_bats`, `r←runs`,
  `h←hits`, `b2←doubles`, `b3←triples`, `hr←home_runs`, `tb←total_bases`,
  `rbi←rbi`, `bb←base_on_balls`, `ibb←intentional_walks`, `hbp←hit_by_pitch`,
  `sf←sac_flies`, `sh←sac_bunts`, `so←strike_outs`, `gidp←ground_into_double_play`;
  `b1 = h − b2 − b3 − hr`.
- `gold.pitching_game` has **no `er` column**; `gold.pitching_season` /
  `_career` have `ra9` but no `er` / `era`. `raw.mlb_boxscore_pitching` carries
  `earned_runs`, `outs`, `batters_faced`, `games_started`, `wins`, `losses`,
  `saves`, and the same H/R/BB/SO/HR/HBP/WP/BK set.
- `raw.mlb_boxscore_batting` for 2026: 2,426 games, joining `core.game` on
  `game_pk` gives 1,939 regular-season games (the rest are spring / exhibition
  / all-star, excluded by `game_type = 'regular'`). ~215 regular-season
  `core.game` rows have no box score yet — an ingest-freshness gap, visible
  through the `mlb doctor` join-coverage check, not a builder defect.
- `raw.mlb_playbyplay` for 2026: one dense row per plate appearance, MLB
  StatsAPI `event_type` vocabulary, running `home_score` / `away_score`
  totals, `rbi` per play. Scoring runners appear only in free-text
  `description`. ~180 of 2,426 games have partial data (< 60 PA).

## Goals / Non-Goals

**Goals:**

- `gold.batting_game` / `gold.pitching_game` populated for 2026-onward
  regular-season games from `raw.mlb_boxscore_*`, `source = 'mlb_boxscore'`.
- One `TRUNCATE` per game relation, then both builders append — no builder
  writes a `(game, player, team)` key the other also writes.
- `er` / `era` on the pitching relations for 2026+, null for 1910–2025.
- A play-by-play cross-check gate for a sample of 2026 games.
- Season / team / career roll-ups pick up 2026 with no logic change beyond
  the `era` recompute.

**Non-Goals:**

- Reconstructing 2026 lines from `raw.mlb_playbyplay` as the *source* — it is
  the cross-check only (per the answered scope question). Run attribution from
  description text, the incomplete-game problem, and the full event map are
  avoided.
- Postseason / spring / all-star 2026 lines — regular season only, matching
  the rest of the backbone.
- Backfilling `er` for 1910–2025 (no earned-run data in the event stream).
- Stolen bases / caught stealing in the batting relations, even though the
  2026 box score carries them — still deferred to a future baserunning
  relation for cross-era consistency.
- A `public_safe` variant — the backbone stays `local_research` (core-dimension
  lineage), unchanged by this.

## Decisions

### 1. MLB box score is the 2026 source; play-by-play is the tie-out

Chosen over an event reconstruction from `raw.mlb_playbyplay`. The box score
is MLB's official scorer line — complete, carries runs and earned runs
directly, and maps to the gold columns with almost no transformation. A pbp
reconstruction would have to parse scoring runners out of free text, decide a
policy for ~180 partial games, and re-derive what MLB already computed. The
1910–2025 Retrosheet builder is itself validated against an external official
line (Baseball-Reference); doing the same for 2026 with pbp as the independent
check keeps the methodology parallel: *primary record builds the row, an
independent source proves it*.

Trade-off: the 2026 rows are pre-aggregated by MLB's scorer, not event-derived
like 1910–2025. The spec's "computed from a primary game record" requirement is
worded to allow this, and the table contract documents it.

### 2. Two builders, one truncate — extend `_build_backbone_relation`

`_build_backbone_relation` currently runs one build SQL after the `TRUNCATE`.
Extend it (or add a sibling) to take an ordered list of `(build_sql, source)`
pairs: pre-check each source, `TRUNCATE` once, run every build whose source is
present, sum the counts. The Retrosheet builder gains `AND g.season <= 2025`;
the new `batting_game_mlb_build.sql` / `pitching_game_mlb_build.sql` carry
`AND g.season >= 2026 AND g.game_type = 'regular'`. The season bound is the
partition line, so the two can never write the same key.

Alternatives rejected:
- *One builder that `UNION ALL`s both sources* — couples two unrelated source
  schemas in one file, and the `%(season)s` scoped-rebuild bind gets awkward.
- *`source='...'` append flag on `_build_backbone_relation` with the caller
  ordering two calls* — the second call would `TRUNCATE` away the first's rows.

### 3. `er` / `era` columns — additive migration, null-safe roll-ups

New migration: `er integer` on `gold.pitching_game`; `er integer` + `era numeric`
on `gold.pitching_season` and `gold.pitching_career`. The Retrosheet pitching
builder writes `er = NULL`. The MLB builder writes `er = earned_runs`.

Roll-ups: `gold.pitching_season.er = sum(er)` **only when every contributing
game row has `er`** (`CASE WHEN count(*) = count(er) THEN sum(er) END`) — a
pitcher-season that mixes a null-`er` Retrosheet game and a real-`er` MLB game
would otherwise report a silently-partial total. In practice no pitcher-season
straddles the 2025/2026 boundary, but the guard makes the intent explicit.
`era = er * 27 / outs` when `outs > 0 AND er IS NOT NULL`, else null. `ra9`
stays exactly as today for every year.

`gold.pitching_career.era` is null unless every season in the career has a
non-null `er` — i.e. career ERA only exists for a pitcher whose whole career
is 2026+. Documented as a known limitation, same class as the existing
"career tie-out is not exact" note.

### 4. Play-by-play cross-check

`scripts/verify_mlb_boxscore_tie_out.py` (or a new section in
`verify_baseball_reference_tie_out.py`). For a sample of complete 2026 games
(PA count within the expected band, so the ~180 partial games are excluded):
group `raw.mlb_playbyplay` by `(game_pk, batter_id)`, map `event_type` to
PA / AB / H / BB / SO / HBP / SF / SH / HR the same way the box score would,
and compare to the `mlb_boxscore`-sourced `gold.batting_game` rows
field-by-field. Fail if a counting stat is outside a small documented
tolerance on more than a small fraction of the sample. Runs against a built
database, not CI.

Tolerance rationale: `event_type` maps cleanly for the common cases;
`field_error` (AB, no H), `fielders_choice` / `force_out` (AB), `catcher_interf`
(PA, not AB), the empty `event_type` rows, and multi-out events
(`grounded_into_double_play`, `strikeout_double_play`) are the edge cases that
justify a non-zero tolerance rather than exact match.

### 5. `mlb doctor` checks

- Row count + `core.game` join coverage for the 2026 `mlb_boxscore`-sourced
  rows (the ~215 not-yet-ingested regular-season games surface here as a
  coverage shortfall, not a silent gap).
- A guard: `SELECT count(*) FROM (SELECT game_id, player_id, team_id FROM
  gold.batting_game GROUP BY 1,2,3 HAVING count(DISTINCT source) > 1)` must be
  0 — no key written by both builders.
- The existing regular-season envelope check already covers the new rows.

## Risks / Trade-offs

- **[Pre-aggregated source for 2026]** The 2026 rows are MLB's scorer line, not
  event-derived. → The pbp cross-check is the mitigation; the table contract
  and honest-limitations doc state the methodology split so a researcher
  comparing a 2025 and a 2026 season knows they came from different pipelines.
- **[`era` coverage cliff]** `era` is null 1910–2025, populated 2026+. A naive
  `AVG(era)` across eras is meaningless. → Documented in `TABLE_CONTRACTS.md`
  and the column comment; `ra9` (every year) is the cross-era rate.
- **[Incomplete box-score ingest]** ~215 2026 regular-season games have no box
  score yet; more accrue as the season runs. → `mlb doctor` join-coverage
  makes the gap visible; `mlb report` is re-run as ingest catches up. Not a
  builder bug.
- **[Partial pbp games poison the cross-check]** ~180 games have < 60 PA. →
  The cross-check samples only games whose PA count is in the expected band.
- **[StatsAPI `event_type` drift]** MLB could add or rename an `event_type`. →
  The cross-check's mapping has an explicit "unmapped `event_type`" failure
  path (loud, not silently 0), so a new value trips the gate rather than
  undercounting.
- **[Roll-up `er` partial-season]** A pitcher-season mixing null and non-null
  `er` game rows. → The `CASE WHEN count(*) = count(er)` guard nulls the whole
  season total rather than reporting a partial sum.

## Migration Plan

1. Migration `NNNN_pitching_er_era.sql` — `ALTER TABLE ... ADD COLUMN` for `er`
   (game / season / career) and `era` (season / career). Additive, reversible
   (`DROP COLUMN`), no data backfill. Applies in the pytest migrate.
2. Ship the two new `sql/*_mlb_build.sql` builders and the
   `_build_backbone_relation` extension behind the existing source pre-check —
   on a database without `raw.mlb_boxscore_*` the new builds skip cleanly and
   behaviour is unchanged (1910–2025 only).
3. `mlb report` on production picks up 2026 once run. Rollback: revert the
   builders + `DROP COLUMN er, era`; `gold.pitching_game` returns to
   Retrosheet-only.

## Open Questions

- Whether to fold the pbp cross-check into `verify_baseball_reference_tie_out.py`
  or ship it as a second script. Either satisfies the spec; decide during
  implementation based on how much of the harness (`TieOutCase`, connection
  handling) is reusable.
