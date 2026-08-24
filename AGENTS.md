# MLB project operating doctrine

This file is the durable instruction set for agents working in this repository.
Read it with `CLAUDE.md`, `docs/NORTH_STAR.md`, `docs/ARCHITECTURE.md`, and the
active plan under `plans/` before changing code. When an older document conflicts
with verified current repository state, repair the stale document in the same
change rather than silently following it.

## Mission

Build a free, reproducible MLB research and forecasting platform with three
connected outputs:

1. a trustworthy historical and current baseball database;
2. a broad experimental system for statistics, feature engineering, simulation,
   and predictive modeling; and
3. an original Astro research/forecasting site that can eventually offer the
   useful product surface of an MLB odds-analysis site without copying its code,
   assets, prose, or design.

The platform should be technically deep enough to demonstrate professional data
engineering, database administration, statistical research, ML engineering, and
product-development ability. Optional advertising or affiliate monetization must
remain removable and must never influence model output or research conclusions.

## Planning and delegation

- Use GPT-5.6 Sol for planning, architecture, difficult decisions, review, and
  final verification. Do not spend Sol usage on ordinary implementation.
- Delegate bounded implementation, mechanical refactors, repetitive tests, and
  long-running reconnaissance to the configured Antigravity agent using Gemini
  3.6 Flash (Medium), normally one plan work package at a time.
- A delegated prompt must be self-contained, name the plan and exact scope, state
  whether edits are allowed, identify the dedicated test database, and require a
  changed-file/test/limitation handoff.
- Delegated agents must not merge, delete worktrees, rewrite unrelated changes,
  alter production data, or expand into the next plan. Sol reviews each gate
  before the next package begins.
- Preserve user and parallel-agent changes. Never assume a dirty worktree is
  disposable.
- Reuse the existing `mlb_test` test database for database verification;
  do not create additional test databases unless the owner explicitly asks.

## Architecture decisions

### PostgreSQL remains the system of record

Keep PostgreSQL and the existing `raw`/`core`/`gold`/`meta` layering. Do not
rename or replace foundational schemas merely for stylistic consistency.

- `raw`: source-faithful, replayable landing data and immutable snapshots.
- `core`: conformed identities and canonical facts at explicit grains.
- `gold`: derived baseball statistics, feature families, immutable feature
  snapshots, evaluation outputs, and other analysis-ready products.
- `meta`: ingestion, source, transformation, research, feature, experiment,
  artifact, and model-run provenance.
- `serve`: add only when the website contract is ready; narrow, read-only marts,
  never raw tables or arbitrary public SQL.

Every table must document its grain, natural/business key, source lineage,
time semantics, point-in-time availability, update strategy, and retention rule.
Prefer narrow domain tables joined into versioned snapshots over one ever-wider,
sparsely populated feature table.

### SQLMesh is the preferred SQL transformation framework

Adopt SQLMesh incrementally for deterministic, set-based `gold` and `serve`
models because the existing spike already demonstrated tie-outs, plans,
environments, incremental models, audits, tests, and lineage. Do not migrate the
entire system at once.

- SQLMesh owns named SQL transformations, rolling statistics, feature-family
  tables, evaluation models, research marts, and serving marts.
- Python continues to own network ingestion, file parsing, procedural identity
  resolution, genuinely sequential algorithms, model training, simulation, and
  orchestration that is clearer outside SQL.
- Keep schema/extension/role DDL in numbered migrations.
- Do not introduce dbt beside SQLMesh. Reconsider dbt only through a recorded
  architecture decision if SQLMesh fails a measured requirement or a concrete
  need for dbt's ecosystem/semantic-layer tooling outweighs operating two
  frameworks. Framework popularity alone is not a reason.

### Refactor `conform.py` without a wholesale rewrite

`conform.py` contains valuable, tested multi-pass identity logic, but it must stop
growing as a monolith. Split orchestration, identity reconciliation, games,
events, markets, and shared query execution into cohesive modules. Move stable,
set-based transformations into named SQLMesh models after exact production
tie-outs. Keep procedural or order-dependent reconciliation in Python.

Large SQL strings do not belong embedded in Python modules. New and refactored
SQL must follow these ownership rules:

- named SQLMesh model files for derived relations;
- numbered migration files for DDL;
- named, package-owned `.sql` resources for operational statements that cannot
  be SQLMesh models;
- small parameterized statements may remain inline only when moving them would
  reduce clarity.

Never duplicate a business formula across Python and SQL. Establish one canonical
definition, test cross-language parity when two implementations are necessary,
and make dependencies explicit so upstream changes propagate through lineage.

### ClickHouse is a measured future option, not a current migration

Do not add ClickHouse now. PostgreSQL already holds the present data volume and
preserves transactional constraints, joins, mutable conformance, and operational
simplicity. ClickHouse becomes a candidate read-optimized analytical replica only
after benchmarks demonstrate that indexed/partitioned PostgreSQL plus materialized
gold tables cannot satisfy a real workload, such as interactive pitch-level scans,
large feature sweeps, or website concurrency. Any trial must use representative
queries, document replication/CDC and consistency costs, and leave PostgreSQL as
the authoritative store until a separate decision says otherwise.

## Ingestion and data management

The connector contract (`bootstrap`, `update`, health checks, run tracking,
resumability, and real-Postgres integration tests) is a strong foundation. Harden
it rather than replacing it with a generic framework:

- atomic download-to-temporary-file then rename;
- checksums, source URL, retrieval time, license/profile, schema fingerprint, and
  parser version recorded for every landed artifact;
- bounded retries/backoff, rate-limit handling, archive size/member/path checks,
  and explicit partial-failure behavior;
- declared snapshot or append semantics and tested idempotency/conflict keys;
- advisory locks or equivalent protection against overlapping runs;
- raw schema-drift alerts and reviewed promotion into typed core tables;
- least-privilege ingestion roles and secrets with restrictive file permissions;
  and
- freshness, coverage, duplicate-key, referential, and point-in-time leakage
  checks visible through `mlb doctor`.

Do not introduce dlt merely to replace working source-specific connectors. It may
be evaluated for a genuinely new source only if a bounded spike shows less code
and equal replayability, provenance, testability, and operational control.

## Research and knowledge system

Treat research as versioned input to engineering, not a collection of links.
Maintain a structured knowledge base containing:

- question/hypothesis;
- source and reuse rights;
- population, seasons, target, and evaluation design;
- formula or method;
- reported effect and uncertainty;
- known leakage/confounding risks;
- applicability to available project data;
- implementation status and linked feature/model IDs; and
- reproduction notes and result.

### Formula and Cross-Reference Verification Doctrine

Every calculated sabermetric statistic, rolling rate, and model feature must:
1. Document its authoritative formula citation (e.g., FanGraphs Library, Baseball-Reference, Tangotiger/The Book, MLB Statcast specifications, or peer-reviewed research);
2. Implement exact point-in-time correctness with zero future leakage;
3. Include deterministic hand-calculated integration test fixtures verifying arithmetic precision;
4. Undergo cross-reference validation against known credible reference sources (e.g., `baseballr`, `baseball.computer`, Retrosheet box scores, or FanGraphs season aggregates) with explicit tolerance thresholds; and
5. Maintain health checks with domain bounds and null rate assertions.

Every proposed statistic or feature must link to research, a transparent baseball
or mathematical rationale, or an explicitly labeled exploratory hypothesis.
Negative results are retained so failed ideas are not repeatedly rediscovered.

## Statistics and feature platform

Create a broad but governed catalog of reusable, point-in-time-correct statistics
across these grains:

- pitch and pitch sequence;
- plate appearance;
- inning and half-inning;
- player-game and player-season;
- team-game, matchup, series, and season;
- park, umpire, weather, travel, rest, lineup, starter, and bullpen context; and
- market snapshot and forecast cutoff.

Support career/season-to-date, expanding, exponentially weighted, and rolling
windows with explicit minimum samples and shrinkage. Include handedness and
platoon splits, opponent/park/era adjustment, aging curves, uncertainty, and
availability/freshness flags.

Feature generation should be generous but not blind. Maintain a feature registry
with formula, owner, grain, entity keys, event time, availability time, lookback,
version, null policy, allowed data profiles, and tests. Generate interactions from
reviewed families: splines/polynomials for aging and nonlinear effects; matchup
interactions; ratios and differences with denominator guards; recent-versus-long
term deltas; and latent/embedding features when justified. Do not materialize an
unbounded Cartesian explosion of arbitrary products. Compute/storage may be cheap;
false discovery, leakage, and misleading certainty are not.

## Modeling and simulation program

Build depth and breadth through a target ladder rather than disconnected models:

1. pitch outcome/type/location and swing/contact quality;
2. plate-appearance outcome;
3. base/out state transitions and run expectancy;
4. inning, first-five, team-run, and full-game run distributions;
5. winner, moneyline, run line, and totals;
6. player-game props; and
7. player/team season projections.

Use Markov chains for base/out and run-state transitions and simulation to compose
granular predictions into inning/game distributions. Evaluate simple baselines
before complexity: empirical rates, log5/Elo, generalized linear models, GAMs and
hierarchical/shrinkage models. Then test regularized regression, random forests,
gradient boosting, SVMs where dataset size permits, neural/sequence models where
their structure is useful, and calibrated ensembles/stacking built only from
strictly out-of-fold predictions.

“Try many options” means a registered, reproducible experiment program:

- immutable data/feature/model versions and configurations;
- rolling-origin and nested validation;
- untouched final holdouts and true forward monitoring;
- exact matched samples and one prediction per game/cutoff;
- log loss, Brier score/decomposition, calibration, sharpness, coverage, and
  uncertainty—not accuracy alone;
- multiple-comparison controls and stability checks across seasons/eras;
- resource budgets and pruning rules; and
- champion/challenger promotion requiring practical, stable improvement.

Never use the test/forward period to choose features. Never stack in-sample base
predictions. Never claim betting value without permitted, time-stamped prices and
vig-aware evaluation.

## Code Architecture, Encapsulation, and Polymorphic Reusability

All platform code must follow strict object-oriented and modular engineering principles:

1. **Proper Encapsulation & Structured Dataclasses**:
   - Complex domain entities (models, simulations, player projections, market allocations, game states) must be encapsulated in immutable, frozen dataclasses or typed structures with clear attribute types.
   - Internal implementation details, SQL joins, and raw dictionary manipulations must not leak across domain boundaries.
2. **Polymorphic & Interoperable Interfaces**:
   - Allocators, simulators, models, and evaluators must implement polymorphic base protocols or abstract base classes (e.g. `BaseModel`, `BaseAllocator`, `BaseSimulator`) so new algorithms can be plugged in without refactoring consumer modules.
   - Input/output contracts must be strictly interoperable between database queries, CLI commands, serving marts, and downstream web APIs.
3. **Mathematical Precision & Exhaustive Documentation**:
   - Every formula must include docstrings documenting inputs, mathematical citations, bounds, and failure modes.
   - Modules must include deterministic hand-calculated test fixtures and real database integration tests.

## Product direction

Use OddsTrader only as product research. Its current MLB surface emphasizes a
daily betting grid, moneyline/run-line/total predictions, projected scores,
expected value, cover probability, ratings, best available lines, live movement,
and player props. Our differentiated product should add transparent provenance,
model cards, calibration, uncertainty, forecast-change explanations, season
replay, research queries, and engineering lineage.

With a zero-dollar data budget, do not pretend to offer a full sportsbook odds
comparison feed. Use lawfully reusable sources, distinct Polymarket/Kalshi lines,
and a client-side user-entered odds calculator until a permitted feed exists.
Market probabilities, model probabilities, fair prices, conditional playable
prices, and picks must remain separate concepts.

## Definition of done

In addition to `CLAUDE.md`:

- every change has tests at the correct grain and a production-shaped tie-out;
- SQL/model changes declare point-in-time and leakage behavior;
- docs, catalogs, lineage, and health checks change with the code;
- experiments and artifacts are immutable and reproducible from a clean clone;
- source rights and the active data profile are enforced, not merely documented;
- performance claims include representative benchmarks;
- no copied competitor design/content or unsupported “AI edge” claim ships; and
- a plan gate is complete only after Sol reviews the delegated handoff and
  verification evidence.
