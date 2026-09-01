# GitHub Automation DOX

## Purpose

Own repository automation and collaboration metadata under `.github/`: CI,
security scans, dependency automation, labels, issue/PR templates, CODEOWNERS, and
workflow policy.

## Ownership

- `workflows/` owns GitHub Actions behavior;
- Dependabot/dependency review config owns automated dependency update policy;
- CODEOWNERS/review templates own collaboration metadata, not runtime application
  behavior;
- security/quality workflows complement local verification; they do not replace
  tests run before handing off work.

## Local Contracts

- Pin third-party GitHub Actions to reviewed immutable revisions where current
  repository policy requires it; dependency automation may update those pins.
- Keep workflow permissions least-privilege. Do not add broad write permissions
  to make one step easier.
- Never print/store secrets or private data in logs/artifacts.
- CI must not point at production PostgreSQL or production credentials.
- Required checks should represent real correctness/security gates and remain
  deterministic enough for contributors to reproduce locally.
- Avoid duplicate workflows that run the same tool with slightly different
  settings. Consolidate ownership instead.
- Expensive or network-dependent checks should have a clear reason and bounded
  runtime; ordinary PR correctness should not depend on flaky third-party APIs.
- Keep action versions and Python/tool setup compatible with `pyproject.toml`,
  `uv`, Ruff, mypy, pytest, SQLFluff, SQLMesh, pgTAP, and Chadwick requirements
  actually used by the repo.
- Changes to labels/templates/branch governance must stay consistent with
  `CONTRIBUTING.md`, `CLAUDE.md`/agent Git rules, and the GitHub governance
  runbook.

## Work Guidance

Before adding automation, inspect existing workflows and reuse established setup
steps/caches. Prefer one clear source of CI truth over specialized copies.

Do not relax a failing security/test gate until the failure is understood. If a
bot/service itself is failing independently of repository code, document that
separately from a real code finding.

Dependency-bump PRs should still pass the same compatibility tests as human code
changes.

## Verification

- Validate workflow YAML/action syntax with the repository workflow lint job/tool.
- Review changed `permissions:`, secret usage, artifact upload/download behavior,
  and event triggers (`pull_request`, `push`, `workflow_dispatch`, schedules).
- Confirm renamed jobs/checks do not accidentally break branch-protection required
  status contexts.
- For CI-command changes, run the same command locally where practical.

## Child DOX Index

No child DOX file yet. Add `.github/workflows/AGENTS.md` only if workflow-specific
rules grow enough to justify separating them from templates/governance metadata.
