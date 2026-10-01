## 1. Scope and harness

- [x] 1.1 Record Chadwick's `-f 0-96` and `-x 0-66` field lists (from `cwevent -d`) in a table in this change folder, each marked in-scope, state-dependent, or excluded; verify the table lists all 97 and 67 fields.
- [x] 1.2 Finalise the exclusion list (fields needing files outside the event file) with the reason for each; verify by running `cwevent` on a fixture and showing every excluded field is justified.
- [x] 1.3 Extend `validation.py` to compare whole rows over a field list, with an error when a column is missing on either side; verify with a unit test that a dropped column fails.
- [x] 1.4 Capture small Chadwick references for the existing 8 fixtures for all in-scope fields with recorded hashes; verify the integrity test passes and fails when a file is edited.

## 2. Game state and lineups

- [x] 2.1 Implement lineup and defense tracking from `start`, `sub` and adjustment records; verify against Chadwick fields for batter, pitcher, fielders and lineup positions on the fixtures.
- [x] 2.2 Implement outs, inning/half tracking, base occupancy and score before each play, plus new-game and end-game flags; verify those fields match Chadwick on the fixtures.
- [x] 2.3 Add strict/diagnostic handling for impossible state (runner from an empty base, fourth out); verify with unit tests for both modes.

## 3. Play effects

- [x] 3.1 Apply batter and runner destinations from play text and advances; verify destination fields (58-61) match Chadwick on the fixtures.
- [x] 3.2 Compute outs on play, double/triple play flags and runs scored; verify fields 40-42 and score fields.
- [x] 3.3 Compute RBI (field 43) from Retrosheet's published rules; verify on fixtures and record any rule learned from Chadwick output.
- [x] 3.4 Add errors (fields 51-57), putouts and assists (88-95), fielded-by (46); verify against Chadwick.
- [x] 3.5 Add pinch hitter/runner and removed-player fields (80-87) and responsible pitcher (75-77); verify against Chadwick.
- [ ] 3.6 Add the extended fields (`-x 0-66`) that remain in scope; verify against Chadwick.

## 4. Equality runs

- [ ] 4.1 Add an on-demand command that runs a season through the engine and Chadwick and writes a mismatch report; verify it on a fixture and on the 1950 sample.
- [ ] 4.2 Run 2019 and drive mismatches to 0, recording each learned rule with example plays in a results note; verify the report shows 0 mismatches and 0 misaligned games.
- [ ] 4.3 Resolve `B` and `B1S` (48 plays, 1976): determine Chadwick's treatment, implement or report explicitly; verify against the 1976 output.
- [ ] 4.4 Run every other available season in held-out batches, widening only after the previous batch is clean; verify per-season reports, and list any season that cannot reach 0 with its cause.

## 5. Verification and close-out

- [ ] 5.1 Run package tests, `ruff`, `ruff format --check`, `mypy --strict`; verify clean output.
- [ ] 5.2 Confirm no import of `mlb_baseball`, pandas, psycopg or native code and no Chadwick needed at run time; verify with the existing import test.
- [ ] 5.3 Review the diff for copied or line-by-line translated Chadwick code and for silently skipped plays; verify with an independent reviewer that also runs the code.
- [ ] 5.4 Update `packages/retrosheetpy/AGENTS.md` and write the final results note (seasons validated, exclusions, unresolved seasons); verify `openspec validate retrosheet-state-engine --strict` passes.
