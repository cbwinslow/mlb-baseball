## 1. Rewrite `openspec/project.md`

- [ ] 1.1 "Who it's for" — replace the one-line "Secondary: the data scientist who clones the repo" with the two-product model: `mlb-research` (public toolkit) and the internal Engine, plus the one-sentence ship/internal test from design.md D1. Verify: the section names both products and states the test.
- [ ] 1.2 "Delivery" — add the point-in-time feature store and one reference baseline model to the list of what the public distribution includes. Verify: the section lists both alongside the Parquet/loader/DuckDB-WASM/docs items.
- [ ] 1.3 "Current phase … Phase is done when:" — remove `announced to r/Sabermetrics`; add `point-in-time feature store shipped in a public release` and `one reference baseline model (Elo v2) + model card shipped`. Verify: the criteria list no longer mentions Reddit/announcement and does mention the feature store and baseline.
- [ ] 1.4 Replace the "Frozen — no work until the phase milestone is met" section with "Phased ladder" — Phase A / B / C with the contents and entry criteria from design.md D2; the `~110 "Engine" composite packages` line moves into Phase B item 1 (triage). Verify: no "Frozen" heading remains; three phases each carry an explicit entry criterion; every ambition previously in the frozen list appears in a phase.
- [ ] 1.5 "Longer vision (recorded, not scheduled)" — fold the four bullets into the ladder per design.md D5; keep only the one-line pointer that Phase C paid betting-advice needs the per-US-state legal homework. Verify: the section is either removed or reduced to that single pointer, and nothing it named is lost from the ladder.
- [ ] 1.6 Add the SQL-vs-Python layer-split note per design.md D4 (under "Database engineering standards" or a short "Modeling layer" subsection). Verify: the note states deterministic aggregation → versioned `.sql` (ships) and iterative/stochastic → Python reading feature tables (writes `gold.prediction`).
- [ ] 1.7 Update the `NOW / NEXT / LATER` block so the queue is consistent with the ladder (NEXT points at Phase A's feature store + baseline; LATER points at Phase B). Verify: `NOW/NEXT/LATER` names no item that contradicts a phase gate.

## 2. Update `mlb_baseball/model/AGENTS.md`

- [ ] 2.1 Replace the "Predictive-model expansion remains secondary / do not expand the Engine catalog" framing with the ship/internal line: the backtest harness, feature store, Markov/sim engine, and the one reference baseline **ship**; tuned artifacts, tuned configs, non-baseline backtest results, and the model ladder above the baseline stay **internal**. Reference `openspec/project.md`'s ship/internal test rather than restating it. Verify: the file points to `project.md` for the test and states which model assets ship.
- [ ] 2.2 Reconcile the "do not create sidecars for every Engine module" and "do not expand the Engine catalog" lines with Phase B item 1 (triage is now a sanctioned lane, gated on Phase A). Verify: the lines no longer read as an absolute freeze; they defer to the phase gate.

## 3. Doc-sync sweep

- [ ] 3.1 `grep -rn -iE 'frozen|freeze|r/Sabermetrics' --include='*.md' . | grep -v docs/archive | grep -v openspec/changes/archive` and update every load-bearing reference to the old frozen list (at least: root `AGENTS.md`, `docs/AGENTS.md`, `docs/GITHUB_GOVERNANCE_RUNBOOK.md`) to point at the phased ladder. Leave incidental uses of the word alone. Verify: the grep output contains no reference that still describes a binary freeze of model/site/Engine work.

## 4. Verification

- [ ] 4.1 `openspec validate --all` passes and `openspec validate two-product-model --strict` passes. Verify: both exit 0.
- [ ] 4.2 Read `project.md` end to end: the two-product model, the ladder, and the v1 criteria are mutually consistent, and no previously-listed ambition (the ~110 Engine packages, the prediction ladder, live betting, the subscriber site) has been dropped. Verify: a written note in the PR confirming each of the four is present in a phase.
