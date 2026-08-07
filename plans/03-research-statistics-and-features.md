# Plan 03 — Research knowledge base, statistics, and feature factory

## Objective

Build a governed, reusable catalog of baseball knowledge and point-in-time SQL
statistics that supports broad experimentation without uncontrolled leakage or
feature duplication.

## Work packages

### 03A — Research registry

Define structured records for hypotheses, citations/rights, population, target,
method/formula, reported effect, uncertainty, leakage/confounding, applicability,
implementation IDs, reproduction, and negative results. Seed it from current
`RESEARCH.md`, ADRs, sabermetric literature, journals, reproducible blogs, and
public model documentation. Separate sourced knowledge from exploratory guesses.

### 03B — Grain-complete statistic backbone

Create documented canonical tables/models for pitch, sequence, plate appearance,
half-inning/inning, player-game, team-game, matchup, series, and season. Establish
base/out state and run expectancy; batter/pitcher/defense/baserunning/park/umpire/
weather/travel/rest/lineup/starter/bullpen families. Use SQLMesh models and audits.

### 03C — Windows and normalization

Generate expanding, season-to-date, rolling, exponentially weighted, and career
statistics with minimum samples, shrinkage, era/park/opponent adjustments,
handedness/platoon splits, freshness, and uncertainty. Every row carries event
time and availability time so historical snapshots reproduce what was knowable.

### 03D — Feature registry and recipes

Register formula, grain, keys, lookback, availability, null policy, version,
rights profile, cost, and tests. Implement reviewed nonlinear/interaction recipes:
age splines/quadratics, matchup effects, guarded ratios/differences, recent versus
long-term deltas, and research-backed transforms. Generate candidates from
families, not arbitrary unbounded Cartesian products.

### 03E — Immutable snapshots and pruning

Assemble narrow families into immutable target/cutoff-specific snapshots. Measure
coverage, stability, leakage, redundancy, compute/storage, and incremental value.
Retain candidate history and negative results; promote only reproducible features.

## Acceptance gate

- Every feature is traceable to a registry record and canonical SQL/model.
- Point-in-time tests deliberately insert future data and prove it is excluded.
- Window calculations match hand-computed fixtures at boundary dates.
- Statistics span all required grains with explicit keys and no accidental fanout.
- A reproducible candidate-generation report distinguishes explored, promoted,
  rejected, and unavailable-under-public-profile features.

