## 1. Establish the declared training contract

- [x] 1.1 Inventory the current `feat.game`, `feat.player_form`, and `feat.pitcher_form` schemas plus their existing test, catalog, source, and point-in-time evidence; record the observed result in the change and verify every candidate column is assigned admitted, excluded, or needs-evidence.
- [x] 1.2 Define and load a versioned `game-win-v1` feature-set declaration beside the public `mlb_research` package; require entity/grain, source relation, availability semantics, null policy, coverage window, and evidence references for every selected field. Verify valid and missing-field fixtures accept/reject as expected.
- [x] 1.3 Implement feature-set validation that rejects labels, post-game fields, market outcomes, and `gold.game_feature` compatibility columns for the first game-win set. Verify parameterized unit tests cover each prohibited category and an allowed `feat.*` field.

## 2. Produce model-readiness evidence

- [ ] 2.1 Extract/reuse the existing backbone tie-out, feature-store leakage, relation-integrity, and rate/null checks behind one readiness evaluator; it must not rebuild, ingest, conform, migrate, or write PostgreSQL. Verify a missing feature artifact and a failed required check produce named blockers.
- [ ] 2.2 Add the documented read-only readiness CLI/report interface with stable JSON and human-readable output, explicit DuckDB path/version, redacted source/build identity, and no ambiguous database target. Verify CLI help, JSON schema, and a clean synthetic build return the documented result.
- [ ] 2.3 Add per-season/per-feature coverage and null-rate evidence to the report, distinguishing declared null policy from unexplained missingness. Verify fixtures cover an expected early-season null, an unexplained null that blocks readiness, and a coverage-window exclusion.
- [ ] 2.4 Make the evaluator return `ready` only when every required evidence check and declared feature admission check passes; otherwise return `not_ready` with every blocker. Verify ready/not-ready integration cases against a disposable PostgreSQL + DuckDB build.

## 3. Make the researcher workflow unambiguous

- [ ] 3.1 Perform the bounded public-entry-point audit named in `design.md`; record each finding as blocking ambiguity, stale/duplicate documentation, or deferred cleanup, with the exact owner/path. Verify the inventory covers the CLI, public package API, feature-store docs, metric catalog docs, SQL locations, and tests.
- [ ] 3.2 Repair blocking/stale researcher-facing paths found in 3.1: document the feature declaration, readiness workflow, generated manifest, coverage limits, and the `feat.*` versus legacy `gold.game_feature` boundary. Verify docs links/build checks and public CLI/API wording are coherent.
- [ ] 3.3 Publish the finite completion hierarchy: feature-version freeze, chronological model-candidate promote/retain/reject decision, and unchanged Phase-A exit gate. Verify it links to `openspec/project.md` without duplicating or weakening the constitution.

## 4. Verify against real evidence and close the gate

- [ ] 4.1 Run focused unit/integration tests, catalog validation, formatter/lint/type checks, and OpenSpec validation for all changed paths. Verify all commands and results are recorded in the change.
- [ ] 4.2 Against an explicitly designated, fully-built verification database (never an ambiguous target), run the existing Baseball-Reference and 2026 box-score tie-outs, `mlb build`, and the new readiness report. Record the exact build/version, result, coverage profile, and any honest blockers.
- [ ] 4.3 If the report is ready, freeze `game-win-v1` and open the separate first-ML-experiment proposal; if not ready, record the bounded blockers and create only the focused follow-up changes required to clear them. Verify no model implementation begins in this change.
