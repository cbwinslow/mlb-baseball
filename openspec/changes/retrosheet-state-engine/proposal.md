## Why

`retrosheetpy` (change `pure-python-retrosheet`, merged) reads event files and parses play text, but it
cannot say what the game looked like after each play, and it cannot replace Chadwick. The owner's goal is a
free, pip-installable, pure-Python replacement for the Chadwick tools (no compiler, no database, no
dependency on mlb-baseball) that other baseball researchers can use on its own, and that stays correct on
next year's Retrosheet files.

## What Changes

- Add `retrosheetpy.cw`: a function-by-function Python port of the Chadwick C library (`cwlib`: parser,
  game/file/scorebook/roster/league readers and writers, game iterator, box score, lint) and of all six
  Chadwick tools (`cwevent`, `cwgame`, `cwdaily`, `cwsub`, `cwcomment`, `cwbox` including `-X` and `-S`),
  with their command-line drivers. Console scripts use Chadwick's own names; `retrosheetpy TOOL ...` and
  `python -m retrosheetpy.cw TOOL ...` also work.
- The rules are translated from Chadwick's source, never inferred from its output (design D3, owner
  decision 2026-10-01; the earlier infer-from-output engine was replaced). Output is proven byte for byte
  against the real tools on every season 1910-2025, and with differential fuzzing and synthetic games.
- CI builds Chadwick at the reference commit and runs the package tests against it.
- No `mlb_baseball` change, no database, no new runtime dependency (standard library only).

## Capabilities

### New Capabilities

- `retrosheet-state`: Chadwick-equal readers, game-state iteration and tool output for Retrosheet event files.

### Modified Capabilities

(none)

## Impact

- New and changed code only under `packages/retrosheetpy/`, plus a CI job in `.github/workflows/ci.yml`.
- Docs: package `AGENTS.md`/`README.md`/`API.md` and the results notes in this change folder.
- Licence: the port is a derivative of GPL-2.0-or-later Chadwick; the package stays AGPL-3.0-or-later (compatible
  through "or later"). A human legal read is recommended before a public release.
- Later, separate changes: PyPI release and documentation site, "get a season" data-access helpers, and the fate
  of the older `play.py`/`validation.py`/`report.py`/`records.py`.
