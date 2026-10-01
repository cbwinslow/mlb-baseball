# Session handoff — 2026-10-01

Branch: `feat/raw-source-tieout`. All tasks of `openspec/changes/raw-source-tieout`
are ticked (4.2, 4.3, 4.4 done this session). Untracked `.idea/` is IDE config, not ours.

## Where things stand

- **Retrosheet tie-out gate passes for 1871–2014** (run 8, exit 0, 24 min) and gives
  one known difference for 2015–2025: `BOS202509030` runs 8 vs 9, GitHub issue #267 (a
  `cwevent` obstruction-play parsing gap). Results: `results-history.md`,
  `results-2015-2025.md`, raw logs beside them. Code commit under test: `1ed8ff7`.
- Every difference is an evidenced register entry (E1–E8 in `passmarks.md` section 2)
  or a stale load; no raw data was edited to satisfy the gate.
- **One production write this session (owner-approved):** the 2000s event archive was
  force-reloaded into `mlb` (`raw.retrosheet_event` / `raw.retrosheet_game`, 2000–2009).
  105 of 1,936,585 event rows changed (Retrosheet's own upstream corrections, e.g.
  `TBA200205030`); none added or removed. `core.*` / `gold.*` were NOT rebuilt from it.
- Not done: other decade archives were not compared against Retrosheet's current files
  (the gate passes against them as loaded); Retrosheet's published notes were not found
  online, so E8 (1947 `99#` row) is "not yet checked against their notes".
- Not run: the full test suite. Run: the two tie-out test files (79 pass), ruff, mypy on
  the two tie-out modules, `scripts/check_dox.py`, `openspec validate raw-source-tieout`.

## Decisions for the owner

1. Rebuild `core`/`gold` for 2000–2009 from the corrected raw rows? (105 events; the
   `play-engine` change task 1.2 notes it.) Needs the normal conform/report path.
2. Compare the other decade archives against Retrosheet's current files (same read-only
   diff used for the 2000s; ~minutes per archive) and reload any that changed.

## Ground rules to remember

- Production `mlb` is real data. Every gate run is read-only; always pass `--expect-db mlb`.
- Gate = checker, never a fixer. Raw is stored as published; a difference is explained,
  filed, or a stale load that is reloaded through its connector.
- Keep replies to the owner short and plain (see `CLAUDE.md`).
- Postgres is shared and on spinning disks; the gate's full history run is ~24 min.
