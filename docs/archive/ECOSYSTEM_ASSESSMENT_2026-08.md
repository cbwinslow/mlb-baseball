# MLB ecosystem assessment — 2026-08-24

> **Status: historical snapshot (2026-08-24), not maintained.** A point-in-time review kept for the record. Current direction: [`openspec/project.md`](../openspec/project.md).


## Decision

Do **not** add a git submodule, MCP server, PostgreSQL extension, or new data
source as a result of this survey. The sole accepted addition is
dev-only `hypothesis`, used by Plan 01B Log5 property tests to complement
deterministic hand-calculated fixtures. The project already has a mature,
intentional baseline and Plan 01 is still active. The practical next move is a
small, versioned research register and a sequence of tightly bounded evaluation
spikes after the current plan gates—not a tool-collection exercise.

This inventory is an admission queue, not approval to install or ingest. A
candidate needs an owner, a specific work package, rights/source-profile review,
an exact fit with the `raw`/`core`/`gold`/`meta` contract, a reproducible
`mlb_test` evaluation, and a recorded accept/defer/reject decision before it can
enter the project.

## Baseline found in this repository

The platform already contains the components that a new external project would
most commonly try to provide:

| Area | Present capability | Assessment |
| --- | --- | --- |
| Data and identity | 16 connector modules; raw artifacts/manifests; Chadwick ID crosswalk; Retrosheet, MLB Stats API, Statcast, Lahman, Baseball-Reference, prediction-market, and RSS inputs | Keep the source-specific connector contract. A generic ingestion framework or a second MLB wrapper would duplicate it. |
| Warehouse and transforms | PostgreSQL system of record; `raw`/`core`/`gold`/`meta` (and narrow `serve`) layers; migrations; an accepted SQLMesh foundation | Continue incremental SQLMesh adoption. Do not introduce dbt, a second warehouse, or a second transformation runtime. |
| Quality and operations | `mlb doctor`, `inventory`, `audit`, manifest checksums, advisory locks, `pg_dump` backups, `pg_stat_statements`, real-Postgres `mlb_test` integration tests | Add tools only when they produce a measured gap that these checks cannot expose. |
| Baseball analytics | Run expectancy/Markov/simulation, Elo/log5/GBM/stack baselines, calibration/evaluation, and feature families for offense, platoon, pitching, running, park, weather, framing, defense, workload, and markets | The limiting work is point-in-time validation and immutable feature snapshots, not a lack of algorithms. |
| Delivery and AI tooling | Current Codex skills include Qodo review/rules, deep research, data-analytics workflows, OpenAI/Cloudflare/Vercel guidance, plus a locally configured Antigravity research delegate. `prediction-markets-mcp` is documented as a development-only convenience. | Keep MCP servers out of production ingestion; call source APIs/libraries directly. |

There are no Git submodules in the current checkout. The only unrelated local
change observed while assessing was untracked `convo.txt`; it was preserved.

## Codex skills, plugins, and MCP posture

These are operator capabilities, not application dependencies. They should not
be committed to the repository or put on the critical path of `mlb bootstrap`,
research, prediction, or public serving.

| Available capability | Project use | Decision |
| --- | --- | --- |
| Qodo codebase wisdom, rules, and local-change review skills | Reconciliation, scoped rule lookup, pre-PR review | Use on demand. It complements rather than replaces the repository's real database tests and Sol gate review. |
| Antigravity local delegate | Bounded reconnaissance, mechanical implementation, repetitive test work | Use read-only `plan` mode by default and `accept-edits` only after explicit owner authorization. Require the documented `mlb_test`/no-production-write handoff. |
| Data Analytics skills | Decision reports, KPI/metric design, analysis validation | Use for a future report/dashboard only when a source-backed artifact is requested; it is not a data warehouse or feature store. |
| Cloudflare/Vercel/Astro-adjacent skills | Later serving, deployment, caching, auth, observability | Defer until Plan 05. Do not let hosting guidance pull forward a public API/site. |
| Hugging Face trainer/evaluation skills | Model-training or evaluation experiments | Defer until Plan 04 and only where the experiment register establishes a real model need. |
| PostgreSQL/Neon skill | Managed-Neon-specific design | Do not use for the current bare-metal PostgreSQL system unless the hosting decision changes. |
| Box, Google Drive, and document skills | External-document collaboration | Not needed for the local research database; connect only for an explicit document/workspace request. |
| `prediction-markets-mcp` | Interactive market reconnaissance | Retain as documented developer convenience only. The pipeline continues to use direct, provenance-recorded REST calls. |
| MLB-oriented MCP servers | Interactive lookup wrappers | Do not add. They duplicate the existing direct `pybaseball`/MLB-StatsAPI paths and weaken reproducibility if made part of ingestion. |

No new external plugin connection is currently justified: native web research,
the local repository, and the existing direct source connectors cover this
assessment without giving an external service access to project data.

## Adoption rules

1. **Reference first.** Read/cite another project's method or compare a frozen
   output before importing its code.
2. **Package before submodule.** A maintained, compatible PyPI package with a
   narrow interface is preferable to vendoring a moving repository. A submodule
   is allowed only when upstream itself must remain independently runnable and
   pinned, the license is compatible with AGPL-3.0-or-later, and the dependency
   cannot be expressed as a package, data artifact, or small reimplementation.
3. **One bounded spike.** Use fixtures and `mlb_test`, no production writes and
   no added source. Define a parity target, time/memory budget, rollback, and
   acceptance test before installation.
4. **One decision record.** Record source rights, maintenance posture, security
   surface, expected owner, versions, result, and removal plan. Rejected spikes
   stay recorded to prevent rediscovery.
5. **Integrate only after the active plan allows it.** A candidate does not
   bypass the current Plan 01/02 contracts or create a third database.

## Candidate inventory

### Baseball data, reference implementations, and possible submodules

| Candidate | Best use | Status | Why / gate |
| --- | --- | --- | --- |
| [pybaseball](https://github.com/jldbc/pybaseball) | Existing Statcast/BRef connector dependency | Retain; no submodule | Already serves the appropriate wrapper role. Its individual source paths remain subject to rights and availability checks. |
| [MLB-StatsAPI](https://github.com/toddrob99/MLB-StatsAPI) | Existing MLB Stats API dependency | Retain; no submodule | Already installed. It is a GPL-3.0 wrapper, so use it as a normal dependency and continue preserving raw responses; never copy its code. |
| [Chadwick Register](https://github.com/chadwickbureau/register) | Person-ID authority and crosswalk | Retain current source handling | The Register offers stable UUIDs and crosswalks under ODC-By; preserve release/hash provenance rather than pinning a Git submodule. |
| [Chadwick tools](https://github.com/chadwickbureau/chadwick) | Existing `cwevent`/`cwgame`/`cwbox` parser binaries | Retain external CLI | This is already the correct boundary. Do not replace it with an unmaintained Python binding or vendor the C project. |
| [Retrosheet](https://www.retrosheet.org/index.html) | Canonical historical play-by-play/box-score comparison | Retain current connector | Use its coverage/release notes in source lineage and compare formulas against it; do not introduce a duplicate loader. |
| [baseballr](https://billpetti.github.io/baseballr/) | Formula and aggregate cross-reference | Reference-only spike | An MIT R package with a useful independent implementation surface. It is not a Python runtime replacement and cannot automatically grant rights to its upstream sources. Use it to cross-check selected season aggregates. |
| [baseball.computer](https://github.com/droher/baseball.computer) | SQLMesh model-design and lineage reference | Design-reference spike; no submodule | It is especially relevant because it is SQLMesh-native and documents external model metadata. It builds a DuckDB product from a different source/serving contract, so copying its models would be a divergence risk. |
| [pybbda](https://github.com/bdilday/pybbda) | Markov/run-expectancy and Marcel reference | Parity-only spike | It implements a lineup-aware Markov run-expectancy tool. Compare a frozen synthetic fixture, not its data access or application architecture. |
| `retrosplits` / `boxball` | Supplemental derived historical data | Defer | Derived data do not replace source-faithful raw ingestion. Consider only if they materially improve a documented coverage gap and their provenance/rights can be carried through. |
| Community MLB MCP servers | Interactive lookup | Reject for production | They are thin wrappers around already-owned direct sources. MCP adds an availability and prompt/tool boundary without improving reproducibility. |
| Generic sports-betting GitHub backtesters | Test ideas and anti-leakage checks | Reference-only | Most have unverified data/odds rights and incompatible schemas. Treat good patterns (walk-forward cutoff, vig removal, settlement at observed price) as review checklists, never as drop-in components. |

**Submodule conclusion:** none of the candidates satisfies the submodule bar
today. The strongest references (`baseball.computer`, `pybbda`) should be read,
version-pinned in a research record, and exercised through disposable fixture
comparisons. This preserves the project's independent architecture and keeps
license/data lineage clear.

### Python ecosystem

| Candidate | Fit | Recommendation and acceptance gate |
| --- | --- | --- |
| [PyMC](https://www.pymc.io/) + [ArviZ](https://python.arviz.org/) | Hierarchical partial pooling, uncertainty intervals, posterior predictive checks | **High-value future spike in Plan 04.** Start with a small season-to-date player-rate model and compare it with existing empirical/shrinkage baselines on rolling-origin log loss, Brier/calibration, runtime, and diagnostic health. Store posterior/artifact metadata immutably. |
| [Bambi](https://bambinos.github.io/bambi/) | Formula-level Bayesian GLM interface on PyMC | Defer behind PyMC | Adopt only if a PyMC spike proves the project needs repeated mixed-effect models and the formula layer improves, rather than hides, point-in-time design. |
| [Polars](https://docs.pola.rs/) + PyArrow | Faster local parsing/columnar research | Benchmark-only | Pandas/COPY is already deliberate. Benchmark an actual Statcast/Retrosheet parse and load; adopt only for a measured bottleneck with identical values, null semantics, and artifact lineage. Do not create dual dataframe implementations casually. |
| [Pandera](https://pandera.readthedocs.io/) | Declarative dataframe contracts at raw promotion boundaries | Narrow evaluation | It could make schema-drift expectations executable, but existing raw tolerance and `mlb doctor` checks are valuable. Trial one source with a precise failure/reporting comparison; do not replace database integration tests. |
| [Hypothesis](https://hypothesis.readthedocs.io/) | Property tests for parsers, event state transitions, and ID reconciliation | **Adopted dev-only for Plan 01B.** | `tests/unit/test_log5_properties.py` verifies Log5 bounds, complement symmetry, league-average identity, equal-team identity, and monotonicity. Keep hand-calculated fixtures as the authoritative arithmetic evidence; add new generative tests only for stated invariants. |
| Optuna | Budgeted, registered hyperparameter search | Defer to experiment governance | Useful only after immutable snapshots and rolling validation are complete. It must not select on the final holdout or create untracked sweeps. |
| MLflow | Experiment/artifact tracking | Reject for now | `meta` already owns provenance and the roadmap requires a project-native immutable contract. A second experiment metadata system would split the source of truth. |
| Great Expectations / Soda | Dataset quality framework | Reject for now | Existing health checks, SQLMesh audits, and database tests are aligned with the actual relational grains. Reconsider only if repeated policy/observability gaps prove a unified declarative layer is cheaper. |
| DuckDB | Local research / SQLMesh candidate engine | Retain only where already used | It must not become a second system of record or a production serving database. |
| dbt | SQL transformations | Reject | SQLMesh is an explicit architecture decision. |
| Airflow, Dagster, Prefect | Workflow orchestration | Reject for now | Cron + `flock`, source locks, and pending workflow serialization are the simpler $0 fit. |
| Evidently / similar monitoring suites | ML drift reports | Defer | First implement feature/prediction freshness, calibration, and forward monitoring in `meta`/`gold`; add an external dashboard only if it closes a measured reporting gap. |

### PostgreSQL administration and extensions

| Capability | Decision | Required evidence before a change |
| --- | --- | --- |
| [`pg_stat_statements`](https://www.postgresql.org/docs/current/pgstatstatements.html) | **Adopted.** Keep it as the primary query-planning/execution evidence. | Continue filtering out unrelated cluster workload; no extra work implied. |
| [`pg_trgm`](https://www.postgresql.org/docs/current/pgtrgm.html) | Available for ad-hoc research; **do not add to conformance.** | A user-facing similarity query may justify a narrow index/migration. ID-based reconciliation remains authoritative. |
| HypoPG | Defer; useful only as a session-local DBA aid. | A slow, measured query and a candidate index whose hypothetical plan is materially better; validate the real index separately before retaining it. |
| `pgstattuple`, `pageinspect`, `pg_buffercache`, `amcheck` | Ad-hoc DBA toolbox, not a standing dependency. | An actual bloat, cache, or corruption investigation. |
| TimescaleDB | Declined for now. | Repeated representative time-range workload failures after normal partitions/indexes/materialized gold tables are optimized. |
| `pgvector` | Defer. | A named, rights-approved embedding feature and a similarity-search consumer; assess storage, versioning, retrieval quality, and public-safe behavior. |
| `pg_cron` | Declined. | A demonstrated coordination requirement that cron + `flock` and advisory locks cannot meet. |
| PostGIS / Apache AGE | Declined. | A real spatial or graph query product; venue coordinates alone are insufficient. |
| [`pgTAP`](https://pgtap.org/) | **Adopted for a narrow Plan 01B contract.** | `tests/pgtap/log5.pg` independently verifies Log5 identities and the `gold.prediction` storage contract in a rolled-back transaction. pgTAP 1.3.4 and `pg_prove` are installed locally for PostgreSQL 16; CI installs the matching extension in its disposable service container. Keep pgTAP limited to database-native contracts that pytest expresses less clearly. |

## Methodology and research shelf

Add these to the existing knowledge-base process as citations with a question,
population, formula, rights, leakage risks, reproduction design, and linked
feature/model ID—not as informal bookmarks.

| Reference | Contribution to this project | Suggested first use |
| --- | --- | --- |
| Tango, Lichtman & Dolphin, [*The Book: Playing the Percentages in Baseball*](https://www.insidethebook.com/) | Run expectancy, leverage, lineup, win-probability, and decision-analysis foundations | Anchor the Markov and simulation-family methodology; recreate only claims supported by project data. |
| FanGraphs [wOBA](https://library.fangraphs.com/offense/woba/), [wRC+](https://library.fangraphs.com/offense/wrc/), and [linear weights](https://library.fangraphs.com/principles/linear-weights/) | Explicit definitions, year-varying constants, and park/league adjustment rationale | Keep as formula citations and tie-out references; do not assume third-party constants are point-in-time available without versioning them. |
| Baumer, Jensen & Matthews, [openWAR](https://arxiv.org/abs/1312.7158) | Open, reproducible overall-player-value methodology | Research-architecture reference: decomposed components and uncertainty, not a goal to copy or expose as an identical metric. |
| Jensen, Shirley & Wyner, [hierarchical Bayesian hitting performance](https://arxiv.org/abs/0902.1360) | Partial pooling of player performance | Candidate design for small-sample hitter/pitcher rates after a PyMC spike. |
| [Hierarchical Bayesian Bradley–Terry for MLB](https://arxiv.org/abs/1712.05879) | Team rankings and probability prediction with hierarchical structure | Challenging alternative to Elo/log5; compare fairly on the same chronological cutoffs. |
| [Hierarchical Bayesian pitch framing](https://arxiv.org/abs/1704.00823) | Context-adjusted umpire/catcher/pitch effects | Methodology reference for the existing framing family, with strict source-era and location-coverage flags. |
| [MLB Statcast glossary](https://www.mlb.com/glossary/statcast) and [CSV dictionary](https://baseballsavant.mlb.com/csv-docs) | Field definitions and measurement-era notes | Canonical raw-data references for every Statcast-derived feature. |
| [Retrosheet coverage/release page](https://www.retrosheet.org/index.html) | Historical availability and known reconstructed-game coverage | Required coverage citation in cross-era studies and tests. |
| [Gneiting & Raftery, Strictly Proper Scoring Rules](https://doi.org/10.1198/016214506000001437) | Proper scores and calibration reasoning | Evaluation reference for log loss/Brier/coverage; reinforces the project's "not accuracy alone" rule. |

## Proposed sequence

1. **Now (no dependency change):** create research-register records for the
   ten references above and a candidate ledger with `candidate`, `purpose`,
   `license/rights`, `owner`, `plan`, `baseline`, `success metric`, `cost`, and
   `decision` fields.
2. **After Plan 01/02 gates:** run two fixture-only parity spikes: `pybbda`
   against the project Markov model, and `baseballr` against one completed
   seasonal aggregate. Their purpose is validation, not adoption.
3. **Plan 04:** run a PyMC/ArviZ hierarchical-rate spike only after immutable
   feature snapshots and rolling evaluation are available. It must beat or add
   well-calibrated uncertainty beyond existing baselines on an untouched forward
   window.
4. **When a real performance incident occurs:** use `pg_stat_statements`, then
   optionally HypoPG, before considering Polars, TimescaleDB, ClickHouse, or a
   new extension.
5. **Quarterly or per-plan-gate:** refresh this ledger, re-check upstream
   license/maintenance status, and close stale proposals as rejected/deferred.

## Limits of this assessment

This is a web and repository inventory as of 2026-08-24, not legal advice or a
license grant. Open-source code licenses and a public endpoint do not by
themselves grant redistribution or public-serving rights to the underlying
baseball/market data. Every future source remains subject to
`docs/DATA_SOURCES.md`, `docs/SOURCE_RIGHTS.md`, and the project's source-profile
enforcement.
