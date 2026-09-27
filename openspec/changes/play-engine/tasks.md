## 1. Foundations and pre-registration

- [ ] 1.1 Verify the Retrosheet event-code mapping to outcome classes against Chadwick documentation and real `core.play` counts; write the mapping and the excluded codes into the design, and verify the counts are plausible (strikeout, walk and home-run shares per season).
- [ ] 1.2 Confirm the readiness gate: run #246 tasks 4.2 and 4.3 read-only against production `mlb` and record the result; if blockers are reported, list them and clear every one that affects this engine's inputs before task 2.3, the first dataset build, so no result is built on an input that must later change.
- [ ] 1.3 Commit the calibration and simulation tolerances to this change before any test-season scoring; verify they appear in the change's git history before the first test-season result.
- [ ] 1.4 Add `mlb_baseball/pa/AGENTS.md` and register it in the parent index; verify `scripts/check_dox.py` passes.

## 2. Plate-appearance dataset

- [ ] 2.1 Read the primary source for the odds-ratio blend (The Book, 2007, or an open-access equivalent), record the citation, and add a test reproducing a worked example from it; verify the test passes, or mark the citation secondary if the source cannot be read.
- [ ] 2.2 Check the same formula against real `mlb` values (a sample of real plate appearances) and record the comparison; verify it is reproducible from one command.
- [ ] 2.3 Build the plate-appearance dataset for 2015–2025 with pre-PA inputs from `feat.player_form` / `feat.pitcher_form`, base-out state, park, and handedness from `raw.retrosheet_allplayers`; verify a test for one game against a hand-built expected row set.
- [ ] 2.4 Add dataset-level leakage checks (every input's source timestamp, every form-row join, and no post-appearance field such as the resulting base-out state), keep the existing form-store checks, and add a doubleheader test proving a second game cannot see the first; verify all pass and that a deliberately leaky fixture fails.
- [ ] 2.5 Report coverage and missingness per season and per input; verify the report lists every input with its missing share and no missing value is zero-filled.

## 3. Scoring protocol

- [ ] 3.1 Extend `mlb_research.backtest` with multiclass log loss, per-class calibration and a paired comparison, and re-export; verify unit tests against hand-computed values.
- [ ] 3.2 Implement the league-average baseline and score it on the 2022–2023 validation seasons; verify the log loss is recorded and reproducible from one command.

## 4. Ratings blend

- [ ] 4.1 Implement the ratings blend with shrunk batter, pitcher, league and park rates; verify hand fixtures, probabilities sum to 1, and a player with no history falls back to the prior.
- [ ] 4.2 Score it against the baseline with the paired comparison on the 2022–2023 validation seasons; verify the result and record adopt or negative result in the feature ledger.

## 5. Feature groups, one at a time

- [ ] 5.1 Create the feature ledger and add game situation, platoon, and park and weather as separate groups, measuring each on the 2022–2023 validation seasons; verify each group has a source citation, a leakage-check result and a measured effect in the ledger.
- [ ] 5.2 Add the advanced groups one at a time (Statcast quality of contact, pitch quality, umpire zone, catcher framing, defense, fatigue, times through the order), drawing sources from the existing admission and literature documents first; verify each has its ledger row and rejected groups are marked with their numbers.

## 6. Gradient-boosted engine

- [ ] 6.1 Train the multiclass boosted model on 2015–2021 with the admitted groups, tuning on the 2022–2023 validation seasons only; verify no test-season data is read during tuning.
- [ ] 6.2 Adopt or reject the boosted model against the ratings blend on the validation seasons, then score the selected engine once on 2024–2025 and calibrate; verify the test seasons were scored only after selection and record the result.

## 7. Simulation

- [ ] 7.1 Estimate the advancement table and the between-appearance event rates from training seasons only, then build the base-out chain and Monte Carlo simulation on the shipped engine, reusing sound parts of `model/markov/core.py`; verify unit tests for state transitions (including double plays and a steal between appearances) and that simulated probabilities sum to 1.
- [ ] 7.2 Compare simulated runs per game and home win rate with real 2024–2025 values against the committed tolerance, and report next to `markov-v1`; verify the report.

## 8. Wrap-up

- [ ] 8.1 Commit the model card and final feature ledger; verify the card states seasons, classes, scores, limits and intended use.
- [ ] 8.2 Update `openspec/project.md` NOW/NEXT and any owning DOX/docs; verify `scripts/check_dox.py`, lint, and the change's tests pass.
- [ ] 8.3 Run `openspec validate play-engine` and verify it passes; record the finish-line checklist result in the change.
