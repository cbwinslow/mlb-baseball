# Documentation subsystem DOX

## Purpose

This subtree owns human-facing architecture, source, research, runbook, decision, roadmap, manual, and project-navigation documentation. It should make the current system understandable without forcing agents or contributors to load the whole repository narrative for every task.

## Ownership

- Living/current docs: architecture, source catalog, rights, SQL ownership, user manual, runbooks, maps, product direction, research contracts.
- Decision records / ADRs: why important choices were made and when they should be revisited.
- Dated specs/plans: intended work for a bounded change or program; these are historical evidence once superseded.
- `docs/MAP.md`: primary human/agent navigation surface for the docs tree.
- DOX architecture/rollout docs: the context-distribution design itself.

## Local Contracts

- Distinguish **current truth** from **historical intent**. A dated plan does not override newer living architecture/product docs merely because it contains more detail.
- Prefer one canonical owner for current facts and link to it from other docs instead of copy/pasting large repeated sections.
- When verified source behavior disagrees with prose, update the stale prose; do not preserve contradictory text as a second "version" unless historical context is actually useful.
- Keep research/statistical citations precise enough for reproduction and licensing/source-rights statements traceable to the relevant source/profile documentation.
- Do not put private credentials, deployment secrets, local absolute paths, or user-specific runtime data in repository docs.
- Docs describing commands must match the current CLI/package behavior or be clearly marked conceptual/future.
- Generated reference material should identify its generator/source of truth and should not be hand-edited when regeneration is the proper path.
- DOX files are **operational context**, not diaries. They describe durable ownership/contracts/work guidance/verification and route readers to deeper references.
- File-specific source contracts belong beside source files as `*.dox.md` when that locality materially improves progressive disclosure; they should not be duplicated wholesale under `docs/`.

## Progressive Disclosure Guidance

Use the smallest artifact that owns the necessary level of detail:

- root `AGENTS.md`: project-wide invariants and routing;
- subtree `AGENTS.md`: rules/context relevant to nearly all files in that subtree;
- `<source>.dox.md`: high-value knowledge tied to one implementation file;
- living architecture/source docs: durable explanation/reference shared across many components;
- ADR: rationale for a consequential decision;
- runbook/skill: multi-step procedure loaded only when the task requires it;
- dated plan/spec: implementation sequence or temporary program state.

The goal is more total high-quality context with less irrelevant context loaded per task.

## Work Guidance

- When adding a new document, first ask whether an existing canonical document should be extended instead.
- Keep `docs/MAP.md` useful as a map, not an encyclopedia.
- Prefer relative links inside the repository.
- Archive/remove stale duplicated guidance rather than appending ever more caveats to it.
- Use exact dates when documenting changing project state.
- When a code change modifies a documented public contract, update the owning doc/DOX in the same PR.

## Verification

- Check changed relative links.
- Verify command examples against current code/CLI where feasible.
- Compare source/rights claims to `docs/DATA_SOURCES.md`, `docs/SOURCE_RIGHTS.md`, and actual connector behavior.
- For architecture claims, inspect the corresponding package/migration/SQLMesh source rather than relying on an older plan.

## Child DOX Index

| Child | Scope |
| --- | --- |
| [`superpowers/plans/`](superpowers/plans/) | Dated implementation/review plans; historical/contextual unless referenced as active by current project maps. |

Create deeper documentation DOX only where a durable subcollection develops distinct authoring/maintenance rules.
