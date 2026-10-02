## Context

Observed (2026-10-01): `retrosheetpy` has a lossless record reader, a play parser
that yields typed events, modifiers and runner advances (`Play`), and a
comparison harness (`validation.py`) that matches Chadwick on text-derived fields
only. `cwevent -d` lists 97 base fields (0-96) and 67 extended fields (0-66);
many are state-dependent (outs, runners, scores, RBI, putouts, assists, errors,
pinch-runner and responsible-pitcher fields). Chadwick 0.10.0 binaries are at
`~/.local/bin`; its source is public (GPL-2.0, this project is AGPL-3.0). See
`proposal.md` for motivation. The 1950 sample has 98,731 events locally; 2019
data must be downloaded.

## Goals / Non-Goals

**Goals:**

- A state engine whose rows equal `cwevent` output for the in-scope fields.
- A repeatable, whole-row comparison with Chadwick, per season, with a report.
- Rules written from Retrosheet documentation and observed Chadwick behaviour.

**Non-Goals:**

- Performance tuning (about 70k lines/s is accepted unless measurement says the
  full-history run is impractical).
- The CLI, default cache folder, "get a season" command, the other Chadwick
  tools (`cwgame`, `cwbox`, `cwdaily`, ...) and PyPI release: later steps in the
  roadmap in `proposal.md`. The engine API is kept plain and reusable so they can
  build on it.
- Dataframes, PostgreSQL loads, switching any mlb_baseball connector to the engine.
- Fields that need team/roster files, unless the exclusion list says otherwise.

## Decisions

**D1. Build the engine as a fold over parsed plays.** A `GameState` value is
advanced by applying each parsed `Play`; each step returns an event row. Pure
functions over immutable state make single plays easy to test and compare.
*Alternative:* one mutable game object copied from Chadwick's structure — rejected:
harder to test per play and closer to a translation of the C code.

**D2. Whole-row differential testing is the contract.** Extend `validation.py` to
compare every in-scope column, with an explicit exclusion list and a hard error
for any column absent on either side (the review found the old harness skipped
them silently). *Alternative:* hand-written expected values per rule — kept only
for small rule tests; they cannot prove equality at scale.

**D3. Clean-room rule for Chadwick.** Understanding behaviour from Chadwick source
or documentation is allowed. Code is written from our own parsed model and
Retrosheet's rules, never pasted or translated line by line. Each rule that was
learned from Chadwick behaviour is recorded in a results note with the plays that
revealed it. Equality is shown by output only.

**D4. Order of work: 2019 first, then widen.** Tune on a small set of fixtures
and 2019, then run seasons never used for tuning (as in section 5 of the previous
change) before claiming equality. Era rules (old scoring, deduced games, runner
placement oddities) are expected to appear late; stopping and reporting a season
that cannot reach 0 is the agreed outcome, not a failure to hide.

**D5. Field groups in dependency order.** (1) game and lineup state: batter,
pitcher, fielders, runners, outs, score, inning, new/end game flags;
(2) outs on play, destinations, RBI; (3) errors; (4) putouts and assists;
(5) pinch hitter/runner fields and responsible pitcher; (6) extended fields.
Each group gets its own passing season run before the next starts.

**D6. Strict by default.** Same rule as the play parser: unsupported or
impossible input raises in strict mode and is surfaced explicitly in diagnostic
mode (see spec).

**D7. Reference data is captured and checked in small, and large on demand.**
Fixture-level captures (as in `tests/reference/`) run in CI; full-season runs are a
documented command that needs Chadwick and downloaded files, and their results are
written to a note in this folder.

## Risks / Trade-offs

- [Early-era and unusual plays make exact equality slow to reach] → widen season
  by season, record each learned rule, report seasons that stop short.
- [Equality with Chadwick may copy its bugs] → where Chadwick contradicts
  Retrosheet's published rules or its own CSV, report the three-way difference,
  never silently pick one (existing project rule).
- [GPL contamination from reading source] → clean-room rule D3, written rules from
  documentation, differential tests only; reviewer checks for copied structure.
- [Chadwick or data unavailable in CI] → fixture captures in CI, live comparison
  skipped visibly (not vacuously) with a recorded version check.
- [Scope is large] → tasks are grouped by field group; each group is shippable and
  reported on its own.

## Open Questions

- Which extended fields (`-x`) are genuinely independent of roster files; the
  exclusion list is finalised in task 1.2 and does not change the approach.
