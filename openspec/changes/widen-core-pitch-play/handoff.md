# Handoff — 2026-10-10 (widen-core-pitch-play)

Resume from `tasks.md`; this records where the session stopped.

## Done (commit db03c73 on `wip/uncommitted-2026-10-08`, not pushed)
- 1.1-1.3 read-only checks (findings in `design.md`); 2.1 migration `0117`; 2.2 `conform_pitch_insert.sql`.
- Tests added in `tests/integration/test_conform.py` (column inventory, typed values, blank-to-NULL, run-twice); 8 pitch-related tests pass. Full suite, mypy, and a production `mlb conform` NOT run.

## Next
1. Section 3 (play): migration for `core.play_retro` + MLB-only columns on `core.play`; named SQL; same three tests. `raw.retrosheet_event` key is unique after the Negro League de-dup; load-metadata columns are `_season`, `_group`, `_scope`, `_loaded_at`.
2. 1.4: test that pins `core.pitch`/`core.play` as `local_research` and `core.play_retro` unregistered (`mlb_baseball/export.py` RELATIONS).
3. 2.3 / 4.1: value parity and timing on a copy of production; production `conform` only with owner approval.
4. Push the branch and open a PR when section 3 is done (AGENTS.md pre-authorizes merge after `test`/`secrets`/`lint`).

## Decisions made this session
- ADR-305 (carry everything); weather and sportsbook closing lines approved if free and reliable (task 6.10 of `streamline-core-gold-direction`).
- SQLMesh: not used for `conform` builds in this change; revisit after the spike (parent task 3.2).
- Parent change: nightly timings measured (7.1) — failures were a lock clash and a network drop, not the update storm.
