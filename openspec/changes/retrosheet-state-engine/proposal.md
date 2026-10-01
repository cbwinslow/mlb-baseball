## Why

`retrosheetpy` (change `pure-python-retrosheet`, merged) reads event files and
parses each play's text, and it matches Chadwick on every field that can be read
from one play string (0 mismatches on 7 seasons). It cannot yet say what the
game looked like after each play: outs, who is on base, who scored, RBI, who made
the putouts and assists. Those fields are the bulk of Chadwick's `cwevent` output,
so until they exist the package cannot replace Chadwick. The Slice B go/no-go note
(`pure-python-retrosheet/slice-b-go-no-go.md`) recommends doing it now, with a
hard equality target.

## Long-term goal and roadmap

The owner's goal is for `retrosheetpy` to be a free, pip-installable, pure-Python
replacement for the Chadwick tools, with byte-identical output, that other
baseball researchers can use on its own (no dependency on mlb-baseball, no
database, no native code). It also becomes a one-stop shop for Retrosheet files:
download, organize into a local folder, parse, and hand back usable data.

This change is step 1 of a series, each its own OpenSpec change:

1. **This change:** `cwevent` equivalent and the game-state engine it needs.
2. **CLI and one-stop data access:** `retrosheetpy` command namespace with
   Chadwick-compatible commands and options, a default cache folder
   (overridable), and a "get a season" command that downloads, unpacks,
   organizes and parses; a Python API returning plain data (pandas only as an
   optional extra).
3. **Other Chadwick tools** (`cwgame`, `cwbox`, `cwdaily`, `cwcomp`, `cwsub`),
   each proven identical to Chadwick on real seasons, reusing the engine.
4. **PyPI release:** packaging, metadata, versioning, docs, clean-install tests.

Chadwick-style commands must match Chadwick's output exactly; extra options and
convenience commands are additions that never change that output.

## What Changes

- Add a game-state engine to `packages/retrosheetpy`: it walks a game's records
  in order, keeps the lineup, defense, outs, runners and score, and produces one
  event row per play with the state before and after.
- Cover the `cwevent` fields `-f 0-96` and `-x 0-66` (documented by `cwevent -d`).
  Fields that need a team or roster file stay out of scope and are listed
  explicitly rather than left blank.
- Prove equality by comparing output with Chadwick 0.10.0 row by row, on the
  existing validation harness extended to whole rows. Order: 2019 first, then
  every season; any season that cannot reach 0 mismatches is reported, never
  waved through.
- Settle the open `B` and `B1S` modifiers (48 plays, 1976): find out what
  Chadwick does with them and handle them the same way, or surface them explicitly.
- No `mlb_baseball` change, no database, no new dependency, no connector switch.

The rules come from Chadwick's own C source, translated to Python (design D3,
owner decision 2026-10-01; GPL-2.0-or-later source, notices kept). Equality is
still proven by output against `cwevent`.

## Capabilities

### New Capabilities

- `retrosheet-state`: game-state tracking and event rows for Retrosheet event
  files, with Chadwick-equal output as the acceptance test.

### Modified Capabilities

(none: `retrosheet-parsing` is still an unarchived change, so this change does not
alter an archived spec.)

## Impact

- New and changed code only under `packages/retrosheetpy/` (new engine modules,
  validation extended to full rows, new reference captures and tests).
- Docs: package `AGENTS.md`/DOX index and a results note in this change folder.
- CI: package tests stay small; full-season comparisons are an on-demand command,
  not a CI step (they need Chadwick and downloaded data).
- Nothing in `mlb_baseball`, migrations, SQL or the warehouse changes.
