@AGENTS.md

# Claude Code — modeling/research rules

Shared model/PIT/evaluation contracts live in `AGENTS.md`. This file contains Claude-specific behavior for work in this large research namespace.

## Claude-specific discipline

- Do not turn broad brainstorming into implementation automatically. First classify whether the idea is a research statistic, predictive feature, evaluation method, prototype, or duplicate of an existing asset.
- Use research/delegation agents for literature/library reconnaissance when useful, but require a concise evidence handoff; deterministic Python/SQL owns actual calculations and experiment artifacts.
- Before creating a new module, search this namespace and current research/stat registries for an existing implementation. This directory already has substantial historical proliferation.
- For model-performance claims, demand the actual chronological holdout/calibration evidence. Do not summarize training metrics as validation.
- If a result looks implausibly strong, perform a documented leakage/PIT review rather than declaring either success or leakage from the metric alone.
- Do not let Claude's desire to "clean up" old model modules trigger a mass rewrite. Classification/consolidation/extraction must be incremental and test-backed.

## Context loading

- Read the exact module/tests and research citation first.
- Load detailed experiment/model runbooks or skills only when running that procedure.
- If a future module sidecar exists, treat it as the local contract but verify formulas against the cited source/fixtures.

## Verification

- Run deterministic hand fixtures for formulas.
- Run chronological/rolling evaluation for predictive changes.
- Re-run baseline/calibration comparisons before presenting a model improvement.
- Record what was actually executed and any data/profile limitations.