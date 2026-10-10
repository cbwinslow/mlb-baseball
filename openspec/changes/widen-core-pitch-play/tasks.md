## 1. Facts before code

- [x] 1.1 Generate the raw-vs-core column inventory for `raw.statcast_pitch`, `raw.retrosheet_event`, `raw.mlb_playbyplay`; list proposed exclusions with reasons. Verify: every raw column is carried or listed with a reason.
- [x] 1.2 Check key uniqueness on production (read-only): (`game_pk`, `at_bat_number`, `pitch_number`) in `raw.statcast_pitch`; (`game_id`, `event_id`) in `raw.retrosheet_event`. Verify: duplicate counts recorded in `design.md`.
- [x] 1.3 Compare `raw.retrosheet_plays` with `raw.retrosheet_event` (row counts, shared keys). Verify: result recorded; decide include/exclude as a follow-up.
- [ ] 1.4 Confirm export rights profiles (`mlb_baseball/export.py` allow-list). Verify: `core.pitch`/`core.play` are `local_research`; a test pins that and that `core.play_retro` is unregistered.

## 2. Pitch

- [x] 2.1 Migration: add typed nullable columns to `core.pitch`. Verify: applies on a disposable database; existing columns unchanged.
- [x] 2.2 Move `_build_pitches` to a named SQL file inserting all columns; keep the LEFT JOIN on `core.game`. Verify: row count equals `raw.statcast_pitch`.
- [ ] 2.3 Tests: run-twice, blank-to-NULL, column-inventory (done, passing on the disposable PostgreSQL); still open: value parity against real raw rows on a copy of production (do with 4.1). Verify: pass on a disposable PostgreSQL.

## 3. Play

- [ ] 3.1 Migration: add `core.play_retro` (partitioned like `core.play`) and the MLB-only nullable columns on `core.play`. Verify: applies; original 19 columns unchanged.
- [ ] 3.2 Named SQL for Retrosheet detail insert and MLB extra fields; keep the Negro League de-duplication. Verify: one detail row per Retrosheet play, none for MLB plays.
- [ ] 3.3 Tests: run-twice, parity vs `raw.retrosheet_event`, roll-up tie-out to game scores, column-inventory test.

## 4. Close out

- [ ] 4.1 Measure `conform` time and table sizes before/after on a copy. Verify: numbers recorded in `design.md`.
- [ ] 4.2 Update `conform.py.dox.md`, `docs/TABLE_CONTRACTS.md`, `docs/DATA_DICTIONARY.md`, and the parent `core-coverage.md`. Verify: docs match the live schema.
- [ ] 4.3 Full production `conform` only after owner approval; then `mlb doctor`. Verify: doctor clean.
