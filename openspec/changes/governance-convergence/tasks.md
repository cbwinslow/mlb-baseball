## 1. Establish the shared governance hierarchy

- [x] 1.1 Add the project North Star and concise engineering invariants to
  `openspec/project.md`; verify each detailed rule points to an existing
  owning contract rather than duplicating it.
- [x] 1.2 Add the document/decision precedence and stale-contract reconciliation
  rule; verify archived plans cannot override current constitution/specs.
- [x] 1.3 Add a shared contract-impact Definition of Done; verify it names grain,
  identity, source/rights, formula/writer, null/PIT, build behavior, public
  interface, failure semantics, and reproducibility.

## 2. Reconcile subsystem contracts

- [x] 2.1 Reconcile `docs/TABLE_CONTRACTS.md` with ADR-287 and
  `docs/FEATURE_STORE.md`: PostgreSQL `gold` may contain deterministic
  statistics/internal compatibility/model outputs, but the canonical
  researcher-facing PIT model feature layer is DuckDB `feat.*`.
- [x] 2.2 Add concise subsystem North Stars to table contracts,
  `SQL_OWNERSHIP.md`, `FEATURE_STORE.md`, and `RESEARCH.md`; verify each
  states one outcome and does not redefine another subsystem.
- [x] 2.3 Strengthen `docs/SQL_OWNERSHIP.md` with the single-production-writer
  cutover rule: candidate parity -> audits -> promote -> remove legacy writer.
- [x] 2.4 Ensure doctor/audit/readiness meanings are aligned between the
  constitution and `docs/AUDIT_RUNBOOK.md`; do not duplicate implementation
  details.

## 3. Promote Platform Convergence

- [x] 3.1 Add a current Platform Convergence gate to
  `docs/PRODUCTION_CONVERGENCE.md` while preserving the dated 2026-08-06
  recovery record below it.
- [x] 3.2 Add Platform Convergence to the constitution's current queue before
  broad Phase B expansion; verify the gate links existing active changes
  rather than spawning duplicate work.
- [x] 3.3 Reconcile stale queue text so `pipeline-recovery`, not the older
  `pipeline-freshness` wording, is the current operational source of truth.

## 4. Capture the holistic review with zero orphan findings

- [x] 4.1 Record the review-disposition table in `design.md`; verify every
  high-priority review area maps to an existing owner/change or a specifically
  named future change.
- [x] 4.2 Confirm future change names do not overlap an existing active
  OpenSpec change before any are opened; prefer extending an existing change.
- [x] 4.3 Update the GitHub governance runbook to state that issues index
  significant OpenSpec changes but do not duplicate `tasks.md`.

## 5. Verification

- [x] 5.1 Review changed docs for contradictory current-state claims and broken
  relative links.
- [ ] 5.2 Run `openspec validate governance-convergence` and the repository's
  documentation/DOX checks when available; record any environment limitation
  rather than claiming an unrun check passed. Current tool runtime does not
  provide the `openspec` CLI; PR #305 CI/link checks are the available remote
  verification and `verification.md` records the limitation.
- [x] 5.3 Open PR #305 summarizing the governance hierarchy, reconciled
  feature boundary, Platform Convergence gate, and review disposition map.

## 6. Imported outside-review follow-up

- [x] 6.1 Add `chatgpt/README.md` that classifies all four imported reviews as
  evidence rather than governing docs and records what is absorbed versus
  residual.
- [x] 6.2 Promote season-dependent constants/context into the SQL ownership
  contract and independent calculation-oracle use into the research doctrine;
  verify neither change adopts a new runtime dependency or data source.
- [x] 6.3 Extend the disposition map with bounded future
  `sabermetric-formula-consolidation` and `library-source-evaluation`
  changes, both explicitly behind current phase gates.
- [ ] 6.4 Verify this follow-up's links/docs and OpenSpec change on PR CI; record
  any unavailable local validation honestly.
