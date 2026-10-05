## Context

The repository already has the right document types:

- `openspec/project.md` — constitution and current phase/queue.
- root/child `AGENTS.md` — durable operating invariants and context routing.
- `openspec/specs/` — durable capability requirements.
- `docs/ARCHITECTURE.md`, `TABLE_CONTRACTS.md`, `SQL_OWNERSHIP.md`,
  `FEATURE_STORE.md`, `RESEARCH.md` — subsystem contracts and explanation.
- `docs/DECISIONS.md` — accepted rationale/ADRs.
- `openspec/changes/<name>/` — bounded implementation work.
- tests, SQLMesh audits, `mlb doctor`, `mlb audit`, and `mlb readiness` —
  executable proof.

The problem is not missing documentation infrastructure. The problem is
convergence: an important rule may appear in several places with different age
or scope, and review findings can disappear if they are not promoted into an
owner, a task, or a gate.

## Decisions

### D1: No standalone "laws" document

The project North Star and concise engineering invariants live in
`openspec/project.md`. Detailed implementation semantics remain in the
nearest owning contract. Other docs link instead of copying the full rule.

Reason: a second constitution would create another source of truth and violate
the repository's existing documentation doctrine.

### D2: Governance follows one ownership chain

The intended chain is:

```text
North Star / constitution
        ↓
durable invariant
        ↓
subsystem contract or accepted ADR
        ↓
active OpenSpec change
        ↓
tasks
        ↓
test / audit / doctor / readiness / CI gate
        ↓
recorded evidence
```

A finding is not considered captured until it has a durable owner or a bounded
work item.

### D3: Precedence is explicit

For current project behavior and intended direction:

1. `openspec/project.md` and current durable `openspec/specs/`;
2. accepted ADRs and subsystem contracts;
3. active OpenSpec change design for the bounded change;
4. shared/local `AGENTS.md` operational instructions;
5. implementation-facing prose and generated docs;
6. archived plans/reviews/history.

This precedence is not permission to ignore contradictory implementation
evidence. When verified code/data shows that a current contract is false,
record the discrepancy, decide the intended behavior, then repair the owning
contract and implementation together.

### D4: Platform Convergence is a gate, not another release

The existing `docs/PRODUCTION_CONVERGENCE.md` is retained and promoted with a
current Platform Convergence section above its historical 2026-08-06 audit.

The gate is complete only when the platform can safely support aggressive new
model/market/product work: required operational health is green; canonical IDs
are stable; incremental/full conformance is equivalent; transformation
ownership is unambiguous; invalid/disabled metrics cannot enter approved model
inputs; feature/readiness diagnostics are reliable; ingestion-item lineage and
backups are verifiable; and at least one representative SQLMesh promotion has
completed parity, audits, cutover, and legacy-writer removal.

### D5: Completion has human, machine, and evidence forms

For every important invariant, prefer:

- **rule** — human-readable requirement;
- **gate** — executable test/audit/doctor/readiness/CI check;
- **evidence** — result log, tie-out, immutable research metadata, or accepted
  ADR.

A checkbox alone is insufficient for correctness-critical work.

### D6: GitHub issues index work; OpenSpec specifies it

One issue may represent one significant OpenSpec change for discoverability,
dependencies, status, and contributor routing. The issue does not duplicate
the detailed `tasks.md`. This avoids two drifting task lists.

### D7: Doctor, audit, and readiness keep separate meanings

- `mlb doctor`: operational installation/source health.
- `mlb audit`: data-contract and integrity correctness.
- `mlb readiness`: whether a declared dataset/feature set is admissible for a
  particular research/model workflow.

Optional or experimental components must not make a healthy installation look
operationally broken.

### D8: Review-finding disposition is explicit

The 2026-10-05 review maps as follows:

| Review area | Durable owner / work |
|---|---|
| pipeline defects, backup check, stale feature artifact, prediction counts, ingestion ledger, framing | existing `pipeline-recovery` |
| stable entity IDs, fingerprints, atomic/incremental conform | existing `stable-ids-incremental-conform`, strengthened by `pipeline-recovery` tasks 6.x |
| PIT feature boundary/readiness | existing `feature-store-boundary`, `model-readiness-audit`, `docs/FEATURE_STORE.md` |
| raw/core/gold layer semantics | `docs/TABLE_CONTRACTS.md`, `docs/ARCHITECTURE.md` |
| one canonical transformation writer / SQLMesh promotion | `docs/SQL_OWNERSHIP.md`; future bounded `gold-transformation-convergence` change after recovery/stable IDs |
| era-correct wOBA and formula consolidation | future `gold-transformation-convergence`; metric catalog remains formula metadata |
| AI-generated metric admission / disabled metrics | existing metric catalog plus future bounded `metric-admission-contract` if pipeline-recovery D10 is insufficient |
| canonical event semantics | existing `play-engine` / `retrosheet-state-engine` are inspected first; create `canonical-event-contract` only for uncovered core-event work |
| target semantics | future `target-registry` change before broad new prediction families |
| normalized market contracts/quotes/settlement | finish `odds-history-capture` first; then future `market-contracts-v1` |
| immutable research/model lineage | existing model provenance is reused; future `research-lineage-v1` only for missing immutable-run guarantees |
| model promotion ladder/calibration | existing feature-store harness/model-card work plus future `model-promotion-v1` when Phase B is authorized |
| AI skills | later, only after CLI/contracts stabilize |

No future change named here is automatically authorized to start. Existing
phase gates and owner-approved focus still control scheduling.

## Contract-impact checklist

A substantial change must ask whether it changes any of:

- grain or business identity;
- source/provenance or rights;
- formula/algorithm or canonical writer;
- null semantics;
- event/observation/availability/prediction time;
- build/replacement behavior;
- public interface;
- failure/health semantics;
- target/settlement definition;
- artifact or research reproducibility.

If yes, update the nearest owning contract in the same change and add the
applicable machine gate/evidence.

## Non-goals

- No schema or production-data changes.
- No mass rewrite of `docs/DECISIONS.md`.
- No new scheduler/framework/database.
- No implementation of the future changes listed in D8.
- No duplicate roadmap or task tracker.
