# MLB execution plans

These plans convert `docs/PROJECT_REVIEW.md` and `AGENTS.md` into the execution
sequence for Antigravity/Gemini 3.6 Flash (Medium). Run one work package at a
time. Do not skip a gate because later work depends on the contracts established
earlier.

## Sequence

| Plan | Outcome | Depends on |
|---|---|---|
| [00](00-workspace-reconciliation.md) | clean, reviewed baseline | none |
| [01](01-correctness-rights-security.md) | trustworthy and safely scoped platform | 00 |
| [02](02-sql-transforms-and-ingestion.md) | named SQL, decomposed conformance, durable ingestion | 01 |
| [03](03-research-statistics-and-features.md) | governed research/statistics/feature factory | 02 |
| [04](04-modeling-simulation-and-experiments.md) | reproducible multi-target modeling program | 03 |
| [05](05-serving-astro-and-launch.md) | original public research/forecast product | 04 |

## Delegation protocol

For each numbered work package, give Antigravity a self-contained prompt quoting
the relevant plan section and `AGENTS.md`. Use `accept-edits` only after the owner
authorizes implementation. Require it to preserve unrelated changes, use a
dedicated `mlb_test_<task>` database, avoid production writes, and return changed
files, commands/results, limitations, and the next gate. It must not commit,
merge, delete worktrees, or begin the next package unless explicitly authorized.

GPT-5.6 Sol performs the gate review: inspect diffs, run proportional independent
verification, compare acceptance criteria, record decisions, then authorize the
next package. Failed ideas and rejected designs are documented rather than erased.

## Global success measures

- Clean-clone bootstrap, migration, conform, prediction, evaluation, and site
  data build are documented and reproducible.
- Every public result is traceable to permitted sources, feature snapshot, model
  artifact, prediction cutoff, and generated time.
- No SQL business formula has untracked duplicate implementations.
- All evaluation is point-in-time correct, matched-sample, calibrated, and honest
  about uncertainty and missing coverage.
- The site works at $0/month with optional monetization disabled.

