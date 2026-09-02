# Plan 03 — Research knowledge base, statistics, and feature factory

## Objective

Build a governed, reusable catalog of baseball knowledge and point-in-time SQL
statistics that supports broad experimentation without uncontrolled leakage or
feature duplication.

**Status:** The first narrow, point-in-time-safe `gold.game_feature` base-family
and immutable experiment-input rehearsal are active in `mlb_test`. Broader
feature families remain gated behind their own rehearsal, audit, and
production-safe review; this does not authorize production model cutover.

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

### 03F — Feature-stage operating contract

Treat `mlb features` as a first-class reusable research build: record input
watermarks, feature-schema/version identity, row-level game-instance identity,
coverage, null rates, availability cutoffs, and a health result. Add a
`predict --reuse-features` path that consumes only a verified successful build;
the legacy combined prediction path remains compatibility behavior, not the
recommended reproducible workflow. Design immutable snapshot storage before
claiming that a build fingerprint alone can reproduce historical rows.

**Implemented first slice:** `mlb experiment snapshot` creates a narrow,
content-addressed copy of resolved `game_base_v1` rows. It records selection,
schema, input watermark, code revision, and environment/lock identity. This is
the recovery boundary for experiments; mutable `gold.game_feature` is not.

### 03G — Source-field census and feature-admission queue

Before adding another predictive feature, generate a versioned raw-to-core-to-
gold field census. For every landed raw field, record its source/table/grain,
candidate canonical destination, data type/domain/null rate/coverage, identity
role, event and availability time, retention status, and reason it is not yet
conformed or feature-eligible. Treat “not currently in `core`” as an inventory
decision, not evidence that a source field should be discarded. Prioritize
high-value game context, player, pitch, lineup, weather, venue, and market
fields, then turn approved candidates into narrow PIT-safe feature-family
proposals with research support, formula, anti-leakage contract, and test plan.
Do not bulk-copy every raw column into `core` or a giant game table: raw stays
source-faithful, `core` stays canonical, and model inputs are named `gold`
families. Publish the census and admission queue before implementing the next
feature family.

**Implemented first slice:** `mlb field-census` is a repeatable-read,
read-only raw metadata/coverage inventory with deterministic JSON and Markdown
outputs. It classifies raw fields without pretending raw-only records were
dropped. The initial queue contains 39 research-backed, timing-aware proposals
and recommends `team_prior_offense_defense_v1` plus `pitcher_workload_v1` as
the next separately gated implementation package.

**First implemented feature family:** `team_prior_offense_defense_v1`
(`mlb_baseball/model/team_rate.py`, ADR-061) adds prior rolling team
OBP/SLG/ISO/BB%/K% and prior runs-for/allowed averages as
`gold.game_feature` enrichment columns, implementing the core, point-in-time-
safe formula for admission-queue items OFF-01/02/03/08 and DEF-01. The
min-sample gates, retained denominators, and doubleheader/era-coverage tests
each of those rows' own text calls for did not land in this package and are
tracked in github.com/cbwinslow/mlb-baseball/issues/8. Same compatibility-
column status as every existing enrichment family: tested and health-checked
in isolation, not wired into the live pipeline or into `game_base_v1`.

**Admission-queue contract closed (issue #8, ADR-062):** the four sub-items
issue #8 tracked all landed. A documented min-sample gate (`MIN_PA=10` for
OBP/BB%/K%, `MIN_AB=8` for SLG/ISO — new precedent, `805ad2e`, extended with
real-value ISO test coverage in `4be0908`) replaced the earlier bare `> 0`
guard for OFF-01/02. `gold.game_feature.home_pa`/`away_pa` (migration `0051`,
`aec00dc`) retain OFF-03's PA denominator unconditionally, so a consumer can
tell a genuinely below-threshold row from one with no data at all. A
suspended/doubleheader regression test (`ee92003`) proved OFF-08/DEF-01's
`compute_run_environment()` already correctly inherits the base feature
family's postponed-observation exclusion and game-number doubleheader
ordering — no production code changed. Historical-era coverage for OFF-01
was measured directly against production `mlb` (`b75c5fc`): zero NULLs or
empty values in `bat_event_fl`/`event_cd`/`ab_fl`/`sf_fl` across every decade
from the 1900s through the 2020s (16,465,588 rows) — no gap found. DEF-01's
separate pitching-vs-defense documentation distinction was not part of
issue #8's scope and was closed in `docs/TABLE_CONTRACTS.md` and
`docs/FEATURE_ADMISSION_QUEUE.md`'s own row text.

**Second implemented feature family (PIT-03) and admission closures (PIT-04, PLN-01):**
`starter_workload.py` (ADR-068, migration `0056_starter_workload.sql`) adds starting
pitcher rest days (`home_starter_rest_days`/`away_starter_rest_days`) and trailing
7-day workload outs (`home_starter_outs_7d`/`away_starter_outs_7d`) as `gold.game_feature`
enrichment columns via Retrosheet events, reusing ADR-042's day-collapse window RANGE-frame
pattern. Admission queue rows PIT-04 (bullpen fatigue) and PLN-01 (probable starter state)
were verified and formally closed with cited commits and test coverage in
`docs/FEATURE_ADMISSION_QUEUE.md`.

## Acceptance gate

- Every feature is traceable to a registry record and canonical SQL/model.
- Point-in-time tests deliberately insert future data and prove it is excluded.
- Window calculations match hand-computed fixtures at boundary dates.
- Statistics span all required grains with explicit keys and no accidental fanout.
- A reproducible candidate-generation report distinguishes explored, promoted,
  rejected, and unavailable-under-public-profile features.
- Feature health detects duplicate game instances, missing/late availability,
  unexpected coverage changes, and stale builds before any model consumes them.
