@AGENTS.md

# Claude Code — Python package rules

This file adds Claude-specific behavior for work under `mlb_baseball/**`. Shared package truth lives in `AGENTS.md`; do not duplicate it here.

## Context loading

- Before editing a package file, read the applicable parent/local `AGENTS.md` chain and any matching `<filename>.dox.md` sidecar.
- Do not preload every package sidecar. Follow the filesystem path and load only the context for the subsystem/file being changed.
- When a sidecar points to exact tests/ADRs/source docs, read those only when they are relevant to the current change.

## Claude workflow

- Use planning/reasoning effort for cross-module API changes, schema/conformance changes, PIT/leakage-sensitive logic, or decomposition of `cli.py`/`conform.py`; ordinary local edits should stay focused.
- When delegating/subagenting package work, give the subagent the exact target path and instruct it to read the local DOX chain first. Do not assume the subagent inherited every parent context file.
- Prefer existing package helpers/registries/contracts discovered from local DOX over generating a new abstraction from memory.
- Before proposing an optimization/refactor, inspect measurements/tests/history named in the sidecar. Do not turn a sidecar's historical warning into a universal rule outside its scope.
- After a meaningful contract change, update the nearest DOX sidecar/`AGENTS.md` as part of the same edit rather than leaving documentation cleanup to a later agent.

## Verification behavior

- Re-run the exact targeted tests named by the local DOX after accepting delegated edits.
- For DB/conformance/connector work, do not substitute mocked PostgreSQL behavior for the repository's real integration fixtures.
- Report what was actually run; never infer passing status from a subagent/self-report alone.
