# Design

## Context

Observed 2026-10-10 on production `mlb`: `core.pitch` and `core.play` are range-partitioned by season (158 partitions each, plus default). `conform._build_pitches` and `_build_plays` truncate-and-insert from inline SQL; `raw.statcast_pitch` has 121 text columns plus `_loaded_at`, so every value is cast at insert time. `raw.retrosheet_event` has 168 columns (all text-coded flags and ids), `raw.mlb_playbyplay` 22. Conform's order, LEFT JOINs and de-duplication of 1,872 Negro League games are correctness-critical (`conform.py.dox.md`). See proposal.md for motivation (ADR-305).

## Goals / Non-Goals

**Goals:** lossless typed carry-forward of pitch and play fields; source keys back to raw; zero change for existing `core.pitch`/`core.play` readers.

**Non-Goals:** linking pitches to plays; new `core` tables outside pitch/play; `gold`/feature work; speeding up `conform` (parent change section 7); replacing the truncate-rebuild pattern.

## Decisions

1. **Pitch: add columns to `core.pitch` in place.** `ALTER TABLE ... ADD COLUMN` (nullable, no default) is metadata-only on partitions. Alternative (a separate `core.pitch_detail`) rejected: one pitch is one fact; a wide fact table is not denormalization, and a join on 13.6M rows would tax every pitch query.
2. **Play: common table plus one-to-one Retrosheet detail.** `core.play` keeps the source-neutral columns; new `core.play_retro` (keyed to `core.play.id`, same season partitioning) holds all Retrosheet event fields. Alternative (union all 190 columns into `core.play`, mostly NULL for MLB-sourced rows) rejected as hard to read and wasteful. MLB-only fields (event type, bat side, pitcher hand, RBI) go into `core.play` as nullable common columns.
3. **Typing at conform time, not in raw.** Raw stays source-faithful text. Numeric columns use the existing `NULLIF(x,'')::numeric` pattern; Retrosheet flag columns (`*_fl`) become boolean, codes stay text/integer per the Chadwick definitions in `retrosheet_event.py.dox.md`.
4. **Source keys.** Pitch: keep `source_game_pk`, `at_bat_number`, `pitch_number` (add a unique index only if the data supports it; verify in tasks). Retrosheet play: `game_id` + `event_id` stored on `core.play_retro`.
5. **Column inventory is generated, not hand-typed.** A script lists raw columns vs core columns and fails the test if a raw column is neither carried nor in the documented exclusion list.
6. **Named SQL files**, run in the existing order, one per source insert (consistent with `conform-design.md` in the parent change).

## Findings (read-only checks, 2026-10-10, production `mlb`)

- **Pitch key:** `raw.statcast_pitch` has 13,649,388 rows and 13,649,388 distinct (`game_pk`, `at_bat_number`, `pitch_number`); none of the three is blank. The key is unique, so it can be the source key.
- **Retrosheet key:** `raw.retrosheet_event` has 16,708,003 rows but 16,540,582 distinct (`game_id`, `event_id`). All 167,037 repeated keys appear once in the `negro_league` group and once in the `pbp` group: the known double-published Negro League games that `conform` already de-duplicates. The key is unique after that step.
- **Excluded Statcast columns (evidence):** `spin_dir`, `spin_rate_deprecated`, `break_angle_deprecated`, `break_length_deprecated`, `tfs_deprecated`, `tfs_zulu_deprecated` are blank in 100% of rows, so excluding them loses nothing. `age_pit_legacy` and `age_bat_legacy` are populated in every row and are therefore carried. Load metadata (`_season`, `_scope`, `_group`, `_loaded_at`) is excluded.
- **`raw.retrosheet_plays` is not a duplicate of `raw.retrosheet_event`.** It is a different layout (16.9M rows, 179 columns) with fields the event table lacks (umpires by base, per-batter lineup and fielder slots, date, game type, pre/post base state). It is a separate source of Retrosheet play detail; its overlap with the event table is a validator. Handled as a follow-up change, not in this one.
- **Exports:** `mlb_baseball/export.py` exports whole tables by an allow-list with a rights profile. `core.pitch` and `core.play` are already `local_research`, so widening them cannot reach a `public_safe` export. A new `core.play_retro` is not exported until someone registers it.

## Risks / Trade-offs

- [Run time and size grow] -> measure `conform` and table size before/after on a disposable copy; accept if within owner's limit, otherwise this feeds parent task 7.4.
- [Duplicate keys: Statcast may repeat (game, at-bat, pitch)] -> check on production data first; if not unique, keep `id` as the key and document.
- [Retrosheet flags with inconsistent meaning across eras] -> keep raw code values; no interpretation in `core`.
- [Rights leak via export] -> new relations are not exported until registered with a rights profile (tested).
- [Observed: parent-table indexes on `core.pitch`/`core.play` show INVALID in `\d` while all 474 partition indexes are valid] -> check whether queries use them; separate fix if it matters.

## Migration Plan

Numbered migration adds columns/table (nullable). `conform` fills on its next run; rehearse on a disposable database with a copied slice first. Rollback: drop the added columns/table (additive only).

## Open Questions

- Whether `raw.retrosheet_plays` becomes a second detail table (and its overlap with the event table becomes a tie-out): a follow-up change; does not affect this one.
