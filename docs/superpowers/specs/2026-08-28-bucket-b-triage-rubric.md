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
- **The composite scoring is invented.** e.g. `BBCRI = 100 + (32.0−Chase%)·2.2 + (Take%−68.0)·1.6
  + (58.0−Whiff%)·0.8` — the weights `2.2/1.6/0.8`, the "runs per point" conversions, and the
  tier cutoffs (`≥ 116.0` = "elite") come from nowhere.
- **None are wired to data.** They take hand-typed CLI args (`mlb vaa --release-height 5.8 …`).
  Zero `get_connection()` / `raw.` / `core.` / `gold.` references. They cannot produce a number
  for a real player, cannot feed a model, cannot power a website.
- Every docstring carries the same template boilerplate ("Adheres strictly to object-oriented
  encapsulation, polymorphic protocols, and point-in-time correctness…").

The framework to fix this **already exists**. This spec is the rubric for running each Engine
package through it.

## The per-package decision (apply to every ADR-089–258 package)

Exactly one of four outcomes. Record it in `docs/PACKAGE_VALIDATION_STATUS.md`.

### KILL — the default for a package that clears none of the bars below

- Its concept is already covered by a governed feature (e.g. `xslg.py` / `babip.py` duplicate
  `statcast_expected.py`'s xwOBA/xBA work; `two_strike.py` overlaps `pitch_discipline.py`).
- Its premise is one sabermetrics has repeatedly failed to find (`clutch.py`, `lineup_protect.py`
  — this project's own `FEATURE_ADMISSION_QUEUE.md` CTX-06 and `RESEARCH.md` already say so).
- The measurable inputs don't exist in any permitted source (`docs/DATA_SOURCES.md`).
- Deleting it (module + test + CLI subcommand) is less work than governing it, and nothing
  downstream references it.

KILL means: delete the module, its `tests/unit/test_<name>.py`, its `mlb <name>` CLI subcommand
and dispatch test, and mark its ADR **Superseded** (not erased — the ADR trail stays, per
`AGENTS.md`). One PR per ~10 kills.

### KEEP-RAW — real metric, real inputs, genuine modeling value

Clears all of:
1. The underlying quantity is a **named, published metric** (VAA, HAA, active-spin %, CSW%,
   barrel%, chase%) — not an invented composite.
2. Its inputs exist in a permitted source with measured coverage (`mlb field-census --exact`).
3. It is **not** already produced by a governed feature.
4. There is a plausible mechanism for it to help a game/total/prop model (state it in one
   sentence; "it's a real stat" is not a mechanism).

KEEP-RAW conversion = a normal admission-queue entry:
- New `FEATURE_ADMISSION_QUEUE.md` row: ID, grain, exact formula + citation, PIT cutoff rule,
  null policy + coverage gate, required tests, source profile.
- Point-in-time SQL in `mlb_baseball/sql/<name>_update.sql` producing the **raw components** per
  entity per game (entering value only, zero-leakage), wired into `enrich_feature_stage()`.
- `gold.game_feature` columns via a migration; `FEATURE_REGISTRY.md` row with lineage.
- Integration test with a hand-calculated fixture + idempotency + missing-table gate, following
  `tests/integration/test_model_pitch_discipline.py`.
- The invented composite score and tier labels are **dropped** — the model weights the raw
  components itself. The `mlb <name>` CLI calculator can stay as a convenience if it reads real
  data now; otherwise delete it.

### CALIBRATE — real concept, invented magnitude, worth a data-derived version

Clears KEEP-RAW's bars 1–3 but the *value* people want is a composite grade/tier (for the
website), not a raw component. Then:
- Replace every invented constant with one **derived from our own data** (a percentile of the
  real distribution → "elite = p90", or a regression coefficient fit chronologically) or **taken
  from a cited published source** (FanGraphs Guts run values, Tango linear weights). Document the
  method inline and in the ADR.
- Same admission-queue + registry + test discipline as KEEP-RAW.
- The composite is a `gold` column too, but the ADR must state it is a **display/derived**
  metric, and it stays out of `FEATURE_COLUMNS` unless it independently earns its place in a
  chronological retrain (the raw components go in; the composite is redundant with them).

### RELABEL — keep as clearly-marked exploratory, never a feature

The concept is interesting but (a) its premise is weak/debunked, or (b) it can't be tied out or
calibrated to anything real, yet deleting it loses a genuinely useful idea.
- The module stays, but its docstring and ADR are rewritten to say **"exploratory calculator,
  unvalidated, not a model feature, not fit for the public site as fact."**
- No `gold` column, no `FEATURE_COLUMNS`, no registry row.
- Its unit test asserts internal consistency only (documented as such).

## Tie-out reference infrastructure (build once, before the fan-out)

1. `docs/reference/` — transcribed published constants with page/URL citations:
   - Tango *The Book*: RE24 matrix, base/out run-expectancy, linear weights.
   - FanGraphs Sabermetric Library: the metric definitions the Engine packages name.
   - Statcast / Baseball Savant glossary: VAA/HAA/active-spin/barrel/xStat definitions.
2. **FanGraphs "Guts!" connector** — one-time Playwright snapshot of the yearly wOBA weights,
   wOBA scale, FIP constant, and event run values (`wBB`, `wHBP`, `w1B`…) → a dated CSV in
   `downloads/` + a `raw.fangraphs_guts` table. Add a row to `docs/DATA_SOURCES.md` (currently
   lists FanGraphs as "deferred/broken" — this is a narrow, one-time, reference-constant
   exception, ToS note included). These constants are what CALIBRATE needs and the project has
   none of them today.
3. A `mlb_baseball/model/_distribution.py` helper: given a metric expression and a grain, return
   the real percentile breakpoints from our own `raw`/`core` data — so "elite = p90" is computed,
   not guessed.

## Fan-out plan

1. **Rubric review** (this doc) — owner approves the four outcomes and the bars.
2. **Triage pass** — one reading of every ADR-089–258 package (module + test + ADR), each
   assigned an outcome + one-line reason in `PACKAGE_VALIDATION_STATUS.md`. ~110 packages; a
   few hours; done by Claude, not delegated (it's judgment).
3. **Reference implementations** — Claude does 3 end-to-end, one per non-KILL outcome:
   - KEEP-RAW: `vaa.py` → `vaa_v1` (VAA from `raw.statcast_pitch` release/plate geometry).
   - CALIBRATE: `poptime.py` → data-derived catcher pop-time tiers (real p10/p50/p90).
   - RELABEL: `lineup_protect.py` → exploratory relabel.
   These become the templates.
4. **Delegated fan-out** — the KILL batches and the KEEP-RAW/CALIBRATE conversions go to Sonnet
   subagents (own worktree + own `mlb_test`), one package or one KILL-batch per task, each
   prompt quoting: this rubric, the matching reference PR, the package's row in
   `PACKAGE_VALIDATION_STATUS.md`, and `AGENTS.md`. Claude/Fable review every diff and re-run
   tests before merge — a subagent's own green self-report is not sufficient (`CLAUDE.md`).
5. **GBM-v2** — once the KEEP-RAW columns exist, one chronological retrain with the expanded set
   (Plan 04 gate). Most CALIBRATE composites will not survive it; that's expected and fine.

## Non-goals

- Re-deriving sabermetrics from scratch. Where a published formula exists, state it verbatim and
  cite it; don't reinvent.
- Keeping the invented composite scores "because they're already written." A clean raw component
  the model can weight is worth more than a pre-baked score with human-chosen weights.
- Touching the ~35–40 already-governed Bucket A features (that's Plan 06's tie-out work, separate).

## Open questions for the owner

1. KILL is the default — comfortable with aggressively deleting duplicates/debunked packages
   (probably 40–60 of the 110), keeping ADRs as "Superseded"?
2. FanGraphs Guts one-time Playwright snapshot into `raw` — approved as a `DATA_SOURCES.md`
   exception?
3. Reference-implementation set — `vaa` / `poptime` / `lineup_protect`, or different picks?
