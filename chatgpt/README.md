# ChatGPT outside-review archive

This directory contains point-in-time outside reviews supplied by the project
owner. They are **evidence and design input, not governing project
documentation**.

Do not treat a recommendation in these files as adopted merely because it is
written confidently or names a specific library/source. Current project truth
is owned by `openspec/project.md`, durable `openspec/specs/`, accepted ADRs,
and the nearest subsystem contract. When an outside review is accepted, promote
the rule or work item into that owner and leave the original review here as the
historical rationale.

## Disposition

| Review artifact | Current disposition |
|---|---|
| `chatgpt-laws.md` | **Mostly absorbed.** The project North Star, ten engineering invariants, contract-impact Definition of Done, Platform Convergence gate, and major phase priorities are folded into `openspec/project.md`, `docs/PRODUCTION_CONVERGENCE.md`, and subsystem contracts by `openspec/changes/governance-convergence/`. Detailed implementation remains with the active owning changes, especially `pipeline-recovery` and `stable-ids-incremental-conform`. |
| `chatgpt-review.md` | **Mostly absorbed/routed.** Stable identity, atomic publish, gold/feature boundaries, single-writer SQLMesh promotion, doctor/audit/readiness separation, target/market/research-lineage directions, and future AI-skill sequencing are mapped in the governance-convergence disposition table. Items behind Phase B/C remain proposals, not authorization. |
| `sabremetrics-review.md` | **Partly absorbed; remaining work is bounded.** Facts/statistics/features separation and one canonical SQL writer are now durable contracts. Season-dependent constants/reference context, formula consolidation, external calculation oracles, and an optional future `mlb_research.stats` facade remain follow-up work. The next formula-consolidation program should inventory before adding formulas and start with wOBA/wRC+, FIP/xFIP, and RE24/WPA. |
| `source-review.md` | **Evaluation input, not a source/dependency manifest.** Fungo is already adopted. Polars/Pandera already have documented adoption triggers. Other named libraries/sources (for example external sabermetric oracles, SportsDataverse-style reference data, alternate MLB clients, umpire/weather candidates) must be re-verified for current version, license/terms, overlap, rights, maintenance, and unique value before adoption. `docs/DATA_SOURCES.md`, `docs/SOURCE_RIGHTS.md`, and `pyproject.toml` remain authoritative. |

## Residual work extracted from these reviews

These are intentionally **not all active changes**. Existing phase gates still
control scheduling.

1. **Sabermetric formula consolidation** — future bounded change after current
   Platform Convergence blockers: inventory formula owners/constants first;
   make season-dependent context versioned data; remove fixed-era assumptions
   from wOBA/wRC+/FIP/xFIP; verify RE24/WPA ownership; use independent
   calculation oracles where they genuinely provide an independent check.
2. **Library/source evaluation** — future research change, not dependency
   adoption: re-check the candidates in `source-review.md` against the current
   repository and current upstream projects, then record adopt / optional /
   validation-oracle / watch / reject with rights and overlap evidence.
3. **Researcher stats facade** — optional later consumer API
   (`mlb_research.stats`) only if demand exists. Warehouse SQL remains
   canonical; any Python arithmetic must share versioned context and pass
   parity tests rather than becoming a second formula owner.
4. **New signal sources** — weather, umpire and other candidates require their
   own source/PIT/rights design. Observed historical values must not masquerade
   as pregame-available forecast values.
5. **Metric validation contract** — extend the catalog only through a dedicated
   change if additional fields such as formula/context version, validation
   oracle/tolerance, availability, or reliability/sample-size policy are proven
   necessary. Do not add speculative schema fields directly from this review.

## Preservation rule

Keep these imported review files unchanged unless correcting an import error.
Their value is that they preserve what the outside reviewer actually said at
that point in time. Promote accepted conclusions into canonical owners instead
of continuously rewriting the reviews to match the project.
