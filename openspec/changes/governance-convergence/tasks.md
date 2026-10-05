## 1. Establish the shared governance hierarchy

- [ ] 1.1 Add the project North Star and concise engineering invariants to
  `openspec/project.md`; verify each detailed rule points to an existing
  owning contract rather than duplicating it.
- [ ] 1.2 Add the document/decision precedence and stale-contract reconciliation
  rule; verify archived plans cannot override current constitution/specs.
- [ ] 1.3 Add a shared contract-impact Definition of Done; verify it names grain,
  identity, source/rights, formula/writer, null/PIT, build behavior, public
  interface, failure semantics, and reproducibility.

## 2. Reconcile subsystem contracts

- [ ] 2.1 Reconcile `docs/TABLE_CONTRACTS.md` with ADR-287 and
  `docs/FEATURE_STORE.md`: PostgreSQL `gold` may contain deterministic
  statistics/internal compatibility/model outputs, but the canonical
  researcher-facing PIT model feature layer is DuckDB `feat.*`.
- [ ] 2.2 Add concise subsystem North Stars to table contracts,
  `SQL_OWNERSHIP.md`, `FEATURE_STORE.md`, and `RESEARCH.md`; verify each
  states one outcome and does not redefine another subsystem.
- [ ] 2.3 Strengthen `docs/SQL_OWNERSHIP.md` with the single-production-writer
  cutover rule: candidate parity -> audits -> promote -> remove legacy writer.
- [ ] 2.4 Ensure doctor/audit/readiness meanings are aligned between the
  constitution and `docs/AUDIT_RUNBOOK.md`; do not duplicate implementation
  details.

## 3. Promote Platform Convergence

- [ ] 3.1 Add a current Platform Convergence gate to
  `docs/PRODUCTION_CONVERGENCE.md` while preserving the dated 2026-08-06
  recovery record below it.
- [ ] 3.2 Add Platform Convergence to the constitution's current queue before
  broad Phase B expansion; verify the gate links existing active changes
  rather than spawning duplicate work.
- [ ] 3.3 Reconcile stale queue text so `pipeline-recovery`, not the older
  `pipeline-freshness` wording, is the current operational source of truth.

## 4. Capture the holistic review with zero orphan findings

- [ ] 4.1 Record the review-disposition table in `design.md`; verify every
  high-priority review area maps to an existing owner/change or a specifically
  named future change.
- [ ] 4.2 Confirm future change names do not overlap an existing active
  OpenSpec change before any are opened; prefer extending an existing change.
- [ ] 4.3 Update the GitHub governance runbook to state that issues index
  significant OpenSpec changes but do not duplicate `tasks.md`.

## 5. Verification

- [ ] 5.1 Review changed docs for contradictory current-state claims and broken
  relative links.
- [ ] 5.2 Run `openspec validate governance-convergence` and the repository's
  documentation/DOX checks when available; record any environment limitation
  rather than claiming an unrun check passed.
- [ ] 5.3 Open a focused PR summarizing the governance hierarchy, reconciled
  feature boundary, Platform Convergence gate, and review disposition map.
