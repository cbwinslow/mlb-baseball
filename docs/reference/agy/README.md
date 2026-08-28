# Agy (Antigravity / Gemini) planning artifacts — preserved for the record

These are the research and planning documents the Antigravity/Gemini agent ("Agy") produced
while building this project's analytics work. Copied here **verbatim** on 2026-08-28 from
`~/.gemini/antigravity-cli/brain/f1e15173-07f1-47eb-a34c-8cffad6befd9/` (a Gemini conversation
dated 2026-08-21 to 2026-08-23) so the record survives outside that tool's local store. They
have not been edited. Doc consolidation into the main `docs/` set is a later task.

## What's here

| File | Date | What it is |
|---|---|---|
| [`METRIC_EXPANSION_CATALOG.md`](METRIC_EXPANSION_CATALOG.md) | 2026-08-21 | Agy's sabermetric metric catalog — six-grain taxonomy, formulas for CSW%/FIP/xFIP/SIERA/wSB/BaseRuns/RE24/LI, dynamic-windowing SQL pattern, work-package plan. Cites FanGraphs Sabermetric Library, Tango *The Book*, Baseball-Reference, Statcast, Baseball Prospectus. This is the basis of the **governed Bucket A features** (`team_rate`, `offense`, `starter`, `bsr`, `pitch_discipline`, `run_expectancy`, …). Formulas here are real and correctly stated. |
| [`PLATFORM_ASSESSMENT_AND_EXPANSION_PLAN.md`](PLATFORM_ASSESSMENT_AND_EXPANSION_PLAN.md) | 2026-08-23 | Agy's platform assessment + roadmap — data-estate inventory, the "GBM uses 37 of 287 features" finding, GPU assessment (the K80/K40 cards are too old for modern XGBoost/PyTorch), and a tiered expansion roadmap (GBM-v2, Numba Monte Carlo, props, live win prob, season projections). |
| [`PROJECT_ASSESSMENT_AND_ENHANCEMENT_PLAN.md`](PROJECT_ASSESSMENT_AND_ENHANCEMENT_PLAN.md) | 2026-08-21 | Agy's project-quality assessment — verifies the repo against its own policies (DB safety, source rights, testing, type quality, SQL ownership, modeling discipline), evaluates candidate Postgres extensions and Python libraries (pg_trgm, pgvector, DuckDB, Optuna, SHAP), validates completed milestones. **Notably does not mention the "Engine" packages at all** — Agy's disciplined work followed the feature-admission queue; the ~110 Engine packages (ADR-089–258) were a separate, later generation pass (git: Aug 22–24) that skipped it. |

## How this connects to current work

- The **Engine packages** (`BBCRI`, `IZHSMI`, `OFLDII`, … invented composite scores, ADR-089–258)
  are documented in `docs/THEORY_AND_METHODOLOGY.md` §75–140, with a real 139-source bibliography
  in §141. The concepts and the domain literature are sound; what's unjustified is the specific
  composite *weights* (no derivation, no citation tying those numbers to anything).
- The plan for folding the Engine packages into the real feature pipeline (wire to data, replace
  the invented constants with data-derived or cited ones): see
  `docs/superpowers/specs/2026-08-28-bucket-b-triage-rubric.md` and the implementation plan
  alongside it.
