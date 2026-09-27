## 1. Audit and pass marks

- [x] 1.1 Write `audit.md` in this change: for each raw Retrosheet table, which behaviors the existing tests prove and which they do not (landing, reload scope, missing input, column names, content correctness), citing the test files; verify every `raw.retrosheet_*` table appears in it.
- [x] 1.2 Record which raw table each `core.play` and `core.game` column is built from, citing `conform.py` lines; verify each cited line exists.
- [x] 1.3 Commit the pass mark for every comparison (exact match) and the initial explained-differences register (game-log regular season only; box scores end 1961; any others found) before the full-history run; verify they appear in git history before the first full run.

## 2. The gate

- [x] 2.1 Add `mlb_baseball/tieout.py` with the register, the comparison logic (pure functions over counts) and read-only query runners; verify unit tests cover match, unexplained mismatch, explained mismatch, register entry whose rule stops matching, and "not comparable".
- [x] 2.2 Add `scripts/verify_retrosheet_tie_out.py` (explicit database target, read-only transaction, season range option, non-zero exit on failure, elapsed-time output); verify a dry run against a disposable database prints the target and exits 0 on a clean fixture.
- [x] 2.3 Add season-total comparisons across events, CSV plays, CSV batting, game logs (regular and postseason) and box scores where they overlap; verify with a two-source fixture, including a planted mismatch that fails.
- [ ] 2.4 Add per-game and per-player-game comparisons (run for every season, never skipped because the season total matched or is in the register) and the roster identity check; verify with a fixture that a missing roster identifier and a single dropped strikeout are both reported with season and game, and that two opposite game-level errors inside a matching season total are both reported.
- [ ] 2.5 Add the `core` completeness check (`core.play`, `core.game` vs raw; plate-appearance counts plus a keyed comparison of every scoped event row including non-batter plays; duplicates; sampled attribute equality); verify with a fixture where one baserunning play is dropped with plate-appearance counts unchanged, and one play is duplicated.
- [ ] 2.6 Add the read-only production schema check for each compared `raw.retrosheet_*` table against the pinned column contract; verify with a fixture table that has an extra and a missing column.

## 3. Test gaps

- [ ] 3.1 Add pinned column-contract tests for the event, game, and CSV tables (disposable database and the connector's field list; production is covered by 2.6); verify a test fails when a column is renamed in a fixture.
- [ ] 3.2 Close the audit gaps that could hide incorrect data (at minimum an integration test that loads a small real event fixture and checks known counts); verify the new tests pass and each gap in `audit.md` is marked closed or has an issue number.

## 4. Real run and record

- [ ] 4.1 Run the gate read-only against production `mlb` for 2015–2025; record the command, elapsed time and full output in `results-2015-2025.md`; verify it exits 0 or that every difference is explained or has an issue.
- [ ] 4.2 Run it for every remaining season where two sources overlap; record in `results-history.md`; verify every difference is in the register with evidence or has an issue.
- [ ] 4.3 Update `scripts/AGENTS.md` index or the Retrosheet connector DOX sidecars if a contract was clarified; verify `scripts/check_dox.py` passes.
- [ ] 4.4 Note the result in the `play-engine` change (task 2.3 gate) and in `openspec/project.md` NOW/NEXT; verify `openspec validate raw-source-tieout` passes and record the finish-line checklist result in this change.
