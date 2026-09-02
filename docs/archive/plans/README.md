# MLB execution plans

> **Status: retired.** The `plans/` workflow is replaced by OpenSpec (`openspec/changes/` + the `NOW / NEXT / LATER` block in `openspec/project.md`). Files here are historical.


These numbered plans convert durable doctrine into a long-horizon execution
sequence. They remain useful architectural/program records, but they are **not**
all active at once. Newer owner decisions and dated plans may deliberately pause
later tracks without invalidating the work already recorded here.

## Current program — 2026-09-01

The **research database is the active product track**. The prediction ladder and
Astro site are paused until the research database is a coherent outside-user
product.

Read these first for current work:

1. `docs/superpowers/specs/2026-09-01-research-database-v1-design.md` — owner
   focus decision and v1 definition.
2. `docs/superpowers/plans/2026-09-01-research-platform-consolidation.md` —
   deep-review execution plan covering research grains, Stat Registry,
   researcher API, portable DuckDB/Parquet data, package/CLI/acquisition cleanup,
   testing, SQLMesh incrementality, and the eventual gate for reopening models.
3. `docs/AGENT_CONTEXT_ARCHITECTURE.md` and
   `docs/superpowers/plans/2026-09-01-dox-agent-context-rollout.md` — proposed
   hierarchical multi-agent documentation/context pilot.
4. `plans/03-research-statistics-and-features.md` — existing numbered research
   plan; execute only the portions consistent with the current research-database
   focus and newer dated plans.

Do not pull Plan 04 or Plan 05 work forward merely because older status text
called them next. Current focus wins.

## Long-horizon sequence

| Plan | Outcome | Depends on | Current role |
|---|---|---|---|
| [00](00-workspace-reconciliation.md) | clean, reviewed baseline | none | historical/accepted baseline |
| [01](01-correctness-rights-security.md) | trustworthy and safely scoped platform | 00 | largely established; remaining findings are folded into current work as needed |
| [02](02-sql-transforms-and-ingestion.md) | named SQL, decomposed conformance, durable ingestion | 01 | incremental; SQLMesh promotion and ingestion cleanup only when justified by current research work |
| [03](03-research-statistics-and-features.md) | governed research/statistics/feature factory | 02 | **active conceptual plan**, narrowed to research DB/statistics first |
| [04](04-modeling-simulation-and-experiments.md) | reproducible multi-target modeling program | 03 | **paused** until research-consumption gates are met |
| [05](05-serving-astro-and-launch.md) | original public research/forecast product | 04 | **paused** |
| [06](06-package-validation-and-tieout.md) | ADR-089–258 package batch tied out against real sources or honestly relabeled | independent owner-authorized track | Engine expansion frozen; reuse only ingredients that directly support current research work |

## What "research DB done enough to reopen modeling" means

Before Plan 04 becomes active product work again, the current consolidation plan
expects at least:

- stable, obvious game/season research grains;
- validated advanced statistics owned outside prediction-specific modules;
- machine-readable stat/coverage metadata;
- an intuitive researcher-facing Python query surface;
- a rights-safe portable dataset path (Parquet and/or DuckDB);
- clean, non-contradictory outside-user setup/query/export docs;
- isolated/order-independent tests and a clean-install research smoke path;
- no major CLI/acquisition gravity well actively blocking normal maintenance.

This is a gate, not a demand that every possible research statistic be finished.

## Delegation protocol

For each work package, give the delegated agent a self-contained prompt naming the
applicable plan and exact scope. Include:

- whether edits are allowed;
- affected paths/subsystem;
- database safety and actual current test-isolation contract;
- verification expected;
- requirement to preserve unrelated/parallel changes;
- changed-file/test/limitation handoff;
- no authority to merge, delete worktrees, rewrite unrelated work, modify
  production data, or begin the next work package unless explicitly authorized.

The reviewing/lead agent independently reads the diff, verifies the relevant
contracts/tests, and records any meaningful architecture decision before the next
package proceeds. A delegated agent's own "tests pass" statement is evidence to
check, not final verification.

The proposed DOX hierarchy in `docs/AGENT_CONTEXT_ARCHITECTURE.md` is intended to
make these prompts smaller over time by giving each agent reliable local project
context. Delegated prompts should still remain self-contained because different
harnesses pass parent/local context to subagents differently.

## Global success measures

- Clean-clone research database setup, migration, selected ingestion, conformance,
  reporting, diagnostics, query, and export are documented and reproducible.
- Every public research result is traceable to permitted sources and a documented
  grain/coverage/stat definition.
- No SQL/Python business formula has untracked duplicate implementations.
- Missing historical measurement is distinguishable from a real zero.
- Point-in-time prediction data remains separated from finalized historical
  research statistics.
- Portable public-safe artifacts are versioned, checksummed, attributed, and
  usable without PostgreSQL.
- Forecasting/evaluation, when resumed, remains point-in-time correct,
  matched-sample, calibrated, and honest about uncertainty and market timestamps.
- The eventual site works from explicit serving contracts and lawfully reusable
  data rather than exposing arbitrary warehouse state.

## Immediate contract gates

The older plan sequence established several contracts that remain important even
while modeling is paused:

1. **Game identity:** preserve one canonical MLB game identity per provider
   `game_pk` where safely available, with provider-native keys retained when no
   safe crosswalk exists. Carry this through research grains and later prediction.
2. **Workflow serialization:** ingestion/conformance/derived builds must not run
   in conflicting overlapping states. Keep existing locking/ordering protections
   explicit.
3. **Reproducibility honesty:** distinguish content fingerprints from genuinely
   immutable row snapshots/artifacts. Do not describe something as replayable if
   the source rows needed for replay are mutable/missing.
4. **Public safety:** publication/export is rights-profile constrained. Local
   availability is not redistribution permission.
5. **Research vs prediction semantics:** finalized historical statistics and
   "what was knowable before the game" feature values are separate products even
   when they share formulas.

## How to use the old numbered plans

- Treat completed sections as historical contracts/evidence unless a later ADR or
  current code supersedes them.
- Treat unfinished sections as candidates, not automatic authorization.
- When an older status paragraph conflicts with verified current code or a newer
  owner decision, repair the stale status during the next material edit instead
  of silently following it.
- Record actual completed work in `PROGRESS.md`; do not use plan prose as proof
  that implementation happened.
