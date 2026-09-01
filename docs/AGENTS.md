# Documentation DOX

## Purpose

Own human-facing architecture, product, data, research, operations, decisions,
reference material, plans/specs, and navigation for the repository.

The docs tree is not a second source-code implementation. It explains durable
contracts, operating procedures, evidence, and rationale that cannot be inferred
reliably from code alone.

## Ownership

Primary living docs include:

- `NORTH_STAR.md` — long-term mission and product principles;
- `PRODUCT_DIRECTION.md` — current product focus and explicit pauses/freeze rules;
- `ROADMAP.md` — living built-vs-planned state;
- `ARCHITECTURE.md` — system/data-layer architecture;
- `MAP.md` — navigation/reading map;
- `DATA_SOURCES.md` / `SOURCE_RIGHTS.md` — source scope and reuse rights;
- `TABLE_CONTRACTS.md` / data dictionary material — relation grains/keys/lineage;
- `RESEARCH.md`, feature/stat registries, runbooks, and public API docs.

`superpowers/plans/` and `superpowers/specs/` are dated work/design artifacts, not
living truth. `reference/` contains tie-out/source reference material. ADR history
is evidence for why a decision was made; it does not override newer explicit
accepted decisions or verified current behavior.

## Local Contracts

### Living vs historical truth

Every doc should make clear whether it is:

- **living** — expected to describe current behavior;
- **dated evidence/snapshot** — true at a particular time;
- **plan/spec** — intended work, not proof it shipped;
- **reference** — source/tie-out material;
- **generated** — derived from code/registries and not hand-edited.

Do not cite an old plan as proof current code behaves that way. Verify code/tests
or the current living contract.

### Avoid duplicate current-state prose

Prefer one authoritative living owner for each fact and link to it elsewhere.
Do not keep several independent copies of:

- current product status;
- test database behavior;
- source rights;
- table grains;
- stat formulas;
- CLI command lists;
- package/dependency state.

Where drift is recurring, generate reference material from code/registries rather
than asking humans/agents to synchronize prose manually.

### Source and formula claims

- Research/statistical claims need citations or a clearly labeled project-derived
  result.
- Formula docs must identify authoritative definitions and distinguish formula
  definition from project-specific implementation/coverage.
- Rights statements must match `SOURCE_RIGHTS.md` and enforcement code; never
  broaden redistribution from prose alone.

### Plans and ADRs

- Plans describe scoped intended work and acceptance gates.
- Progress/evidence records describe what actually happened.
- ADRs capture non-trivial decisions and revisit conditions.
- Do not append diary-style history to operating docs when a dated plan/progress
  entry or ADR is the correct artifact.
- When a decision changes, update living docs and mark/ supersede the old decision
  rather than leaving readers to reconcile contradictions.

## Work Guidance

When changing behavior, update the nearest living doc in the same change if users
or future agents would otherwise be misled.

Keep `MAP.md` useful as a navigation layer. New long-lived docs should either be
indexed there or intentionally live under a self-explanatory subtree with a local
index.

Prefer concise task-oriented runbooks. Put detailed implementation contracts near
source via DOX sidecars or registries instead of making human docs reconstruct
source internals.

Do not edit generated/reference artifacts manually unless their contract says they
are hand-maintained.

## Verification

- Check relative links for changed docs.
- Verify commands against current CLI/script behavior before publishing them.
- Verify relation/column names against current migrations/models/catalogs.
- Verify source-rights wording against enforcement code and `SOURCE_RIGHTS.md`.
- For docs-only changes, application tests are unnecessary unless the doc edit
  exposes a code/docs mismatch that must be fixed too; CI/link checks still apply.

## Child DOX Index

No child DOX files are required initially. Create children only for durable doc
subtrees whose authoring rules materially differ, such as a future generated
reference tree or a formal ADR directory.
