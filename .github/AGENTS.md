# GitHub automation DOX

## Purpose

This subtree owns GitHub-native collaboration and automation: Actions workflows, issue/PR templates, CODEOWNERS, Dependabot, labeler configuration, security/release metadata, and repository checks.

## Local Contracts

- Keep workflows least-privilege: grant only the permissions a job actually needs.
- Pin third-party actions to trusted immutable revisions where repository policy requires it; review dependency provenance before adding new actions.
- Do not put secrets or credential values in workflow YAML, examples, logs, or artifacts.
- CI should reproduce real project quality gates rather than maintain a second inconsistent set of commands.
- The required test path must exercise the real PostgreSQL behavior expected by integration tests; do not replace database integration with mocks merely to make CI simpler.
- Avoid duplicate workflows that run the same expensive checks with slightly different names. Consolidate when behavior overlaps.
- Keep caching keyed to the actual dependency/tool inputs so stale environments do not mask failures.
- Workflow changes that affect release/security posture should update the relevant contributor/security docs in the same PR.
- Automated reviewers are advisory evidence, not authority. Verify findings against source behavior; address real findings and explain false/out-of-scope ones.
- Do not weaken branch/review/security gates just to make a PR green.

## Workflow Design Guidance

- Fast deterministic checks first; expensive/integration/security checks can follow with clear dependency relationships.
- Keep Python environment setup consistent with `uv` and project lock/config.
- Ruff, mypy, pytest/PostgreSQL, SQLFluff/SQL ownership checks, secret scanning, dependency review, CodeQL, SBOM/Scorecard or similar existing controls should remain coherent rather than proliferating replacements.
- Add matrix dimensions only when they represent supported environments worth testing.
- Artifacts should contain useful diagnostics and must not leak secrets or restricted data.
- Scheduled jobs should have an explicit maintenance/value reason; do not add recurring automation just because GitHub Actions supports it.

## Verification

- Validate YAML/workflow syntax using the repository's workflow lint path.
- Review job permissions and secret exposure.
- Confirm referenced scripts/commands/files exist.
- When changing CI commands, run the equivalent command locally or in the current execution environment where possible.

## Child DOX Index

| Child | Scope |
| --- | --- |
| `workflows/` | CI, security, lint, dependency, release, and repository automation workflows; inherits this contract unless workflow-specific DOX becomes necessary. |

Individual workflow files normally do not need `*.dox.md` sidecars. Their behavior should be explicit in YAML plus this subsystem contract; add a sidecar only for genuinely complex reusable workflow infrastructure.
