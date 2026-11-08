# Session handoff — 2026-11-08

Replaces the 2026-10-05 handoff, which described the odds-history backfill push.
Direction and phase gates are owned by `openspec/project.md`; this file records
only what is in flight and what the next session should pick up.

## State

- `main` is green again as of `3c91363` (PR #402). That fixed the backup restore
  across pg_dump/client-version mismatches, declared Chadwick's undeclared
  `cw_game_line_append` in the retrosheetpy harness, and made the tmpfs test
  tablespace fall back cleanly after a reboot.
- The 2026 regular season and postseason are complete in the database; the audit
  is `changelog/2026-11-08-2026-data-completeness.md`.
- Publishing data to Hugging Face is paused by owner decision (2026-11-08). The
  current `backbone` export preset still includes 2026 rows built from
  `raw.mlb_boxscore_*`, and `docs/SOURCE_RIGHTS.md` marks MLB redistribution as
  "no" — do not publish that preset without an explicit decision.
- Unit suite: 1130 passed, 4 skipped. Integration `test_backup.py`: 11 passed.
  retrosheetpy differential suite against the pinned Chadwick commit: 835 passed,
  0 skipped.
- `stabilize-and-market-store` (PR #396) is 26 commits ahead of `main` and
  conflicting. Land it in slices, not whole. Two `tests/unit/test_nightly.py`
  assertions there expect the older step order and need reconciling with the new
  nightly code before that slice can merge.

## Next, in order

1. Docs truth pass: `README` export section, `docs/COMMANDS.md` (regenerate with
   `python -m mlb_baseball.command_index > docs/COMMANDS.md`), the stale 2026
   limitation, and this file.
2. `mlb doctor` runtime: a full run exceeded 600s on the production database,
   with repeated whole-table `count(*)` scans over `raw.kalshi_candle` /
   `raw.polymarket_price`. Profile which check owns those counts before changing
   anything; `--populated` completes in ~5s.
3. Fresh-database rehearsal (`openspec/changes/fresh-database-bootstrap`):
   `preflight → migrate → bootstrap --since-year 2025 → coverage → conform →
   audit → doctor` on a disposable database, fixing each break at its own layer.
4. Release mechanics for v1: build `packages/mlb-research`, add PyPI trusted
   publishing, tag the release, then verify `pip install mlb-research` and
   `import mlb_research` in a clean venv. Until that exists the docs site's
   `pip install mlb-research` instruction is false.
