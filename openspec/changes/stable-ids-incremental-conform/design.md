## Context

Observed 2026-10-02 (issue #275):

- The daily job takes 2 h 7 min: update 22 min, conform 44, report 14, predict 47 (`logs/mlb_daily_update.log`). `pg_stat_statements` puts the `core.play` insert at 25 min and `core.pitch` at 15 min.
- `conform.run()` truncates 23 tables in one statement and rebuilds them. `core.team`, `core.player`, `core.venue` and `core.game` use auto-numbered ids, so every night re-issues all of them; `core.play`/`core.pitch` reference `core.player` directly, which is why the truncate must name them all.
- `core.play` and `core.pitch` are already range-partitioned by season (158 partitions each). `core.game` and `core.market` are not partitioned.
- Production `core.game`: 237,457 games; 225,410 with a Retrosheet id; 229,988 with an MLB `game_pk`; 12,047 MLB-only; 75 games since 2015 unmatched (mostly regular-season, 29 in 2020, one All-Star game per year).
- Game linking runs five rule steps every night (`_backfill_game_pk`, `_backfill_mlb_team_id`, `_backfill_game_pk_via_mlb_team_id`, `_backfill_game_pk_via_exact_final_score`, `_backfill_team_ids_via_mlb_id`).
- `core.team_franchise` (166 franchises, unique `franchise_id` from Lahman) is data-driven; 59 team entries with a blank league have no franchise (unverified: likely All-Star and Negro League codes).
- Retrosheet republished all files on 2026-08-09; `mlb source-check` (merged) now detects that.

Textbook basis: stable surrogate keys plus merge/upsert instead of truncate-and-reload; reprocess by input change with idempotent steps (Kimball surrogate-keys guidance; Tobiko's incremental-load write-up).

## Goals / Non-Goals

**Goals:**
- Ids never change; a normal night rebuilds about one season.
- A republished past season is rebuilt, and only that season.
- Incremental and full rebuilds are provably equal.
- Less code: remove the mass truncate, the index drop/recreate, and nightly rematching.

**Non-Goals:**
- Changing what the gold statistics compute, or the Elo/`predict` model logic.
- Renaming tables (separate change).
- Replacing cron or adding a scheduler (issue #274).
- Optimising `predict` beyond measuring it.

## Decisions

**D1: The core tables are the key map; no separate map table.** A persistent `core.*` table with a unique natural key already maps natural key to id. A second table would duplicate it and need keeping in sync. Natural keys: team `(retro_team_id, first_year, last_year)` (exists); game `retro_game_id` and `game_pk` (both unique today); player `retro_id` or `mlbam_id` (either may be null; match on whichever is present, fill the other when it arrives); venue by its source key (confirm in task 2.1). Rejected: a `meta.key_map` table (extra moving part, no extra capability).

**D2: Upsert, not truncate.** `INSERT ... ON CONFLICT (natural key) DO UPDATE` for team, player, venue and game, writing only changed columns. Rows whose source disappeared are left in place and counted in the run output; deleting is an explicit, reviewed action, because removing a player or game would orphan history.

**D3: Fingerprint = row count plus latest `_loaded_at` per `_season` of each raw input, stored in `meta.input_fingerprint(layer, season, fingerprint, built_at)`.** Cheap (index-friendly), and any `--refresh` reload changes `_loaded_at`, so a republish is always seen; the cost is that a reload with identical content causes one harmless rebuild. Rejected: hashing every row (a full scan, which is the cost we are removing); using file dates (misses API sources and manual loads). Task 2.2 verifies the scan cost on production.

**D4: Season replace uses the existing partitions.** For `core.play` and `core.pitch`, load the new season into a staging table, then swap it in (detach old partition, attach new) inside one transaction. Unpartitioned tables (`core.game`, `core.market`) use delete-by-season then insert in one transaction. Readers never see an empty season.

**D5: `report` follows `conform`.** Today `conform` empties gold and `report` refills it, because ids changed. With stable ids gold stays valid; `conform` writes the list of rebuilt seasons to `meta`, and `report` rebuilds only those seasons for the season-grain gold tables. Career-grain tables (`gold.batting_career`, `gold.pitching_career`) depend on all seasons; they are recomputed only for players in the changed seasons. If measurement (task 1) shows `report` is fast enough, leave it as a full rebuild and record that.

**D6: Match once, record how.** Add a `game_pk_rule` text column on `core.game` and run the five matching rules only over games where `game_pk IS NULL`. Collapse the five functions into one ordered rule list. Unmatched games stay null (project rule: an honest NULL beats a guess).

**D7: `mlb conform --full` is the safety net and the test oracle.** It performs the old behaviour (all seasons). The equivalence test builds a fixture in two incremental steps and compares with one full run.

**D8: First stable run is a full rebuild.** Existing ids in production were issued by the truncate path; after the first run under the new code they become permanent. Anything that stored `core.*` ids (predictions, features) is rebuilt by the normal job that night; no id mapping from old to new is attempted.

## Risks / Trade-offs

- Incremental logic drifting from the full path → the equivalence test runs in CI on a fixture and in a one-off production comparison (task 6.1).
- Chained downstream state (Elo ratings, running totals, `predict`) depends on earlier seasons → out of scope here; `conform` exposes the earliest rebuilt season in its output so a later change can recompute forward from it. Until then a corrected old season leaves such state stale; this change records that as a known limit, not a silent one.
- Player matching with two nullable keys can merge or split people wrongly → match strongest key first, never merge two existing rows automatically, log conflicts (task 3.2).
- Partition swap on live tables → done in one transaction, staged first; rollback is leaving the old partition.
- First run is long (a full rebuild) → run it once, deliberately, after a backup.

## Migration Plan

1. Measure (tasks 1.x), no schema change.
2. Migration: unique natural-key constraints (if missing), `game_pk_rule`, `meta.input_fingerprint`.
3. Land upsert for team/player/venue/game behind `mlb conform --full` parity: the full path produces what the old truncate path produced (compare counts and checksums before and after).
4. Land season-level rebuild and fingerprints; switch the nightly script to the default (incremental) mode.
5. Remove the mass truncate and index drop/recreate once the equivalence test and a production comparison pass.
Rollback: `mlb conform --full` with the previous commit; nothing is deleted from raw.

## Open Questions

- Whether `report` career-grain tables are cheap enough to leave as full rebuilds (answered by task 1.3).
- Which venue key is the natural key (task 2.1 reads `conform_venue*` and the source tables).
