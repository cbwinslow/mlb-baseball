# Bucket B triage rubric: fold the "Engine" packages into the real feature pipeline

**Status:** Design spec, not yet an implementation plan. Written via `superpowers:brainstorming`
on 2026-08-28 with the project owner. Companion to `plans/06-package-validation-and-tieout.md`
and `docs/PACKAGE_VALIDATION_STATUS.md`.

## Context

`mlb_baseball/model/` has ~150 files. Roughly 35–40 are real, governed features (the
`docs/FEATURE_ADMISSION_QUEUE.md` → `docs/FEATURE_REGISTRY.md` → `gbm.py::FEATURE_COLUMNS`
pipeline). The other ~110 — ADR-089 through ADR-258, the "Engine" packages with invented acronym
scores (`BBCRI`, `IZHSMI`, `OFLDII`, `FSRJI`, …) — **bypassed that pipeline entirely.** Verified
2026-08-28 by reading a sample (`chase_recog`, `heat_check`, `oppo_liner`, `first_step`, `vaa`,
`haa`, `xslg`, `babip`, `active_spin`, `blast_angle`):

- **Concepts are real** and mostly well-chosen (breaking-ball chase discipline, VAA, in-zone
  fastball contact, first-step reaction, spin efficiency). The benchmark input constants are
  roughly plausible.
- **The concepts are also documented** — `docs/THEORY_AND_METHODOLOGY.md` §75–140 gives every
  Engine package a formula section, and §141 is a real 139-source academic bibliography (James,
  Tango/Lichtman/Dolphin, Nathan, Petriello, Pollack/Fast, Carleton, Roegele, Husband, …).
- **What is *not* justified is the specific composite weights.** `BBCRI = 100 + (32.0−Chase%)·2.2
  + (Take%−68.0)·1.6 + (58.0−Whiff%)·0.8` — the `2.2 / 1.6 / 0.8`, the `0.0022` runs-per-point
  conversion, and the `≥ 116.0` "elite" cutoff appear in THEORY §133 exactly as in the code, with
  no derivation and no citation tying *those numbers* to anything. They read as Agy's own
  reasonable-looking estimates, not fitted or sourced values. (Contrast §2.1 SIERA, which carries
  the real published Swartz/Seidman coefficients, or §3.1 IVB, which has Alan Nathan's physical
  derivation.)
- **None are wired to data.** They take hand-typed CLI args (`mlb vaa --release-height 5.8 …`).
  Zero `get_connection()` / `raw.` / `core.` / `gold.` references. As built they cannot produce a
  number for a real player, feed a model, or power a website.
- The disciplined Bucket A work (`team_rate`, `offense`, `starter`, `bsr`, `diff`, …) went through
  the full admission queue; Agy's own Aug-21 assessment
  (`~/.gemini/antigravity-cli/brain/f1e15173-…/PROJECT_ASSESSMENT_AND_ENHANCEMENT_PLAN.md`)
  documents *that* work and does not mention the Engine packages at all. The Engine batch was a
  separate, faster generation pass (git: Aug 22–24) that skipped the queue.

The framework to fold them in **already exists**. This spec is the rubric for running each Engine
package through it.

## The per-package decision (apply to every ADR-089–258 package)

**The default is WIRE.** The concepts are real and the owner wants the work used, not discarded.
Every package is presumed worth wiring to real data unless it clears one of the two narrow
exceptions below. Record the outcome + a one-line reason in `docs/PACKAGE_VALIDATION_STATUS.md`.

### WIRE — the default: connect the concept to real data, fix the constants

Do all of:
- **New `FEATURE_ADMISSION_QUEUE.md` row** — ID, grain, exact formula, PIT cutoff rule, null
  policy + coverage gate, required tests, source profile. Coverage measured with
  `mlb field-census --exact`.
- **Point-in-time SQL** in `mlb_baseball/sql/<name>_update.sql` computing the metric's **raw
  components** per entity per game (entering value only, zero-leakage), wired into
  `enrich_feature_stage()`; `gold.game_feature` columns via a migration; `FEATURE_REGISTRY.md`
  row with lineage.
- **Replace every unjustified composite constant** with one that is either:
  - *derived from our own data* — a percentile of the real distribution ("elite = p90"), or a
    coefficient fit on a chronological sample, method documented in the ADR; or
  - *taken from a cited published source* — FanGraphs Guts run values, Tango linear weights,
    a named article's threshold.
- **Emit the raw components as the model features.** The composite score / tier is kept too (it
  has website value) but the ADR marks it **display/derived**, and it stays out of
  `gbm.FEATURE_COLUMNS` unless it independently earns a place in a chronological retrain — the raw
  components carry the signal; a pre-weighted composite on top is usually redundant.
- **Integration test** with a hand-calculated fixture + idempotency + missing-table gate,
  following `tests/integration/test_model_pitch_discipline.py`.
- Update the package's `docs/THEORY_AND_METHODOLOGY.md` section: cite the source for each constant
  now, or state "calibrated to our data, method: …".
- The `mlb <name>` CLI stays if it now reads real data; otherwise it becomes a thin wrapper over
  the SQL or is dropped.

Where the concept has a real, checkable published *definition* but our composite is invented on
top (VAA, xSLG, spin efficiency), "WIRE" may mean **just expose the real underlying metric** and
retire the invented index — that's a WIRE outcome, not a RETIRE.

### RELABEL — exception 1: premise the project's own research rejects

Only when the package's premise is one this project's *own* documents already call unreliable —
`clutch` (THEORY §141 cites Cramer 1977 "Do Clutch Hitters Exist?"; `FEATURE_ADMISSION_QUEUE.md`
CTX-06 says batting clutch isn't year-over-year repeatable), `lineup_protect` (*The Book* finds no
measurable protection effect) — **and** the owner agrees per package.
- Module stays; docstring + ADR rewritten to: *"exploratory calculator, premise unvalidated /
  contradicted by cited research, not a model feature, not fit for the public site as fact."*
- No `gold` column, no `FEATURE_COLUMNS`, no registry row. Unit test asserts internal consistency
  only, documented as such.

### RETIRE — exception 2: genuinely redundant or unfixable, per-package, owner-confirmed

Not a default and not a numeric target. Only when, for a specific package:
- its metric is *already produced* by a governed feature at the same grain and the Engine version
  adds nothing (e.g. an xBA/xSLG package once `statcast_expected` covers it), **or**
- its formula produces values that are demonstrably wrong (a sign error, a physically impossible
  range) *and* fixing it is genuinely more work than the value it would add.

RETIRE = delete module + `tests/unit/test_<name>.py` + `mlb <name>` CLI + dispatch test; mark the
ADR **Superseded** (kept, not erased, per `AGENTS.md`), noting which governed feature replaces it.
Each RETIRE is called out individually for the owner before the PR — never batched on Claude's
judgment alone.

## Tie-out reference infrastructure (build once, before the fan-out)

1. `docs/reference/` — transcribed published constants with page/URL citations:
   - Tango *The Book*: RE24 matrix, base/out run-expectancy, linear weights.
   - FanGraphs Sabermetric Library: the metric definitions the Engine packages name.
   - Statcast / Baseball Savant glossary: VAA/HAA/active-spin/barrel/xStat definitions.
2. **FanGraphs "Guts!" connector** — one-time Playwright snapshot of the yearly wOBA weights,
   wOBA scale, FIP constant, and event run values (`wBB`, `wHBP`, `w1B`…) → a dated CSV in
   `downloads/` + a `raw.fangraphs_guts` table. Add a row to `docs/DATA_SOURCES.md` (currently
   lists FanGraphs as "deferred/broken" — this is a narrow, one-time, reference-constant
   exception, ToS note included). These constants are what the WIRE calibration step needs and the project has
   none of them today.
3. A `mlb_baseball/model/_distribution.py` helper: given a metric expression and a grain, return
   the real percentile breakpoints from our own `raw`/`core` data — so "elite = p90" is computed,
   not guessed.

## Fan-out plan

1. **Rubric review** (this doc) — owner approves the default (WIRE) and the two exceptions.
2. **Triage pass** — one reading of every ADR-089–258 package (module + test + ADR + its
   `THEORY_AND_METHODOLOGY.md` section), each assigned WIRE / RELABEL / RETIRE + a one-line reason
   in `PACKAGE_VALIDATION_STATUS.md`. Every RELABEL and RETIRE is flagged for the owner to confirm
   before anything is deleted or downgraded. ~110 packages; done by Claude, not delegated (it's
   judgment).
3. **Reference implementations** — Claude does 2–3 end-to-end as templates:
   - WIRE (metric + calibrated composite): `poptime.py` — real catcher pop time from
     `raw.statcast_poptime` / pitch geometry, tiers set from real p10/p50/p90.
   - WIRE (expose the real metric, retire the invented index): `vaa.py` — VAA from
     `raw.statcast_pitch` release/plate geometry as a raw feature.
   - RELABEL: `lineup_protect.py` (only if the owner confirms the premise-check).
4. **Delegated fan-out** — the WIRE conversions go to Sonnet subagents (own worktree + own
   `mlb_test`), one package per task, each prompt quoting: this rubric, the matching reference PR,
   the package's row in `PACKAGE_VALIDATION_STATUS.md`, and `AGENTS.md`. Claude/Fable review every
   diff and re-run tests before merge — a subagent's own green self-report is not sufficient
   (`CLAUDE.md`). RETIREs are done by Claude directly, one PR at a time, each owner-confirmed.
5. **GBM-v2** — once the WIRE raw-component columns exist, one chronological retrain with the
   expanded set (Plan 04 gate).

## Non-goals

- **Discarding the work.** The default is WIRE. RETIRE is a narrow, per-package, owner-confirmed
  exception — never a batch operation on Claude's judgment.
- Re-deriving sabermetrics from scratch. Where a published formula exists, state it verbatim and
  cite it; don't reinvent.
- Touching the ~35–40 already-governed Bucket A features (that's Plan 06's tie-out work, separate).

## Open questions for the owner

1. The default is **WIRE every package** (concept → real data, invented constants replaced with
   data-derived or cited ones, raw components become the model features, composite kept as a
   display metric). RELABEL only for premises this project's own docs reject (`clutch`,
   `lineup_protect`), RETIRE only for genuine duplicates/unfixable — both per-package and
   owner-confirmed. Does that match what you want?
2. FanGraphs "Guts!" one-time Playwright snapshot into `raw` — approved as a narrow
   `DATA_SOURCES.md` exception? (Those yearly wOBA/FIP/run-value constants are what the
   calibration step needs and the project has none.)
3. Reference-implementation picks — `poptime` + `vaa` (+ `lineup_protect` if you confirm the
   premise-check), or different.
