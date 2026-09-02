# Research platform consolidation plan — 2026-09-01

Status: proposed execution plan for owner review.

This plan turns the September 2026 repository review into an ordered engineering
program. It does **not** reopen the paused prediction ladder or Astro site. The
current product focus remains the research database. The purpose of this plan is
to convert the large amount of capability already present into a smaller number
of stable, documented, reusable interfaces.

Related current decisions and work:

- `docs/superpowers/specs/2026-09-01-research-database-v1-design.md`
- `docs/PRODUCT_DIRECTION.md`
- `docs/ARCHITECTURE.md`
- `docs/TABLE_CONTRACTS.md`
- `plans/03-research-statistics-and-features.md`
- PRs #125 and #126: game-grain batting and pitching research backbone
- `docs/CODE_REVIEW_2026-09.md` if/when PR #127 is merged

## 1. Executive decision

The repository should be developed as a layered platform, in this order:

1. ingestion, identity, rights, provenance, and conformance;
2. reproducible MLB research database;
3. researcher-facing Python/query/export interfaces;
4. forecasting and simulation laboratory;
5. market-value research;
6. consumer website and serving layer.

The bottom three layers should become excellent before the upper layers resume
active expansion.

The project does **not** need a rewrite. Its main problem is capability
accumulation and product/interface sprawl, not a bad foundation. Preserve the
working `raw` / `core` / `gold` / `meta` architecture, migrations, source rights
profiles, conformance evidence, health checks, provenance, point-in-time model
contracts, and real-PostgreSQL tests.

The engineering principle for this phase is:

> Prefer work that removes ambiguity, duplication, rebuild cost, or user friction
> over work that merely adds another endpoint, metric, model, command, extension,
> or framework.

## 2. Product definition

Use the following working product definition when evaluating scope:

> An open, reproducible MLB research database and Python toolkit that reconciles
> baseball data from multiple sources into stable identities and research grains,
> publishes validated sabermetric statistics with provenance and coverage
> metadata, supports point-in-time analysis, and provides a common foundation for
> forecasting and market-value research.

The competitive distinction should be stated precisely:

- pybaseball/baseballr make baseball data convenient to fetch;
- baseball.computer demonstrates excellent portable research-data ergonomics;
- this project should make multi-source baseball data reproducible,
  cross-referenced, rights-aware, provenance-aware, and point-in-time researchable.

Do not publicly claim to be a strict superset of another project. Compare specific
capabilities instead.

## 3. Non-goals during consolidation

Until the research product gates below are complete:

- no new Agy/Engine package families;
- no widening `gold.game_feature` simply because a candidate feature exists;
- no new website surface;
- no new model family solely to increase model count;
- no second SQL transformation framework beside SQLMesh;
- no generic orchestration framework without a measured workflow problem;
- no database extension collection for hypothetical future use;
- no broad source expansion until existing acquisition surfaces have been
  evaluated for maintainability and research value;
- no repository split while contracts are still moving.

Existing frozen model/Engine code is retained, classified, and either reused,
validated, or archived later. Freeze means stop expanding it, not delete it.

## 4. Target architecture

The intended dependency direction is from simple, reusable domain primitives up
to operational surfaces:

```text
mlb_baseball.types
        |
        +--> mlb_baseball.stats
        |          |
        |          +--> mlb_baseball.simulation
        |
        +--> mlb_baseball.research --> mlb_baseball.db
        |
        +--> mlb_baseball.ingestion --> mlb_baseball.db
        |
        +--> mlb_baseball.models
                   |
                   +--> stats + simulation + research

mlb_baseball.cli --> all application services
```

Pure baseball/statistical math must be importable without PostgreSQL, XGBoost,
or network libraries. Database-aware code may depend on pure math; pure math must
not depend on database/model orchestration.

## 5. Workstream A — finish the canonical research grain ladder

### Goal

Make common baseball questions answerable from stable, obvious relations without
reconstructing facts from raw events or the pregame feature matrix.

### Canonical conceptual surface

```text
core.player
core.team
core.game
core.play
core.pitch

gold.batting_game
gold.pitching_game
gold.baserunning_game
gold.fielding_game
gold.team_game

gold.batting_season
gold.pitching_season
gold.baserunning_season
gold.fielding_season
gold.team_season

gold.batting_career
gold.pitching_career
```

Not every item must be a physical table. Career surfaces may be views if a view
is correct and fast enough. The contract matters more than storage form.

### Rules

1. Every relation documents its grain and natural key.
2. Game-grain relations store atomic/near-atomic facts where possible.
3. Season statistics are computed from aggregated numerators/denominators, not
   averages of per-game rates.
4. Historical research values and point-in-time prediction features are distinct
   concepts even when they share formulas.
5. Unknown/unavailable values stay NULL with explicit coverage semantics; do not
   convert missing historical measurement into zero.
6. Postseason scope must be explicit, never accidental.
7. Player/team identity must use canonical conformed IDs rather than source-name
   joins.
8. Rebuilds must be idempotent and tie out to credible external references.

### Pitching representation rule

Store canonical innings work as `outs_recorded INT`. Baseball display innings
(`6.2` meaning six innings plus two outs) are formatting, not decimal arithmetic.
Derived rate calculations use outs/innings mathematically, then display baseball
notation at the edge.

### Acceptance gate

For each new research relation:

- migration/contract exists;
- exact grain uniqueness is tested;
- deterministic hand fixture is tested;
- source coverage and null behavior are documented;
- idempotent rebuild is tested against real PostgreSQL;
- at least one real player/team/season external tie-out exists where a credible
  comparator is available;
- `mlb doctor` or equivalent contract check covers material failure modes;
- no new business formula is duplicated in an unrelated model module.

## 6. Workstream B — create a canonical stats domain package

### Problem

Research/reporting code currently reuses constants and formulas that live under
`mlb_baseball.model`. That avoided duplication, but the dependency direction is
wrong: a research statistic should not conceptually depend on a prediction model.
The same formulas will increasingly be used at game, season, career, and PIT
feature grains.

### Target

Create a neutral package incrementally:

```text
mlb_baseball/stats/
    __init__.py
    definitions.py
    batting.py
    pitching.py
    baserunning.py
    fielding.py
    run_values.py
    constants.py
```

Do not move files just for symmetry. Move a formula only when it has multiple
real consumers or when current layering causes a concrete problem.

### Rules

- formulas/constants have one canonical owner;
- pure calculation functions accept typed values/arrays, not live DB connections;
- DB/report/model layers adapt their inputs to those functions;
- when SQL and Python implementations are both required, parity tests use the
  same hand-calculated fixtures;
- formulas include version/citation metadata through the Stat Registry described
  below.

### Acceptance gate

A pure stats import must work in an environment without `psycopg` and XGBoost.
Existing public imports remain backward compatible during migration.

## 7. Workstream C — machine-readable Stat Registry

### Goal

Make statistical meaning, provenance, coverage, validation, rights, and API/docs
metadata a first-class project contract rather than information spread across
SQL, Python, docs, ADRs, and tests.

### Proposed typed contract

A concrete implementation can use a frozen/slotted dataclass plus `StrEnum`
values. Do not introduce Pydantic merely for this registry unless validation
requirements later justify it.

Illustrative fields:

```python
@dataclass(frozen=True, slots=True)
class StatDefinition:
    id: str
    display_name: str
    version: str
    domain: StatDomain
    grain: StatGrain
    unit: StatUnit
    relation: str
    required_fields: tuple[str, ...]
    formula: str | None
    citation: str | None
    source_families: tuple[str, ...]
    coverage_start: int | None
    coverage_end: int | None
    coverage_notes: str | None
    pit_safe: bool
    null_policy: str
    rights_class: str
    validation_status: ValidationStatus
    external_tieout: str | None
    stability: StabilityStatus
```

Exact fields should be chosen from real consumers, not from this example alone.

### Registry outputs

The registry should eventually generate or feed:

- `mlb describe <stat>`;
- `mlb coverage <stat>`;
- Python `db.stats.describe(...)`;
- data dictionary entries;
- MkDocs/mkdocstrings stat reference pages;
- export manifests;
- website tooltips;
- schema comments where practical;
- validation dashboards/reports;
- machine-readable JSON metadata for external consumers.

### Important separation

The registry is not a place to invent formulas. It indexes definitions already
implemented and validated. A candidate metric can have `experimental` status,
but that status must be explicit.

### Coverage as a product primitive

Coverage should be queryable. Example categories:

- `unavailable`: source did not measure/provide it;
- `partial`: known historical gaps or event limitations;
- `complete_for_source`: expected rows available for that source/time period;
- `derived`: calculated from specified inputs;
- `estimated`: model-based rather than directly observed.

This prevents researchers from treating missing measurement as a baseball effect.

## 8. Workstream D — researcher-facing Python API

### Problem

The current supported Python surface is primarily operational: configure,
migrate, ingest, conform, build features, run predictions, health checks, and
inventory. Those functions are useful administration APIs but are not the
research experience users expect from pybaseball/baseballr-style tooling.

### Target facade

Do **not** build an ORM. Build thin typed query methods over stable research
relations.

Illustrative API:

```python
from mlb_baseball import ResearchDB

db = ResearchDB.connect()

player = db.players.search("Aaron Judge")
season = db.batting.season(season=2025, min_pa=400)
leaders = db.batting.leaders(season=2025, stat="wrc_plus", min_pa=400)
games = db.pitching.games(player_id=player.id, season=2025)
meta = db.stats.describe("woba")
coverage = db.stats.coverage("woba")
```

### Return types

- pandas is the default for migration familiarity and broad researcher adoption;
- optional `as_="polars"` and `as_="arrow"` may be added behind optional
  dependencies;
- avoid forcing XGBoost/ML dependencies on research-only consumers.

### Query API principles

- methods correspond to baseball questions and stable grains;
- no hidden network fetches in query methods;
- results come from the configured research dataset/database;
- source/provenance/coverage metadata is reachable without reading source code;
- parameter names use baseball language familiar to researchers;
- expensive/unbounded queries have explicit pagination/limits where needed;
- SQL remains inspectable and tests cover actual PostgreSQL behavior.

## 9. Workstream E — portable research releases

### Goal

PostgreSQL remains the builder/system of record. PostgreSQL must not remain a
requirement for every downstream consumer.

### Release surface

Produce versioned, rights-filtered artifacts such as:

```text
mlb-research-2026.09.01.duckdb
mlb-research-2026.09.01-parquet/
manifest.json
ATTRIBUTION.md
checksums.txt
```

Start with `public_safe`. Do not redistribute local-research/licensed source data
merely because it exists in the local warehouse.

### Manifest contract

At minimum:

- dataset version;
- schema version/migration head;
- generated timestamp;
- git commit;
- data profile;
- included sources and rights classes;
- included relations;
- relation grains;
- row counts;
- temporal coverage;
- checksums;
- known limitations;
- stat-registry version/reference.

### Why DuckDB

DuckDB is a distribution/query artifact, not a replacement system of record. It
provides a zero-server path for notebooks and local SQL while preserving the
PostgreSQL build/conformance architecture.

### Clean-consumer acceptance test

A release gate should prove that a clean environment can:

1. download/open the DuckDB or Parquet artifact;
2. list included relations;
3. query a documented player-season example;
4. inspect stat/coverage metadata;
5. reproduce the example without PostgreSQL or source credentials.

## 10. Workstream F — simplify package dependencies

### Problem

The base install currently includes ML dependencies even when a user only wants
the research database/toolkit.

### Target optional groups

Exact grouping should follow import audits, but the intended direction is:

```text
base:
  psycopg
  pandas
  requests (only if core administration needs it)
  rich

sources:
  pybaseball / selected MLB acquisition client / feedparser as actually needed

export:
  pyarrow
  openpyxl
  duckdb

ml:
  numpy
  scikit-learn
  xgboost

dev:
  pytest
  hypothesis
  ruff
  mypy
  sqlfluff
  sqlmesh
  ...
```

Do not churn dependencies until import ownership is clear. The goal is a lighter
consumer install and clearer layering, not dependency-count aesthetics.

## 11. Workstream G — decompose `cli.py` without changing behavior

### Finding

`mlb_baseball/cli.py` is the clearest structural debt: parser construction,
command handlers, formatting, orchestration, and roughly 120 frozen Engine display
commands live in one very large module/function.

### Phase 1: named handlers

Extract command bodies into named functions while preserving all CLI syntax and
tests.

### Phase 2: dispatch registry

Replace the large `if/elif args.command` chain with an explicit registry of
command name to handler. Prefer ordinary typed callables and dataclasses over a
framework.

### Phase 3: split package

Illustrative target:

```text
mlb_baseball/cli/
    __init__.py
    main.py
    parser.py
    database.py
    ingestion.py
    research.py
    operations.py
    modeling.py
    engines.py
```

The console entry point `mlb = mlb_baseball.cli:main` must remain compatible.

### Phase 4: product decision on Engine commands

Only after the mechanical refactor, decide whether frozen Engine commands remain
many top-level commands or collapse behind `mlb engine <name>`. That is a product
surface decision and requires explicit owner approval; it is not part of the
behavior-preserving refactor.

## 12. Workstream H — decompose MLB acquisition and evaluate existing clients

### Finding

`connectors/mlb_api.py` is large enough to be a subsystem. Acquisition transport
and upstream endpoint shape are not the project's primary differentiator.

### Package boundary

Preserve connector entry points while decomposing by concern:

```text
connectors/mlb/
    connector.py
    transport.py
    schedule.py
    people.py
    teams.py
    rosters.py
    venues.py
    standings.py
    gamefeed.py
    analytics.py
    replay.py
```

### External-client parity spike

Before writing more low-level MLB API glue, compare the existing connector against
current maintained options such as `sportsdataverse-py` and a modern typed MLB
Stats API client.

Representative comparison families:

- schedule;
- people/player metadata;
- roster/team metadata;
- venues;
- standings;
- live/game feed;
- transactions;
- Statcast/Savant query;
- historical behavior;
- pagination/retry/error semantics.

Measure:

- field coverage;
- type/null behavior;
- API request count;
- timeout/retry behavior;
- runtime/memory on representative pulls;
- fixture/replay testability;
- release cadence/upstream maintenance;
- ability to preserve original response artifacts;
- licensing/rights implications.

If a maintained client reliably owns HTTP + parsing, wrap it behind our adapter
and delete equivalent custom transport/parsing code. Keep project ownership of:

- raw artifact preservation;
- checksums and request metadata;
- source rights/profile enforcement;
- replayability;
- canonical loading;
- identity/conformance;
- health/coverage/provenance.

Do not let a third-party SDK's object model become the warehouse contract.

## 13. Workstream I — market acquisition and future observation model

### Near-term

Evaluate official/current SDKs for upstream transport where they reduce custom
HTTP/pagination code. Pin versions and test against captured fixtures. Keep
project-owned canonical market identity and time semantics.

### Future normalized model

When forecasting/market work resumes, separate stable contract identity from
price observations:

```text
core.market
market_observation
```

An observation should preserve at least provider, observed timestamp, relevant
bid/ask/last/implied probability fields, and volume/liquidity fields available
lawfully from that provider.

As-of selection then supports documented cutoffs such as open, 24h, 6h, 1h, and
close without overwriting history.

## 14. Workstream J — SQLMesh and structural performance

### Principle

Do not optimize full-history rebuilds that should not be full-history rebuilds.
First remove unnecessary work; then tune remaining queries.

### SQLMesh ownership candidates

Promote stable relational transformations after exact parity:

- game-grain research relations;
- season/career aggregates;
- linear weights/run-value tables;
- rolling research windows;
- derived research marts;
- later, point-in-time feature families where the SQL is set-based.

Python continues to own procedural identity, source parsing, simulations, and ML
training.

### PostgreSQL index work

Use representative `EXPLAIN (ANALYZE, BUFFERS)` and measured workloads before
adding indexes. Evaluate:

- multicolumn/covering/partial B-tree indexes;
- BRIN for very large physically chronological data (e.g. game date/season on
  event or pitch tables);
- partition pruning quality;
- HypoPG for hypothetical index experiments.

Do not add TimescaleDB, PostGIS, AGE, Citus, pgvector, pg_cron, or other
extensions without a concrete workload that justifies them.

## 15. Workstream K — test architecture and validation

### Preserve

- real PostgreSQL integration testing;
- offline network fixtures;
- Hypothesis/property tests where appropriate;
- SQLFluff/Ruff/mypy/pre-commit;
- pgTAP DB-native contracts;
- security/CI checks.

### Next improvements

1. Reconcile all docs with the current per-run isolated pytest database strategy.
2. Add randomized test ordering (e.g. `pytest-randomly`) to expose hidden order
   dependencies.
3. Finish fixture cleanup/transaction-isolation issues.
4. Only then evaluate `pytest-xdist` with one isolated DB clone per worker.
5. Add periodic mutation testing to critical pure math (stats, simulation,
   probability, identity invariants), not to the entire repository on every PR.
6. Add a clean-install/release smoke path: empty PostgreSQL -> install -> migrate
   -> small public-safe ingest -> conform -> report -> doctor -> export -> open
   portable artifact -> run documented query.

### Validation standard for public stats

For every published statistic where applicable:

- formula/citation documented;
- hand fixture;
- external tie-out;
- grain uniqueness;
- coverage/null semantics;
- idempotency;
- point-in-time classification;
- source rights classification;
- known limitations;
- reproducible dataset/code version.

## 16. Workstream L — documentation as generated/product contract

### Problem

Manual docs can lag code during stacked/parallel PRs. Current examples include
feature/export status and the package description carrying an older product
framing.

### Direction

Treat structured contracts as source material for generated docs where possible:

- Stat Registry -> stat reference and coverage docs;
- export registry -> supported formats/relations docs;
- connector registry -> source capability docs;
- table contracts -> data dictionary;
- CLI parser/registry -> command reference;
- source profiles -> rights/profile matrix.

Use MkDocs Material + mkdocstrings when the curated documentation surface is
ready. Use Quarto separately for reproducible research reports/notebooks; do not
mix product docs and research papers into one tool merely for uniformity.

### Documentation cleanup

Gradually move toward:

```text
docs/
  getting-started/
  guides/
  reference/
  architecture/
  stats/
  data/
  operations/
  development/
  adr/
  research/
  archive/
```

Do not perform a giant docs move in one PR. Migrate when documents are already
being materially changed, preserve redirects/links where practical, and keep
`docs/MAP.md` accurate throughout.

The current monolithic `docs/DECISIONS.md` and large `plans/PROGRESS.md` should
eventually become indexed smaller records or generated indexes. Do not split them
until tooling/link strategy is decided; history must not be lost.

## 17. Workstream M — agent use

AI agents should accelerate research and engineering but must not become the
source of truth for deterministic baseball values.

Good agent tasks:

- literature discovery and synthesis;
- source/API reconnaissance;
- formula candidate extraction;
- schema-to-paper mapping;
- experiment proposals;
- bounded refactors/tests;
- review and anomaly explanation;
- lineage/coverage analysis;
- documentation/report drafting.

Deterministic code owns:

- published `gold.*` values;
- canonical identity decisions under defined rules;
- feature calculations;
- model training/inference;
- probability generation;
- evaluation metrics.

Agents explain and propose; tested code computes.

The hierarchical multi-agent documentation plan is specified separately in
`2026-09-01-dox-agent-context-rollout.md` and the durable design in
`docs/AGENT_CONTEXT_ARCHITECTURE.md`.

## 18. Ordered execution sequence

### Phase 0 — reconcile current truth

- merge/review current research-grain PR stack in dependency order;
- reconcile README, `pyproject.toml` description, `plans/README.md`, docs map,
  and testing doctrine with actual current behavior;
- remove or mark stale current-state statements;
- do not start a broad refactor while the grain PR stack is moving.

Gate: one clearly documented current research workflow from clean setup through
query/export, with no contradictory instructions in root operating docs.

### Phase 1 — research grains

- complete batting/pitching game relations;
- add team/baserunning/fielding grains as supported by honest source evidence;
- build season/career rollups;
- add real tie-outs and coverage metadata.

Gate: common player/team game/season questions do not require raw-table
reconstruction.

### Phase 2 — stats contract

- create neutral `stats/` ownership where real reuse exists;
- implement the first Stat Registry;
- register the first stable research stats and coverage metadata;
- wire `describe`/coverage through Python first; CLI can follow only if it is
  useful to outside users.

Gate: at least one advanced statistic has one canonical definition, multiple
research grains if appropriate, generated metadata, and external validation.

### Phase 3 — research consumption

- add `ResearchDB` facade;
- add pandas-first query methods;
- publish rights-safe Parquet + DuckDB release artifact;
- add clean-consumer smoke tests and notebook/query recipes.

Gate: a new user can answer a player-season research question without building
the full PostgreSQL warehouse.

### Phase 4 — codebase gravity wells

- decompose CLI through behavior-preserving handlers/dispatch/package split;
- decompose MLB connector behind adapters;
- run external-client parity spike and delete redundant acquisition plumbing only
  where the evidence supports it;
- improve test ordering/parallelism after isolation gates.

Gate: large modules no longer grow by default; public facades remain stable.

### Phase 5 — incremental/performance hardening

- promote stable relational transforms to SQLMesh incrementally;
- measure BRIN/index opportunities;
- remove full-history recomputation where inputs did not change;
- validate release/bootstrap performance.

Gate: daily/research refresh cost scales primarily with changed data.

### Phase 6 — reopen forecasting

Only after prior gates:

- resume player-aware PA/Markov work;
- hierarchical/Bayesian true-talent research;
- calibrated model ladder;
- market-observation time series;
- vig-aware value evaluation;
- website serving layer.

## 19. Success measures

The consolidation is successful when an outside researcher can:

1. understand the product in under five minutes;
2. install only the capabilities they need;
3. obtain a portable rights-safe dataset without standing up PostgreSQL;
4. query intuitive game/season/career grains;
5. discover a statistic by baseball name;
6. inspect formula, coverage, source, rights, and validation metadata;
7. reproduce a published example against a versioned dataset;
8. use PostgreSQL and the full ingestion pipeline when they need deeper/local
   research;
9. later run forecasting on the same stable identities and PIT contracts.

Engineering success additionally means:

- root/package imports do not drag in unrelated DB/ML stacks;
- no giant CLI/connector file is the default place to add new behavior;
- stable relational work is incremental;
- docs are generated from machine-readable contracts where practical;
- tests are isolated, order-independent, and eventually parallelizable;
- every added framework/library demonstrably removes more maintenance than it
  adds.

## 20. Three immediate next changes after current PR stack

1. **Truth-reconciliation PR:** fix stale package/docs/testing descriptions and
   establish one current-state reading path.
2. **Stat Registry design + first implementation:** use the new batting/pitching
   grains as the first real consumer instead of designing the registry in the
   abstract.
3. **Research consumer slice:** a minimal `ResearchDB` query facade plus a
   versioned public-safe DuckDB export spike, proving the project is pleasant to
   consume before adding more producer-side capability.

Those three changes create more product value than another large batch of metrics,
models, API endpoints, or database extensions.
