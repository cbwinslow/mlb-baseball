## Why

The project can already price a whole game (Elo, log5, gradient boosting), but
it cannot say what happens on a single plate appearance. Markov chains, Monte
Carlo simulation and any play-level prediction all need that one building
block: the probability of each way a plate appearance can end, for a specific
batter, pitcher and situation.

The project tried a version of this once. `markov-v1` used team-level averages,
sat almost exactly at 50/50 and was held at review (ADR-275): MLB teams look too
alike on average to carry signal. The lesson is to work at the batter-versus-
pitcher level. Adding many team-level features to the game-win model also gave
almost nothing (ADR-086), so features must be earned one group at a time, not
added in bulk.

The owner directed on 2026-09-26 that model work should open now, starting with
this engine. This change is that go decision, scoped to the plate-appearance
engine only. It does not reopen the rest of Phase B.

## North star

A trustworthy, calibrated, point-in-time engine that returns the probability of
each plate-appearance outcome for a given batter, pitcher and game situation,
using only information known before the plate appearance. Markov chains, Monte
Carlo simulation and later pitch-level or player-projection work run on it.

## What Changes

- Add a plate-appearance dataset: one row per completed plate appearance from
  `core.play` (Retrosheet), with the batter's and pitcher's entering form from
  the existing `feat.player_form` / `feat.pitcher_form`, plus base-out state,
  park and handedness. Outcome classes use the existing Retrosheet event codes
  (strikeout, walk, hit-by-pitch, single, double, triple, home run, and
  in-play outs). Baserunning events (steals, pickoffs, wild pitches) are not
  plate-appearance outcomes and are excluded.
- Add a scoring protocol: train 2015–2023, test 2024–2025 walk-forward, judged
  by multiclass log loss and calibration. Nothing is tuned on the test seasons.
- Build the engine in a ladder. Each rung must beat the one before it on the
  test seasons or is recorded as a negative result and not adopted:
  1. league-average baseline;
  2. ratings blend (batter, pitcher, league, park; odds-ratio / log5 style,
     shrunk);
  3. multinomial gradient-boosted model over admitted features.
- Add feature groups one at a time, with a backtest after each: game situation,
  recent form, platoon, park and weather, then advanced inputs (Statcast quality
  of contact, pitch quality, umpire zone, catcher framing, defense, fatigue,
  times-through-the-order). Each group cites its source and passes the existing
  point-in-time leakage checks. Failed groups are written down, not retried.
- Put a Markov state chain and Monte Carlo simulation on top of the finished
  engine, and check that the simulation reproduces real totals (runs per game,
  home win rate) on the test seasons. Compare against `markov-v1`.
- Publish a model card for the engine that says what it can and cannot do.

## Finish line

This change is done when all of the following are true and recorded:

1. The dataset builds reproducibly and passes the leakage checks.
2. The ratings blend beats the league-average baseline on the test seasons.
3. The gradient-boosted engine beats the ratings blend on the test seasons, or
   the failure is recorded and the ratings blend is the shipped engine.
4. Predicted probabilities are calibrated on the test seasons within a
   documented tolerance.
5. The simulation reproduces test-season runs per game and home win rate within
   a documented tolerance.
6. A model card and a feature ledger (every group tried, kept or rejected, with
   the measured effect) are committed.

## Stop rule

Anything not on the finish line goes to a "later" list and does not expand this
change. Explicitly later: pitch-by-pitch prediction, neural and Bayesian
engines, player-performance projections, game-winner comparisons against market
odds, and any new data source.

## Capabilities

### New Capabilities

- `play-engine`: the plate-appearance dataset, scoring protocol, engine ladder,
  feature-group admission rules and finish line.

### Modified Capabilities

<!-- None. Existing specs are consumed, not changed. -->

## Impact

- New package code for the dataset, the ratings blend, the gradient-boosted
  engine and the simulation, built on the existing `mlb_research.backtest`
  harness, `feat.*` feature store, and leakage checks. It does not add a second
  backtest or metric implementation.
- Reads `core.play`, `core.pitch`, `feat.player_form`, `feat.pitcher_form` and
  the metric catalog. Adds no new data source, paid service, or hosted service.
- Depends on the model-readiness change (#246) verification, tasks 4.2 and 4.3,
  being run first. If that gate reports blockers, they are cleared before the
  feature-group stage.
- Publishing to PyPI or Hugging Face is out of scope (owner tabled on
  2026-09-26).
- Updates `openspec/project.md` NOW/NEXT to record the owner's go decision and
  this change.
