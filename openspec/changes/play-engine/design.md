## Context

See `proposal.md` for motivation and the finish line. Facts observed on
2026-09-26 that shape the approach:

- `core.play` holds 16.3M Retrosheet plays (1903–2025) with `batter_id`,
  `pitcher_id`, `event_code`, count and outs, plus 182k partial-season 2026 rows
  from the MLB API. Retrosheet event codes 2–3 and 14–23 are plate-appearance
  endings; codes 4–13 are baserunning events.
- `core.pitch` holds 13.6M pitches (2008–2026) with Statcast measures, joinable
  to plays by game and at-bat.
- `feat.player_form` and `feat.pitcher_form` already give point-in-time 7-day,
  30-day and season-to-date rates with empirical-Bayes shrinkage, excluding the
  entering game's whole calendar day. The engine reuses them.
- Handedness is not in `core.player`. It is in `raw.retrosheet_allplayers`
  (`bat`, `throw`).
- `mlb_research.backtest` is the single home for fold construction and metrics,
  but its metrics are binary (win/loss). The engine needs multiclass log loss.
- `markov-v1` (ADR-275) failed because it used team-level averages. The game-win
  model gained almost nothing from bulk team-level features (ADR-086).

## Goals / Non-Goals

**Goals:**

- One reusable plate-appearance probability function that Markov, Monte Carlo
  and later work can call.
- Every claim of improvement backed by a paired, chronological comparison.

**Non-Goals:**

- Pitch-by-pitch prediction, neural or Bayesian engines, player projections,
  market comparison, new data sources, publishing.
- Rewriting or deleting `markov-v1` or the existing `model/markov/` package.
  The new simulation is compared with it, not swapped in silently.

## Decisions

**D1. Grain and classes.** One row per plate appearance. Classes: strikeout,
walk, hit by pitch, single, double, triple, home run, out in play, and other
(errors, interference). Intentional walks are dropped. *Alternative:* fewer
classes (on-base or not) is simpler but cannot feed a run simulation. The code
mapping is verified against Chadwick documentation and real counts in task 1.1
before anything is built on it.

**D2. Seasons.** Fit on 2015–2021, validate on 2022–2023, test once on 2024–2025.
Advanced pitch data exists from about 2015. Every choice (rung, feature group,
hyperparameter) is made on the validation seasons; the test seasons only confirm
the finally selected engine. The 2026 MLB
API rows are a later forward check, not part of this change.

**D3. Ratings blend first.** Odds-ratio blend of batter rate, pitcher rate and
league rate per outcome, using the shrunk rates already in `feat.*`, then a park
adjustment. This is the classic approach in Tango, Lichtman and Dolphin, *The
Book* (2007); the exact citation and formula are verified before use (task 2.1).
*Alternative:* going straight to gradient boosting would leave no yardstick to
tell whether the fancy model earns anything.

**D4. Gradient boosting second.** A multiclass XGBoost model, which the project
already depends on, so no new dependency. Probabilities are calibrated with the
existing calibration code. *Alternatives:* neural and Bayesian models are later
challengers, not part of this change.

**D5. Evaluation lives in `mlb_research.backtest`.** Extend it with multiclass
log loss, per-class calibration and a paired comparison, and re-export. Do not
add a second fold or metric implementation. This follows
`mlb_baseball/model/AGENTS.md`.

**D6. Where the code lives.** A new small package `mlb_baseball/pa/` (dataset
builder, ratings blend, boosted engine, simulation), with its own `AGENTS.md`
under the DOX rules. It sits outside the legacy `model/` namespace so it does not
deepen it. Pure math stays free of database reads, as in `model/markov/core.py`.

**D7. Feature groups go in one at a time.** Order: game situation, recent form
(already available), lefty/righty platoon, park and weather, then advanced groups
in this order — Statcast quality of contact, pitch quality, umpire zone, catcher
framing, defense, fatigue, times through the order. After each group, run the
paired comparison and update the feature ledger. Groups are drawn from the
existing `docs/research/feature_admission_sources.md` and
`docs/SABERMETRIC_LITERATURE_INDEX.md` before any new literature search, so prior
work is reused.

**D8. Simulation reuses what is sound.** A base-out chain over the 24 base-out
states. The engine supplies the outcome-class probabilities for each plate
appearance. Two empirical tables, both estimated from training seasons only,
connect them to the chain:
- *Advancement table:* for each outcome class and starting base-out state, the
  distribution of the resulting base-out state and runs scored, estimated from
  plate-appearance-ending events only. Double plays and other in-play results are
  part of the "out in play" class distribution rather than separate classes.
- *Between-appearance events:* steals, caught stealing, pickoffs, wild pitches,
  passed balls and balks are not engine classes. They are simulated as a separate
  event process with a per-base-out-state rate per plate appearance, so simulated
  run totals stay comparable to real games.
Existing `model/markov/core.py` is reused where its math is sound; anything not
reused is noted.

**D10. Read the sources, use their examples.** Each formula is read from its primary
source and reproduced from a worked example in it, then checked against real
values in `mlb`. Open-access papers and web pages are read directly. A paywalled
book cannot be, so it is cited as a secondary source unless the owner supplies the
excerpt; no tie-out is claimed that was not done.

**D9. Tolerances are committed before scoring.** Task 1.3 writes the calibration
and simulation tolerances into this change before the test seasons are scored,
so a result cannot pick its own pass mark.

## Risks / Trade-offs

- [Plate-appearance outcomes are noisy, so gains may be small] → Report paired
  intervals, not point estimates. A small real gain is accepted; a claim inside
  the noise is recorded as no gain.
- [Same-day leakage from doubleheaders] → Reuse `feat.*` windows that already
  exclude the entering calendar day, and run the leakage checks on the dataset.
- [Switch hitters and missing handedness] → For a switch hitter, assume the side
  opposite the pitcher's throwing hand and document it. Missing handedness stays
  missing, not defaulted.
- [Many groups tried, so a group may look good by luck] → Choose groups on
  2015–2023 validation only, and confirm the final set once on 2024–2025.
- [Untested metrics in the catalog] → Only catalogued, cited entries are used as
  inputs. Anything `implemented-untested` needs a passing test first.
- [Prerequisite gate not yet run] → The readiness verification (#246 tasks 4.2 and
  4.3) is run and its relevant blockers cleared before the first dataset build.
- [Scope creep back into Phase B generally] → The stop rule in the proposal;
  extra ideas go to the later list.

## Migration Plan

No production data changes. The engine is read-only against production `mlb`; tests use the repository's disposable per-run PostgreSQL fixtures (`tests/AGENTS.md`), never production. The dataset and models are built in DuckDB or
disposable files, read-only against production `mlb`. Each stage merges as its
own small pull request; rollback is reverting that pull request.
