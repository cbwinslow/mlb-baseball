Revalidation Audit — cbwinslow/mlb-baseball
Re-review date: 2026-09-13
Current main reviewed: 757cbca97d9270f27e67733c47a214900a56b89d
Original review baseline: 26d52a573c0a23d4c073f32175530960bd801814

Executive verdict
The original review's central conclusion remains correct:

Do not restart or re-platform this repository. Finish and consolidate the MLB research platform that already exists.

The repository is still best understood as a research infrastructure project whose strongest current architecture is:

text

External sources
      |
      v
PostgreSQL
  raw  -> source-faithful acquisition
  core -> canonical identities + relational facts
  gold -> deterministic derived/research/reporting relations
      |
      v
DuckDB
  feat.* -> point-in-time research/model features
      |
      +--> public `mlb-research`
      +--> later/internal Engine
One wording correction matters:

raw and core are the authoritative PostgreSQL system of record. gold is an important deterministic PostgreSQL-derived research/reporting layer, but it should not be described as authoritative in the same sense as raw/core.

The substantive review remains strong. The re-review found no reason to restart, migrate to another framework, replace PostgreSQL/DuckDB, adopt a workflow platform, or resume speculative website/Engine work.

However, several details in the original handoff should be amended before Claude uses it as an execution plan.

What changed after the original baseline
main moved from 26d52a... to 757cbca....

The four commits after the original review baseline are principally dependency/pre-commit/CodeQL maintenance and archived-document edits. They do not materially change the architectural findings that motivated the original review.

That makes the original architectural review highly reusable, but current-state facts and priorities still need this addendum.

Highest-confidence findings after re-review
1. The Postgres/DuckDB public contract is still inconsistent
This is the strongest confirmed finding.

Current sources disagree:

openspec/project.md says the split is at core and the derived feature/model layer is DuckDB-only.
docs/FEATURE_STORE.md says feat.* in DuckDB is the canonical point-in-time feature surface and explicitly distinguishes it from legacy gold.game_feature.
mlb_baseball/feat.py says it does not touch gold.game_feature.
docs/PUBLIC_API.md still describes root build_features() as rebuilding point-in-time gold.game_feature.
mlb_baseball/public.py::build_features() still calls model.run_features().
mlb_baseball/__init__.py re-exports that legacy function.
docs/ARCHITECTURE.md still describes gold as owning feature/model outputs in language that predates the new DuckDB boundary.
The original P0 architecture-coherence finding therefore remains correct.

But the safe fix is more precise than "silently repoint build_features()":

preserve existing legacy behavior until an explicit compatibility decision is made;
label it clearly as the legacy/internal Engine feature stage;
expose the canonical research build separately if a programmatic operator API is desired;
update docs so "point-in-time feature store" has exactly one canonical meaning;
deprecate/rename legacy behavior only through an explicit compatibility change.
2. The metric catalog validates the original concern about model/
The original review argued that the model/ directory needed classification before more model/metric expansion.

That is now empirically confirmed by the active metric-catalog work.

The first batch has already found:

modules that sound production-integrated but are actually disconnected standalone calculators;
correctly implemented formulas whose constants are not era-accurate;
unsourced Elo tuning constants;
formula-correctness tests that are not independent validation.
This is exactly why the original report argued that:

"tests pass" must not equal "scientifically validated."

Keep the catalog work. Continue it in bounded batches.

3. The feature-store and public-research designs remain excellent
The re-review still endorses:

DuckDB for portable point-in-time features;
explicit event_ts / available_ts / visible_ts semantics;
ASOF historical retrieval;
missing values remaining missing instead of becoming zero;
doubleheader/leakage checks;
model-agnostic chronological backtesting;
fold-train-only normalization for starter quality;
transparent Elo reference baseline;
a lightweight mlb-research package independent of the full operator package.
These are among the project's strongest assets.

4. Source-rights engineering remains unusually strong
The original high assessment still stands.

Keep:

fail-closed rights profiles;
separate local_research and public_safe;
no assumption that unauthenticated means redistributable;
restrictive-lineage inheritance;
publication allow-lists;
explicit source review dates/evidence;
source-rights tests.
The only communication caution remains:

AGPL licensing of this project's code and redistribution rights for upstream data are separate questions.

5. The custom migration and connector systems are still appropriate
Do not replace the SQL migration system with Alembic merely because Alembic is common.

Do not replace the connector registry with a plugin framework.

Do not add Airflow, Dagster, Prefect, Spark, Kubernetes, or another orchestration layer without a measured operational requirement.

The project still benefits from being explicit and boring here.

Corrections to the original bundle
Correction A — downgrade giant structural refactors from P0
The original 05_IMPLEMENTATION_ROADMAP.md made these P0:

split cli.py;
split connectors/mlb_api.py;
split conform.py.
I still agree that all three modules are oversized and should eventually be decomposed.

I do not now recommend doing the full splits as P0 work.

The current constitution explicitly places the one-time full-codebase quality/"vibe-code proof" pass after Phase A v1 + v1.1.

Therefore:

text

Diagnosis: STILL VALID
Recommended eventual direction: STILL VALID
Original P0 priority: REVISED
New priority: LATER / opportunistic when current work touches the module
Exceptions:

a small extraction required to finish a Phase-A feature is fine;
a correctness/import-boundary bug may justify a focused refactor;
do not launch a broad structural campaign while feature-store / metric-catalog / Phase-A release work is active.
Correction B — use the metric catalog's actual status vocabulary
The original review proposed example statuses such as:

text

experimental
published
validated
negative_result
deprecated
obsolete
The implemented catalog now has a canonical schema:

text

published
validated
implemented-untested
negative-result
archived
Do not create a second status vocabulary.

The original intent remains valid, but Claude should use the implemented catalog schema exactly unless a deliberate OpenSpec change modifies it.

The same applies to the model-inventory recommendation: extend the existing catalog rather than build a parallel inventory system wherever the catalog can express the needed fact.

Correction C — the release manifest recommendation is partially implemented
The original roadmap said "Add machine-readable release metadata."

The repository already has an export/backbone manifest containing items including:

schema version;
generated timestamp;
preset;
table list;
excluded tables;
attribution.
Therefore the revised recommendation is:

Augment the existing manifest; do not create a second manifest system.

Remaining desirable provenance includes, where practical:

dataset release/version;
exact git commit/tag;
migration/schema state;
source set/lineage summary;
verification/tie-out results;
coverage bounds;
rights decision/version.
Correction D — physical model/ reorganization is optional, not the goal
I still stand by the finding that model/ is semantically overloaded.

I do not consider a new research/ + engine/ directory tree necessary for success.

The correct order is:

text

classify
-> validate
-> archive/deprecate/keep
-> fix import boundaries
-> move only where movement buys real clarity
The current metric catalog may solve much of the semantic problem without moving files.

Treat the taxonomy in the original report as a conceptual model, not a mandatory directory plan.

Correction E — PostgreSQL authority wording
Where the original roadmap says:

text

PostgreSQL = authoritative raw/core/gold warehouse
read it as:

text

PostgreSQL raw/core = authoritative system of record
PostgreSQL gold = deterministic derived/research/reporting layer
DuckDB feat.* = canonical point-in-time feature/model-input layer
This matches the current project constitution more precisely.

Correction F — interoperability is a requirement, not a unique moat
The original review suggested making interoperability a formal fourth differentiator.

After rechecking the current ecosystem, I would refine that.

baseball.computer already advertises browser, Python, and R access. baseballr 2.0 has broad acquisition and metric coverage. pybaseball remains a familiar Python data-access surface.

Therefore:

Interoperability is table stakes and an important adoption enabler, but it should not be marketed as the primary unique advantage.

The stronger positioning is the integrated research lifecycle:

text

source
-> rights/provenance
-> repeatable acquisition
-> canonical identity
-> validated statistic
-> point-in-time feature
-> chronological experiment
-> calibration/evaluation
-> versioned publication
That combination is much more defensible.

Correction G — "commercially usable" needs careful positioning
The code being commercially usable under AGPL is useful, but permissively licensed baseball libraries also exist.

Do not imply the AGPL license alone is a competitive moat.

A stronger claim is:

the project explicitly engineers the distinction between software licensing, source-data rights, public redistribution, and owner-only research use.

That rights discipline is more distinctive than merely saying "commercially usable."

Correction H — current CI health is not fully green
The CI design still deserves the strong assessment in the original review:

Ruff;
SQLFluff;
mypy;
SQL ownership lint;
docs build;
unit tests;
real-Postgres sharded integration tests;
pgTAP;
secret scanning;
CodeQL;
dependency review;
SBOM/Scorecard/workflow lint;
commit-pinned actions.
But the current main head (757cbca...) has a failing pre-commit.ci - push status.

So distinguish:

text

CI architecture: strong
Current HEAD health: has a failure that should be cleared
Do not describe the current head as completely green until that is fixed/rechecked.

Correction I — root import coupling is real, but already explicitly deferred
Issue #111 remains open and accurately describes the eager import fan-out:

text

mlb_baseball.__init__
-> public
-> model/__init__
-> psycopg + many model modules
The issue is marked frozen/deferred until the research database v1 ships.

That is sensible.

The original diagnosis remains valid; the priority should respect the freeze unless it blocks Phase-A public-package work.

Correction J — structured logging is valid but not urgent
Issue #142 remains open and already scopes the right change:

stdlib logging;
ingestion/connector error paths first;
keep print() for user-facing CLI output;
not a blanket repository-wide conversion.
This is more precise than a generic "replace print" initiative.

Keep it as tracked operational debt, not an urgent rewrite.

Section-by-section verdict on the original documents
00_README.md
Verdict: STAND, with authority wording nuance
Still endorsed:

do not restart;
PostgreSQL raw/core foundation;
DuckDB point-in-time feature layer;
standalone mlb-research;
real PostgreSQL integration tests;
versioned SQL;
rights enforcement;
chronological evaluation;
explicit missingness;
OpenSpec;
website/Engine gating.
Amend only the implication that all PostgreSQL gold output is an authoritative system of record.

01_MASTER_PROJECT_REVIEW.md
Executive/product assessment: STAND
The project is still more valuable as research infrastructure than as an odds/prediction website.

Data architecture: STAND
The Postgres + DuckDB design remains appropriate.

Research reproducibility: STAND STRONGLY
The current feature store and backtest implementation reinforce this assessment.

mlb-research: STAND STRONGLY
The package remains intentionally independent and light.

Backtesting: STAND STRONGLY
Chronology is enforced by the harness, not merely documented.

Elo v2: STAND
The code is transparent about chosen versus sourced constants and handles missing starter data honestly.

Metric catalog: STAND, now confirmed by active work
Continue the exact pattern.

model/ concern: STAND on semantics; REVISE physical-move priority
Classify first. Move only where useful.

CLI / mlb_api.py / conform.py: STAND on debt; REVISE timing
They remain large and deserve eventual decomposition, but not ahead of Phase-A gates.

Public API drift: STAND STRONGLY
The legacy build_features() name remains ambiguous relative to the new canonical DuckDB feature store.

Documentation drift: STAND STRONGLY
The current architecture docs still contain cross-generation descriptions.

Metadata: STAND STRONGLY
The GitHub and root-package descriptions still reference the old ingestion/ML/Astro identity.

Connector registry/concurrency: STAND
Keep the explicit registry and pragmatic same-server scheduling.

Data rights: STAND STRONGLY
One of the best parts of the project.

Migration system: STAND
No Alembic migration is justified.

Configuration/global state: STAND, low priority
Explicit context is a good direction for touched code, not a project-wide DI campaign.

PostgreSQL tuning: STAND, refine solution
The hard-coded 1GB/4GB batch settings are host assumptions. Make them overridable/safe eventually; do not build an elaborate configuration framework unless needed.

Testing: STAND
Continue prioritizing invariants over vanity line coverage.

CI/security: STAND on architecture; current head has a failing pre-commit status
Dependencies: STAND
Keep mlb-research lightweight.

Logging: STAND, scoped and non-urgent
Website/Engine sequencing: STAND STRONGLY
Do not resume Phase B/C merely because old code exists.

Framework restraint: STAND STRONGLY
No evidence supports adding a heavier orchestration/data/ML framework now.

Outside-user experience: STAND as the product goal
Phase A is not yet fully exited, so treat the 5–10 minute experience as an acceptance target rather than a completed fact.

02_ARCHITECTURE_AND_DATA_PLATFORM.md
Verdict: STAND with two edits
raw/core are authoritative; gold is derived.
provenance/release-manifest recommendations should extend the existing exporter manifest rather than invent a second manifest.
Everything else remains directionally correct.

03_CODEBASE_AND_REFACTOR_FINDINGS.md
Verdict: STAND on engineering findings; REVISE scheduling
Keep the refactor philosophy.

Change:

text

large mechanical splits = P0
to:

text

large mechanical splits = later quality pass / opportunistic extraction
The public-API and import-boundary findings remain current.

04_RESEARCH_PRODUCT_AND_PUBLIC_API.md
Verdict: STAND with status-vocabulary and differentiation edits
Use the current metric catalog status enum, not the proposed alternate vocabulary.

Treat interoperability as adoption infrastructure, not the unique moat.

Keep:

lightweight public package;
dataset/feature/schema/model version separation;
point-in-time contract;
model-agnostic backtesting;
few transparent baselines;
rights visibility;
reproducible notebooks;
separate public vs internal product.
05_IMPLEMENTATION_ROADMAP.md
Verdict: NEEDS THE MOST REVISION
The findings are good; the order is not fully aligned with current Phase-A state.

Replace the original order with the revalidated roadmap below.

06_CLAUDE_EXECUTION_HANDOFF.md
Verdict: STAND on principles; REVISE immediate work order
Claude should not create duplicate OpenSpec changes for work already active.

Current active change areas include:

feature-store-v1;
metric-catalog.
Claude should inspect those first and finish/extend them in their intended bounded workflow.

Broad structural refactors should not be the immediate next action.

07_FINDINGS_CHECKLIST.md
Verdict: STAND as an eventual checklist
Interpret the CLI/MLB-API/conform split items as later quality-pass checks, not immediate gates.

Use the implemented metric status vocabulary.

Revalidated scorecard
Scores remain approximate engineering judgments.




Area	Original	Revalidated	Note
Product vision	9	9	Direction remains strong
Data architecture	9	9	Boundary is strong; docs still drift
Research reproducibility	9	9.5	Feature-store implementation strengthens the case
Ingestion architecture	8.5	8.5	Explicit/pragmatic
Database engineering	9	9	Migration/load patterns remain strong
Testing	9	9	Real PG + invariant focus
CI/security design	9	9	Current head status itself is not fully green
Public root Python API	7	6.5	Legacy build_features() ambiguity is confirmed
mlb-research	9	9	Strong separation and dependency discipline
Internal module organization	6.5	6.5	Large modules remain
Model/research semantics	6	6.5	Metric catalog is actively improving this
CLI implementation	6	6	Still oversized; defer broad cleanup
Documentation quality	9	9	Very good depth
Documentation coherence	7	6.5	Cross-generation feature wording is confirmed
Data-rights discipline	9.5	9.5	Still exceptional
Outside-user UX/readiness	7	6.5–7	Good design; Phase A/public release still finishing
Revalidated immediate roadmap
NOW-0 — do not create duplicate work
Before opening anything new:

inspect current active OpenSpec changes;
inspect current open PRs;
finish already-started bounded work before starting a repository-wide cleanup.
NOW-1 — finish feature-store-v1
The task file shows the implementation is essentially complete, with the production-scale owner verification as the key remaining explicit gate.

Finish/record that gate and close/archive the change according to the project's workflow.

Do not mix unrelated structural cleanup into this change.

NOW-2 — finish the current metric-catalog batch and continue bounded triage
The current first batch is doing exactly the right work.

Continue in small batches.

Rules:

read implementation, not only docstrings;
compare formula to source;
distinguish self-consistency tests from independent validation;
use the existing catalog schema;
do not claim validated casually;
flag disconnected/obsolete/negative-result work honestly.
NOW-3 — small architecture-coherence cleanup
After respecting active-change scope, make a small change whose goal is only to remove user-facing ambiguity.

Review:

openspec/project.md;
docs/ARCHITECTURE.md;
docs/FEATURE_STORE.md;
docs/PUBLIC_API.md;
README.md;
mlb_baseball/public.py;
mlb_baseball/__init__.py.
Desired outcome:

text

raw/core = authoritative
gold = deterministic derived research/reporting layer
feat.* = canonical point-in-time feature layer
legacy gold.game_feature = explicitly legacy/internal
Do not silently change an existing API's behavior.

NOW-4 — fix stale repository metadata
Update the GitHub/root package description to match the current research-platform identity.

Suggested direction:

Reproducible MLB research database and analytics toolkit with historical ingestion, canonical schemas, cited metrics, point-in-time features, and leakage-safe evaluation.

NOW-5 — finish Phase A / v1.1 release gates
Prioritize the constitution's actual Phase-A exit criteria over cleanup for cleanup's sake.

This includes public release/versioning and the documented research-platform gates.

LATER-1 — full structural quality pass
After Phase A:

split cli.py where justified;
split connectors/mlb_api.py;
split conform.py;
resolve eager import boundaries;
archive dead/disconnected code discovered by metric triage;
reduce global state where touched.
Use characterization/integration tests.

Do not combine these into one giant PR.

LATER-2 — operational improvements
scoped structured logging;
configurable heavy Postgres memory settings;
benchmark important workflows;
optional fresh-install schema baseline when schema stability justifies it.
AFTER PHASE A — Engine work
Only after the public research platform is stable/versioned:

proprietary/tuned model work;
market-disagreement research;
subscriber product;
advanced ensembles;
live consumer prediction UI.
Revalidated competitor/product positioning
The current ecosystem reinforces one important point:

Do not try to win by simply saying:

text

we support more baseball endpoints
or:

text

we work from Python/R/browser
Those are useful, but competitors already do substantial portions of that.

The strongest positioning is:

A versioned MLB research system that makes provenance, source rights, historical identity, point-in-time feature availability, chronological evaluation, and reproducible publication part of the data product itself.

That is harder to reproduce with a collection of download helper functions.

A useful comparison frame:

text

pybaseball / baseballr:
    excellent acquisition + analyst convenience

baseball.computer:
    excellent historical queryable database / portable access

mlb-baseball + mlb-research:
    aim for the complete auditable research lifecycle
Avoid dismissing those projects. Learn from their ergonomics and breadth.

Revalidated instructions for Claude
When this file conflicts with the original bundle, this file wins.

Claude should:

inspect current main and active OpenSpec changes;
finish active scoped work before creating new cleanup campaigns;
preserve the Postgres/DuckDB boundary;
use the existing metric catalog rather than inventing another registry;
do not treat structural module splits as P0;
do not silently repoint build_features();
use the current catalog status enum;
augment existing manifests rather than creating parallel manifest systems;
keep Phase B/C gated;
preserve real-Postgres tests, source-rights controls, versioned SQL, point-in-time rules, and leakage checks.
Final revalidated conclusion
The original review was directionally correct and remains useful.

The most important things I still strongly stand by are:

do not restart;
finish the public research platform;
Postgres raw/core + DuckDB point-in-time features is the right architecture;
mlb-research is the right flagship public surface;
metric classification/validation is higher value than adding more metrics;
research invariants matter more than vanity coverage;
data-rights engineering must remain fail-closed;
do not add heavy frameworks without measured need;
keep the website/proprietary Engine gated until Phase A is done;
fix architecture/API/documentation ambiguity before calling the public platform stable.
The most important things I revise are:

large module splits are not P0;
use the existing catalog status vocabulary;
augment, do not recreate, the release manifest;
physical model/ relocation is optional;
say raw/core authoritative, gold derived;
interoperability/commercial-code licensing are not standalone competitive moats;
current main has a pre-commit failure, even though the CI design remains strong.
That is the version I would hand to Claude today.

Original Review Bundle (preserved for traceability)
MLB Baseball Project Review Bundle
Repository: https://github.com/cbwinslow/mlb-baseball
Review basis: current main branch reviewed on 2026-09-13, head observed at 26d52a573c0a23d4c073f32175530960bd801814
Purpose: give Claude a durable, implementation-oriented record of the review findings, architectural recommendations, cleanup priorities, and execution plan.

This bundle is intentionally opinionated. It is not a request to rewrite the project. The project is already strong. The objective is to preserve the current strengths while removing architectural drift, simplifying the public contract, and consolidating old and new generations of the codebase.

Documents
01_MASTER_PROJECT_REVIEW.md
Complete review. This is the closest thing to the original long-form assessment and includes product, architecture, codebase, research, testing, CI, security, documentation, and operational findings.
02_ARCHITECTURE_AND_DATA_PLATFORM.md
Canonical architecture recommendation: PostgreSQL, raw/core/gold, DuckDB feat.*, provenance, identity, data rights, migrations, configuration, and operational concerns.
03_CODEBASE_AND_REFACTOR_FINDINGS.md
Concrete software-engineering findings. Focuses on cli.py, model/, conform.py, connectors/mlb_api.py, configuration/global state, package structure, and refactor rules.
04_RESEARCH_PRODUCT_AND_PUBLIC_API.md
Product positioning, mlb-research, public API design, point-in-time features, backtesting, Elo baseline, metric catalog, publishing, interoperability, and researcher UX.
05_IMPLEMENTATION_ROADMAP.md
Prioritized P0/P1/P2 roadmap with PR-sized phases, acceptance criteria, test requirements, risk controls, and recommended sequencing.
06_CLAUDE_EXECUTION_HANDOFF.md
Direct instructions for Claude Code. It explains how to use the review, how to inspect before changing, how to preserve behavior, when to create OpenSpec changes, and what not to do.
07_FINDINGS_CHECKLIST.md
A compact audit checklist Claude can use to track completion.
Primary conclusion
The repository should not be restarted or radically re-platformed.

The project has matured from a broad baseball prediction/website effort into a credible MLB research infrastructure project. Its strongest architecture is now:

text

External Sources
      |
      v
PostgreSQL
  raw   -> source-faithful acquisition
  core  -> canonical relational facts + identity
  gold  -> research/reporting marts
      |
      v
DuckDB
  feat.* -> point-in-time research features
      |
      +--> mlb-research public package
      +--> internal Engine / proprietary modeling
The next major gain should come from simplification, consolidation, and contract clarity, not from adding more frameworks, more metrics, or more product surfaces.

Non-negotiable preservation rules
Do not lose the following strengths while cleaning the codebase:

PostgreSQL as authoritative raw/core store.
DuckDB as the portable point-in-time research/feature layer.
mlb-research as a standalone lightweight public package.
Real PostgreSQL integration tests.
Versioned SQL and explicit migrations.
Source-rights enforcement and fail-closed publication profiles.
Point-in-time clocks and leakage checks.
Metric citations, provenance, and validation.
Connector isolation and resumability.
Historical identity reconciliation.
Chronological backtesting.
Explicit missingness instead of silent imputation.
OpenSpec-based change discipline.
Current freeze on speculative website/prediction expansion until the research platform is complete.
What success looks like
A serious outside analyst should be able to:

understand what this project is in under two minutes;
install mlb-research quickly;
load a documented MLB dataset;
understand the grain and source lineage of a table;
retrieve point-in-time features without leakage;
run a chronological backtest;
compare against a transparent reference baseline;
cite the formula/source for a metric;
reproduce a result from a versioned dataset and code commit;
do all of that without learning the internal ingestion platform first.
That is the product to optimize for.

Master Review of cbwinslow/mlb-baseball
Executive assessment
The project is substantially stronger than its earlier form. It should no longer be thought of mainly as an MLB prediction application, odds website, or collection of baseball scripts.

It is becoming a reproducible MLB research infrastructure platform with four important layers:

a source-ingestion system;
a canonical historical database;
a point-in-time research feature layer;
a public research toolkit that can support independent modeling and analysis.
The overall direction is correct.

The most important qualification is that the repository still contains architectural residue from previous generations of the project. The primary remaining problem is therefore not missing functionality. It is coherence.

The codebase currently contains excellent newer concepts alongside legacy implementations and older product assumptions. The highest-value work is to make the repository consistently express one architecture.

Review scorecard
These scores are judgment calls, not measurements.




Area	Assessment
Product vision	9/10
Data architecture	9/10
Research reproducibility	9/10
Ingestion architecture	8.5/10
Database engineering	9/10
Testing	9/10
CI/security	9/10
Public Python API	7/10
mlb-research package	9/10
Internal module organization	6.5/10
Model/research namespace	6/10
CLI implementation	6/10
Documentation quality	9/10
Documentation coherence	7/10
Data-rights discipline	9.5/10
Outside-user experience	7/10
What the project is now
The most useful interpretation of the repository is:

A reproducible, auditable MLB research database and research environment that integrates historical source acquisition, identity reconciliation, standard and advanced statistics, point-in-time features, leakage-safe evaluation, provenance, and portable research datasets.

That positioning is stronger than "MLB prediction project."

The project constitution's "two products, one database" model is the right strategic boundary:

Public: mlb-research
The public system should help a stranger build or perform credible baseball research.

It should include:

published/versioned data;
data dictionaries;
grain definitions;
formulas and citations;
point-in-time feature retrieval;
a chronological backtesting harness;
one transparent reference baseline;
notebooks and examples;
reproducible research tooling.
Internal: the Engine
The internal layer can contain:

tuned parameters;
proprietary feature combinations;
ensembles;
ranked feature-selection results;
market-disagreement research;
betting/market strategy;
subscriber content;
private backtest results;
commercial model output.
That is a strong open-source/commercial boundary.

Why the idea is valuable
The differentiator is not "more helper functions than pybaseball."

A better value proposition is:

One research system that takes the analyst from source data to reproducible experiment without forcing the analyst to solve identity, provenance, grain, leakage, and historical consistency independently.

The project can differentiate on:

commercially usable code;
research honesty;
full historical coverage;
interoperability;
reproducibility;
provenance and data rights.
Interoperability deserves to become a formal differentiator. A researcher should be able to use the project through:

Python;
R;
PostgreSQL;
DuckDB;
Parquet;
pandas;
Polars;
SQL;
notebooks;
browser-based DuckDB/WASM;
ML frameworks.
The project should not require researchers to adopt the entire application stack.

Architecture review
PostgreSQL raw -> core -> gold
The layered PostgreSQL architecture is fundamentally correct.

raw
raw should remain source-faithful and operationally resilient.

The current strategy is good because it lets the system preserve source data independently of downstream transformation bugs. Schema drift can be absorbed without requiring a full re-download.

Strengths:

source-specific landing;
replayable acquisition;
append versus replace semantics based on source shape;
observable ingestion runs;
resumable large backfills;
tolerant raw schemas;
source-specific operational handling.
Do not over-normalize raw.

core
core is one of the project's most valuable assets.

This is where the project solves painful cross-provider problems once:

player identity;
team identity;
game identity;
provider identifiers;
historical names;
doubleheaders;
event relationships;
schedule matching;
source reconciliation.
The project should increasingly market this explicitly.

A serious research user benefits when the repository can truthfully say:

MLBAM, Retrosheet, Lahman, Statcast and other identities are conformed centrally, and the rules are documented and tested.

That is high-value infrastructure.

gold
gold is appropriate for denormalized research marts and research-facing relations.

Do not "fix" gold by trying to normalize it back into OLTP shapes.

The danger is only conceptual overlap with the newer DuckDB feature layer. The boundary needs to be made explicit:

gold = research/reporting outputs from authoritative warehouse data;
feat.* in DuckDB = point-in-time derived features for model/research evaluation.
Those are different purposes.

DuckDB feature-store review
The addition of DuckDB is one of the best architectural decisions in the repository.

The strongest canonical boundary is:

text

PostgreSQL:
    authoritative acquisition + conformance

DuckDB:
    portable derived feature and experiment surface
That is excellent because DuckDB provides:

local analytical speed;
Parquet-native workflows;
simple distribution;
zero-server researcher use;
Python/R integration;
SQL access;
browser/WASM possibilities.
The project should make this the official feature architecture everywhere.

Point-in-time discipline
The project is especially strong where it models historical visibility explicitly.

Important concepts that should remain first-class:

event time;
data availability time;
visible time;
decision time;
chronological folds;
no future-row joins;
doubleheader ordering;
no forward-filling unavailable data;
no silent zero substitution for unknown historical values.
This is a real differentiator.

A feature-store guarantee like:

every value is what would have been knowable at the model's decision time

is more valuable than many additional metrics.

mlb-research review
mlb-research may eventually become the most important public-facing product.

The design direction is excellent because it is intentionally standalone.

The public package should continue to avoid depending on the full ingestion application.

Correct dependency direction:

text

mlb_baseball ---> mlb_research
Avoid:

text

mlb_research ---> mlb_baseball
The public package should remain lightweight, understandable and easy to install.

The current dependency discipline is good:

pandas;
NumPy;
DuckDB;
Hugging Face dataset access;
no forced XGBoost/scikit-learn dependency for the basic package.
This should remain a design rule.

Public experience target
The normal researcher should not need to learn the ingestion application first.

The public workflow should feel like:

python

import mlb_research as mr

df = mr.load("batting_season", season=2025)
then, when needed:

python

features = mr.get_historical_features(...)
and:

python

result = mr.backtest.run_backtest(...)
That is a coherent product.

Backtesting review
The chronological backtesting harness is unusually strong.

Important strengths:

random split is not the default research path;
chronological fold construction;
model-agnostic callbacks;
sequential model support;
deterministic evaluation ordering;
probability metrics;
calibration;
uncertainty/confidence estimates;
matched-sample comparison.
This is the right research philosophy.

Recommended extension
Research predictions should eventually be persisted with complete provenance.

A prediction record should be traceable to:

dataset version;
source versions;
feature version;
feature manifest hash;
code commit;
model name;
model version;
training cutoff;
fold;
prediction timestamp;
game key;
prediction;
actual outcome.
This would make experiment reproduction exceptionally strong.

Elo v2 review
The public Elo reference model is the right kind of baseline.

It is:

understandable;
sequential;
historically valid;
light on dependencies;
configurable;
auditable;
appropriate as a benchmark rather than a proprietary "best model."
The public baseline does not need to maximize predictive performance.

Its purpose is to establish a transparent reference.

A researcher should be able to say:

my model improved log loss/Brier score relative to the repository's reference baseline over a chronological holdout.

That is a useful scientific contract.

Keep sourced ideas and chosen/tuned parameters clearly separated.

Metric catalog review
The metric catalog is one of the strongest recent ideas.

A metric should not be considered real simply because a Python module exists.

Each metric should answer:

what is it?
what does it measure?
what is its formula?
where did the formula come from?
what data does it require?
what grain does it operate at?
where is it implemented?
is it validated?
what test proves the validation claim?
is it public or internal?
This catalog should become the mechanism for cleaning the enormous research/model surface.

Recommended expansion
Eventually use machine-readable catalogs for:

data sources;
relations;
metrics;
features;
models;
datasets.
Then generate documentation and validation from those catalogs.

That creates a semantic registry for the project.

Main code-organization problem: model/
The mlb_baseball/model/ namespace is currently the largest conceptual problem.

It appears to contain a mixture of:

metrics;
deterministic statistics;
features;
experimental research;
prediction models;
simulation;
evaluation;
market logic;
utility calculations;
legacy experiments.
Those are not one abstraction.

model/ has effectively become "anything mathematical."

That makes future maintenance harder because file placement no longer communicates intent.

Recommended taxonomy
The exact final names should be derived from dependency analysis, but a healthier conceptual structure would be similar to:

text

research/
    metrics/
    features/
    baselines/
    simulations/
    experiments/

engine/
    models/
    market/
    proprietary/
Do not perform a giant rename all at once.

Instead:

classify;
record the classification in the catalog;
move only when touching a module or when a bounded migration can be fully tested.
The goal is not churn.

The goal is to stop adding new material to an ambiguous namespace.

CLI review
The CLI has excellent functionality but excessive implementation concentration.

The command surface itself is mostly good.

Commands such as:

text

mlb bootstrap
mlb update
mlb conform
mlb build
mlb verify
mlb doctor
mlb inventory
mlb export
are sensible.

The issue is that one large cli.py owns too many responsibilities.

Recommended structure
Preserve the command names but split implementation:

text

mlb_baseball/
    cli/
        __init__.py
        parser.py
        dispatch.py
        commands/
            ingest.py
            warehouse.py
            research.py
            operations.py
            catalog.py
            experiments.py
A command handler should be independently testable.

Example shape:

python

def handle_build(args: BuildArgs, context: AppContext) -> int:
    ...
main() should become boring parser + dispatch code.

That is a major maintainability improvement with low product risk if done mechanically.

Public API drift
One concrete architectural inconsistency should be resolved early.

The newer architecture says the canonical feature layer is DuckDB.

However, older public/programmatic paths still expose a build_features() concept that maps to the previous PostgreSQL-oriented feature pipeline.

This creates an ambiguity:

python

mlb_baseball.build_features()
can reasonably be interpreted as "build the canonical feature store," even if it currently invokes older behavior.

That ambiguity should be eliminated before public API stability matters.

Possible solution:

python

build_feature_store()
for the DuckDB layer, with an explicit deprecation or rename of legacy feature-building behavior.

The important requirement is that "feature store" must have one canonical meaning.

Documentation drift
The repository has very strong documentation but several historical generations.

The correct authority chain should be:

text

openspec/project.md
    -> canonical product constitution

docs/ARCHITECTURE.md
    -> canonical technical architecture

README.md
    -> newcomer-facing summary

implementation docs
    -> implementation-specific details
If a lower layer contradicts a higher layer, treat that as a documentation bug.

This is especially important around:

PostgreSQL versus DuckDB feature ownership;
paused versus active product surfaces;
public versus private research;
dataset publication behavior;
current source-rights policy.
Archived historical docs are useful, but they should never compete with current docs for authority.

Repository/product metadata
The project's current identity has outgrown older metadata that still describes it as ingestion + ML + an oddstrader-style site.

Update:

GitHub repository description;
root pyproject.toml description;
package metadata;
badges/landing copy if needed.
Recommended positioning:

Reproducible MLB research database and analytics toolkit with historical data ingestion, canonical schemas, cited metrics, point-in-time features, and leakage-safe evaluation.

That is much closer to the actual system.

Connector review
The connector contract is strong.

The pattern around:

bootstrap();
update();
health_check();
optional backfill;
is simple enough to understand and strong enough to operate.

Do not replace it with a complex plugin framework.

mlb_api.py
This is an implementation hot spot.

It has enough responsibilities that internal decomposition would improve maintainability.

Potential internal layout:

text

connectors/mlb_api/
    __init__.py
    client.py
    schedule.py
    games.py
    people.py
    standings.py
    boxscores.py
    analytics.py
    archive.py
    loader.py
    health.py
The public connector contract should remain unchanged.

This should be a mechanical refactor, not a rewrite.

Connector concurrency
The custom concurrency logic is pragmatic.

It is good that the repository models same-host concurrency constraints based on real observed failures rather than adopting a heavyweight orchestrator prematurely.

Do not add Airflow/Dagster/Prefect merely because orchestration exists.

A future evolution could define declarative connector metadata:

python

ConnectorSpec(
    name="retrosheet_event",
    host="retrosheet.org",
    max_parallelism=1,
)
Then scheduling can be derived.

But build this only if the current hard-coded grouping becomes painful.

Data-rights review
This is one of the repository's best engineering features.

The project correctly separates:

code license;
source data rights;
redistribution eligibility;
local research usage.
Rights rules should remain executable invariants, not just prose.

Important rules:

fail closed;
restrictive lineage propagates downstream;
public export must be allow-listed;
source rights must be documented before new publication surfaces are added;
local research data must not silently become redistributable.
One communication warning:

Be precise when saying the project is "commercially usable."

The code may be commercially usable under its license while some upstream datasets have different redistribution conditions.

Make that distinction obvious.

Migration review
The custom SQL migration system is appropriate.

Strong features include:

deterministic order;
migration table;
advisory lock;
transaction handling;
support for concurrent index operations;
idempotency/recovery care;
explicit SQL ownership.
There is no clear need to move to Alembic.

Long-term improvement:

Once v1 stabilizes, consider a fresh-install baseline schema so new users do not necessarily need to replay the entire historical migration chain.

Do not remove upgrade migrations.

A baseline is an installation optimization, not a replacement for migration history.

Configuration review
Typed centralized configuration is good.

The next improvement is to reduce module-global mutable state over time.

A future application context could look like:

python

@dataclass(frozen=True)
class AppContext:
    settings: Settings
    database: Database
    logger: Logger
This would improve:

testing;
concurrency;
library reuse;
explicit dependency flow;
multi-environment execution.
This is not a P0 rewrite requirement.

It is a direction for touched code.

PostgreSQL memory/tuning review
Heavy-job tuning is sensible, but hardware assumptions should become configurable.

Values such as large work_mem and maintenance_work_mem can be reasonable on the production server and dangerous on a small user's machine.

Future options:

conservative default;
desktop profile;
server profile;
custom override.
Always prefer measurement over generic tuning.

Testing review
Testing is a major strength.

The project correctly uses real PostgreSQL for integration behavior instead of pretending all DB behavior can be mocked safely.

The test system's isolation and database-name safety checks are especially good.

Keep emphasizing invariant-based tests.

For this project, the most valuable tests are not simply line coverage.

High-value invariants include:

grain uniqueness;
identity consistency;
point-in-time correctness;
no future leakage;
source coverage;
join coverage;
idempotency;
replayability;
migration safety;
rights-boundary enforcement;
external tie-outs;
missingness behavior.
100% coverage is useful only when it supports those guarantees.

CI and security review
The project has a mature workflow set.

Strengths include:

Ruff;
SQLFluff;
mypy;
PostgreSQL integration tests;
secret scanning;
CodeQL;
dependency review;
workflow linting;
SBOM;
OpenSSF Scorecard;
docs checks;
Pages publishing.
Do not add more workflows simply to increase workflow count.

Focus on:

reliability;
clear blocking versus advisory semantics;
avoiding duplicate work;
keeping CI time reasonable;
preserving secure pinned actions.
Dependency review
The root package is intentionally broad because it operates the full platform.

That is acceptable for the operator application.

The public consumer package should remain lightweight.

Do not push full-operator dependencies into mlb-research.

Optional extras for the full package may eventually be useful, but only if dependency weight becomes a real onboarding problem.

The biggest architecture win has already happened: the public package is separate.

Package/module structure
The root package currently spans too many domains at one directory level.

Potential future grouping:

text

mlb_baseball/
    cli/
    db/
    ingestion/
    warehouse/
    research/
    operations/
    publishing/
Do not adopt this exact tree blindly.

Before moving files:

produce dependency graph;
identify import cycles;
find public import surfaces;
find tests bound to module paths;
move bounded groups;
maintain compatibility imports where useful.
The objective is clarity, not movement for its own sake.

conform.py
conform.py should be decomposed eventually, but it should not be redesigned from scratch.

It contains valuable historical knowledge and source-specific edge cases.

A possible destination:

text

conform/
    players.py
    teams.py
    identities.py
    games.py
    plays.py
    pitches.py
    markets.py
    standings.py
    pipeline.py
Move knowledge intact.

Do not "simplify" away important comments, guards or edge cases.

Logging and operations
The next operational maturity step is structured logging.

CLI output can remain human-friendly, but internals should increasingly emit structured events.

Example:

json

{
  "event": "connector_failed",
  "source": "mlb_api",
  "mode": "bootstrap",
  "stage": "analytics",
  "run_id": "...",
  "error_type": "...",
  "elapsed_ms": 12500
}
This enables:

readable CLI output;
machine parsing;
dashboards;
performance diagnosis;
postmortems;
easier support.
Website and prediction roadmap
Keeping the public website and large prediction expansion paused is correct.

The current priority should remain:

make the research database and public research platform excellent for a stranger.

The website, subscriptions, real-time predictions and market intelligence become much easier once the research substrate is stable.

Do not reverse that sequencing prematurely.

Model expansion
Do not add more model/metric files until the existing inventory is classified.

The current bottleneck is deciding which artifacts are:

sourced metric;
validated metric;
experimental metric;
negative result;
feature;
model;
simulation;
private research;
obsolete work.
The metric catalog is the right foundation.

A project becomes scientifically stronger when it can distinguish valuable work from merely existing work.

Framework restraint
Do not rebuild the system around:

Airflow;
Dagster;
Prefect;
Spark;
Kubernetes;
an ORM-first rewrite;
a second warehouse;
a generic ML platform.
The current stack is powerful enough:

text

Python
PostgreSQL
DuckDB
SQL
Parquet
uv
pytest
Use frameworks only when a measured operational problem justifies them.

Outside-user experience
This is the area where the engineering is ahead of the product experience.

A good v1 test:

Can a serious baseball analyst who has never spoken with the maintainer find the repository and produce useful research in ten minutes?

The path should be obvious.

Example:

bash

Run

$
uv add mlb-research
python

import mlb_research as mr
df = mr.load("batting_season", season=2025)
Then:

python

features = mr.get_historical_features(...)
Then:

python

result = mr.backtest.run_backtest(...)
Every step should link directly to:

grain;
data source;
limitations;
formula/provenance;
version.
Documentation review
Documentation quality is excellent.

The problem is documentation entropy.

Keep current docs conceptually small:

text

README
PROJECT CONSTITUTION
ARCHITECTURE
DATA SOURCES / DATA MODEL
CONTRIBUTING / DEVELOPMENT
Everything else can be specialized or historical.

Archived material should stay searchable but clearly non-authoritative.

What should be preserved
Do not lose these:

PostgreSQL authoritative raw/core model.
DuckDB point-in-time feature store.
standalone mlb-research.
plain versioned SQL.
real PostgreSQL integration tests.
source-rights profiles.
point-in-time clocks.
cited metrics.
chronological folds.
explicit missingness.
connector isolation.
resumability/replay.
identity reconciliation.
public/internal product boundary.
OpenSpec workflow.
paused speculative product work.
Main risks
1. Architectural ambiguity
Old PostgreSQL feature/model paths still coexist with the newer DuckDB architecture.

Resolve the canonical path.

2. Namespace entropy
model/ and cli.py carry too much meaning.

3. Public API drift
Public names must match current architecture.

4. Research credibility dilution
No metric should be considered "validated" simply because code and tests exist.

Independent tie-out and source review matter.

5. Onboarding gap
The project can do more than the average new user can easily discover.

Overall recommendation
Do not restart.

Do not re-platform.

Do not resume feature sprawl.

Instead:

make the architecture canonical;
classify the research/model inventory;
split giant modules mechanically;
strengthen mlb-research;
finish provenance;
tighten public API semantics;
improve onboarding;
only then expand downstream modeling or consumer products.
The project now has a credible chance to contribute something distinct to baseball research precisely because it is integrating the entire lifecycle:

text

source
 -> provenance
 -> ingestion
 -> identity
 -> conformance
 -> statistic
 -> metric citation
 -> point-in-time feature
 -> reproducible dataset
 -> chronological experiment
 -> calibrated evaluation
 -> export/publication
That lifecycle should become the organizing idea for the entire repository.

Architecture and Data Platform Review
Recommended canonical architecture
The project should explicitly standardize on this architecture:

text

                         +----------------------+
                         | External Data Sources|
                         +----------+-----------+
                                    |
                                    v
+------------------------------------------------------------------+
| PostgreSQL                                                       |
|                                                                  |
| raw   - source-faithful, replayable acquisition                  |
| core  - canonical relational facts and cross-source identities   |
| gold  - research/reporting marts and publishable warehouse output|
+-------------------------------+----------------------------------+
                                |
                                v
+------------------------------------------------------------------+
| DuckDB                                                           |
|                                                                  |
| feat.* - point-in-time features, research snapshots, portable ML |
+-------------------------------+----------------------------------+
                                |
                 +--------------+--------------+
                 |                             |
                 v                             v
       +-------------------+          +--------------------+
       | mlb-research      |          | Internal Engine    |
       | public toolkit    |          | proprietary work   |
       +-------------------+          +--------------------+
This boundary should be reflected consistently in:

openspec/project.md;
docs/ARCHITECTURE.md;
README.md;
docs/PUBLIC_API.md;
package APIs;
CLI help;
examples;
code comments where architecture is described.
PostgreSQL responsibilities
PostgreSQL should remain authoritative for:

raw source acquisition;
raw artifacts and ingestion lineage;
identity reconciliation;
canonical game/player/team entities;
source-to-source relationships;
constraints and referential integrity;
durable warehouse reporting relations;
ingestion observability;
migration history;
publication lineage where appropriate.
PostgreSQL is not the place to keep every experimental feature merely because SQL can do so.

DuckDB responsibilities
DuckDB should own:

point-in-time feature relations;
research snapshots;
model-input relations;
portable local analysis;
Parquet-oriented consumption;
no-server researcher workflows;
browser/WASM-compatible analytical use where feasible.
DuckDB outputs should be reproducible artifacts, not authoritative source storage.

Deleting the DuckDB feature file should be recoverable by rebuilding from authoritative PostgreSQL data.

Raw layer
Principles
Preserve source fidelity.
Avoid premature semantic transformations.
Prefer reproducibility over elegance.
Preserve enough metadata to replay and audit.
Handle schema drift intentionally.
Avoid source-specific assumptions leaking into generic loader code.
Recommended invariants
Every raw relation should eventually have metadata describing:

source;
source dataset;
source version/date if known;
acquisition run;
acquired timestamp;
expected grain;
replacement/append behavior;
redistribution profile.
Core layer
Purpose
core is the project's canonical semantic layer.

The most valuable work here is not fancy analytics. It is correctness.

Identity is a flagship feature
Cross-provider identity should be treated as a named product capability.

Document and test:

player identity resolution;
team identity resolution;
game identity resolution;
provider ID mappings;
historical rebrands;
franchise changes;
doubleheaders;
postseason/regular-season edge cases;
missing/uncertain identity.
Recommended principle
Prefer stable numeric/source identifiers over fuzzy names whenever possible.

Fuzzy matching should remain a diagnostic or explicit fallback, not a silent identity mechanism.

Gold layer
gold should be optimized for researcher consumption and reporting.

Appropriate contents include:

player-season;
team-season;
game-level box-score/statistical backbone;
career aggregates;
standings/reporting tables;
validated publishable advanced statistics;
denormalized analytical relations.
Avoid turning gold into an unbounded experimental feature dump.

Feature layer
DuckDB feat.* should have a strict contract.

Each relation should define:

entity key;
grain;
decision timestamp;
source visibility timestamp;
supported feature windows;
missing-value semantics;
feature version;
update/rebuild behavior;
leakage checks.
Four-clock thinking
Preserve the project's explicit temporal model.

At minimum distinguish:

event occurrence;
data availability;
feature visibility;
model decision time.
A point-in-time system should never silently use "event date" as a substitute for "when this information was knowable."

Provenance
Provenance should become a first-class cross-layer concept.

Dataset provenance
Every published dataset version should identify:

git commit;
schema/migration version;
export preset;
source set;
source rights profile;
generated timestamp;
data period coverage;
checks/tie-outs run;
known limitations.
Feature provenance
Each feature should eventually identify:

feature name;
feature version;
input relations;
SQL/source implementation;
visibility logic;
formula or transformation description;
metric/source citation where relevant;
validation tests.
Model/prediction provenance
Each model output should be traceable to:

dataset version;
feature version;
model implementation version;
config;
train cutoff;
evaluation fold;
git commit;
prediction timestamp.
Source rights
The existing fail-closed philosophy is excellent.

Keep these rules:

source rights are explicit;
unknown rights do not default to redistributable;
restrictive lineage propagates to downstream relations;
publication presets are allow-lists;
local-research-only data never silently enters public release bundles.
Recommended next step:

Add a machine-readable lineage graph sufficient to answer:

Why is this table publishable or not publishable?

That graph does not need to be a complex graph database. A small manifest can be enough.

Migration architecture
Keep versioned SQL migrations.

The current design is appropriate for a SQL-first warehouse.

Preserve
deterministic order;
advisory lock;
transaction handling;
support for nontransactional index operations;
migration state table;
explicit SQL review.
Future optimization
After v1 stabilizes:

create a baseline schema snapshot for new installs;
keep full migrations for upgrades;
CI test both fresh baseline installs and upgrade paths.
Do not collapse migration history prematurely.

Database performance
Prefer measured optimizations.

Good current practices
season partitioning for large event tables;
index review from production statistics;
pg_stat_statements;
evidence-based removal of unused indexes;
query-plan review;
bounded concurrency.
Recommendations
make heavy-job memory configurable;
capture representative EXPLAIN plans for important research queries;
add benchmark fixtures for top public use cases;
only adopt incremental transformation frameworks where full rebuild cost is proven problematic.
Configuration
Current typed configuration is good.

Recommended evolution:

python

@dataclass(frozen=True)
class AppContext:
    settings: Settings
    database: Database
    logger: Logger
Use explicit context for touched code over time.

Benefits:

easier testing;
less module-global mutation;
clearer concurrency;
easier library embedding;
clearer dependency boundaries.
Do not force a project-wide DI rewrite.

Observability
The project already has strong data-health concepts.

Continue unifying them.

Operational signals
For every connector/build stage, record:

run ID;
source/stage;
mode;
start/end time;
items attempted;
rows written;
items skipped;
retries;
errors;
throughput;
artifact locations/checksums where applicable.
Structured logging
Move internal logging toward structured events while preserving friendly CLI output.

Do not require a remote logging stack.

JSON-capable logs plus human rendering are enough.

Backup and reproducibility
Treat these differently:

authoritative PostgreSQL state may require backups;
raw downloaded artifacts may be replayable but expensive;
DuckDB feature store should be rebuildable;
published Parquet should be immutable/versioned;
model artifacts should be versioned separately from source data.
Document restoration priorities.

Architecture acceptance criteria
The architecture cleanup is complete when:

no current docs disagree on where features live;
no public API name points to an obsolete architecture without explicit deprecation;
mlb-research remains independent;
rights rules are enforced at publication;
every public table has documented grain/provenance;
every public feature has point-in-time semantics;
feature store rebuild is reproducible from authoritative data;
external users can understand the architecture without reading archived plans.
Codebase and Refactor Findings
Refactor philosophy
The codebase does not need a rewrite.

The correct strategy is:

preserve behavior, preserve tests, reduce ambiguity, and move responsibilities into clearer boundaries.

Every major cleanup should be mechanical first and conceptual second.

Rules
No giant repository-wide rename.
No framework migration during structural cleanup.
No speculative abstraction.
No rewriting historically tricky logic merely for style.
No deleting comments that encode production lessons.
No changing public behavior unless the change explicitly intends to.
Every move should leave compatibility shims where needed.
Every refactor PR should have narrow acceptance criteria.
1. mlb_baseball/cli.py
Finding
The CLI contains too much parsing, dispatch, orchestration, special-case command behavior, and import knowledge in one module.

The command surface itself is valuable.

The implementation concentration is the problem.

Target state
text

mlb_baseball/
    cli/
        __init__.py
        parser.py
        dispatch.py
        types.py
        commands/
            ingest.py
            database.py
            warehouse.py
            research.py
            catalog.py
            operations.py
            experiments.py
Responsibilities
parser.py

argument definitions;
subparser construction;
no business logic.
dispatch.py

maps parsed command to handler;
minimal branching.
commands/*.py

command-specific validation;
invokes service-layer functions;
owns formatting only where specific to that command.
Compatibility requirement
Keep:

python

mlb_baseball.cli:main
or a compatibility module that exposes the same console entry point.

Do not break existing shell usage.

Tests
Add/retain:

parser tests;
dispatch tests;
one test per public command family;
exit-code tests;
CLI error-message tests;
no-network unit tests where feasible.
2. mlb_baseball/model/
Finding
model/ currently communicates almost no semantic category.

It mixes deterministic metrics, feature logic, experiments, simulation, prediction and other research code.

Required first step: inventory, not moving
Produce a catalog for every module with fields such as:

yaml

module: mlb_baseball.model.example
category: metric | feature | baseline | model | simulation | experiment | utility | legacy
visibility: public | internal
status: validated | published | experimental | negative_result | obsolete
data_dependencies:
outputs:
citation:
validation:
replacement:
Do this before large-scale moves.

Future target
Possible conceptual split:

text

research/
    metrics/
    features/
    baselines/
    simulations/
    experiments/

engine/
    models/
    market/
    proprietary/
The exact final structure should be derived from the inventory.

Important safety rule
Do not assume a passing unit test proves scientific correctness.

Validation requires:

formula inspection;
source citation;
data-grain review;
point-in-time review if predictive;
independent tie-out where possible.
3. mlb_baseball/conform.py
Finding
The file is large because it contains real domain complexity.

This is architectural pressure, not evidence that the logic should be rewritten.

Refactor goal
Split by domain while preserving execution order and behavior.

Possible layout:

text

mlb_baseball/conform/
    __init__.py
    prerequisites.py
    players.py
    teams.py
    identities.py
    games.py
    plays.py
    pitches.py
    standings.py
    markets.py
    health.py
    pipeline.py
Required workflow
identify internal call graph;
add characterization tests around risky boundaries;
extract pure helpers first;
move one domain at a time;
keep public conform.run() stable;
compare row counts before/after on representative database;
run doctor/audit before merge.
What not to do
Do not replace explicit logic with a generic transformation framework merely to shrink the file.

4. mlb_baseball/connectors/mlb_api.py
Finding
The module has become too broad.

It likely contains several independent concerns:

API client behavior;
schedule acquisition;
game feeds;
boxscores;
analytics;
archives/replay;
item ledger;
bulk load;
health checks.
Target
text

mlb_baseball/connectors/mlb_api/
    __init__.py
    client.py
    schedule.py
    games.py
    boxscores.py
    people.py
    standings.py
    analytics.py
    artifacts.py
    loader.py
    health.py
Keep connector-facing API stable:

python

bootstrap()
update()
health_check()
and any supported stage-specific entry points.

Acceptance tests
bootstrap dispatch unchanged;
update unchanged;
analytics backfill/replay unchanged;
archived artifact checksum behavior unchanged;
item ledger behavior unchanged;
health checks unchanged;
integration row counts match representative fixture runs.
5. Public API inconsistency
Finding
The project now has a newer DuckDB feature-store architecture, but public/programmatic feature-building names still reflect older PostgreSQL feature logic.

This is dangerous because names become contracts.

Recommendation
Decide one canonical meaning.

Suggested:

python

build_feature_store(...)
for DuckDB.

If an older PostgreSQL feature builder must remain:

python

build_legacy_game_features(...)
or keep it internal.

If backward compatibility matters:

python

def build_features(...):
    warnings.warn(..., DeprecationWarning)
    return build_feature_store(...)
Only do this if semantics are compatible.

Do not silently change behavior without documenting it.

6. Root package exports
Review mlb_baseball/__init__.py.

Only export intentionally supported surfaces.

Avoid re-exporting internal implementation modules merely for convenience.

Define a support policy:

Stable
documented public functions/classes;
semantic-versioning expectations.
Provisional
documented but allowed to change before 1.0.
Internal
no compatibility guarantee.
This will matter if the project becomes a real package used by others.

7. Configuration/global state
Finding
Current typed settings are good, but module-global environment/config access can complicate:

concurrent tests;
library reuse;
embedding;
multiple database contexts.
Direction
For new or touched orchestration code, prefer explicit context.

python

@dataclass(frozen=True)
class AppContext:
    settings: Settings
    db: Database
    logger: logging.Logger
Do not retrofit the whole repository in one PR.

8. Database tuning
Review code that sets session-level PostgreSQL memory values.

Make large values configurable.

Recommended options:

toml

[database]
profile = "safe"  # safe | desktop | server | custom
or simple numeric overrides.

Defaults should assume modest hardware.

Heavy production settings can be explicit.

9. Logging
Finding
Human-readable prints are appropriate at the CLI boundary, but internal components benefit from structured logging.

Direction
Use stdlib logging.

Fields should include:

source;
run_id;
stage;
mode;
game/season key where relevant;
elapsed duration;
retry count;
error class.
Support:

bash

Run

$
mlb ... --log-format human
$
mlb ... --log-format json
This is optional until the logging refactor becomes active.

10. Package layout
The root mlb_baseball namespace is crowded.

Before reorganizing, generate an import/dependency inventory.

Potential target:

text

mlb_baseball/
    cli/
    db/
    ingestion/
    warehouse/
    research/
    operations/
    publishing/
Do not move files merely to satisfy a directory aesthetic.

A move is justified when it improves dependency clarity and maintenance.

11. SQL ownership
Preserve the rule:

deterministic warehouse/feature transformation logic belongs in versioned SQL files, not embedded SQL strings in Python.

This is a good architectural constraint.

Use Python for:

orchestration;
iteration;
simulation;
optimization;
model fitting;
control flow.
Use SQL for:

deterministic relational transforms;
aggregations;
warehouse builds;
point-in-time joins;
materialized research outputs.
12. Dependency discipline
Do not broaden mlb-research dependencies because the root package already has a dependency.

The consumer package should remain light.

For the operator package, consider optional extras only if install weight becomes a real issue.

Do not over-engineer extras prematurely.

13. Deprecated code handling
Legacy behavior should have one of four states:

text

active
deprecated
archived
removed
Avoid indefinite zombie code.

For deprecated code:

mark it;
document replacement;
add tests for compatibility if still supported;
define removal trigger/version.
14. Refactor acceptance criteria
A structural cleanup PR is successful when:

tests remain green;
no research outputs change unexpectedly;
no public command breaks;
imports remain compatible where promised;
module responsibilities become narrower;
no new abstraction is introduced without demonstrated value;
documentation is updated in the same PR;
code coverage/invariant coverage does not regress.
Research Product and Public API Review
Product identity
The strongest public product is not "MLB predictions."

It is:

A reproducible MLB research toolkit and dataset platform.

The project should make that identity unmistakable.

Primary user
The best target user is a technically capable baseball analyst who:

writes Python or SQL;
understands basic baseball statistics;
cares about data provenance;
needs historical reproducibility;
wants to build their own models;
does not want to rebuild identity mapping and source ingestion.
This is a better fit than optimizing first for casual sports fans.

Public product contract
The public system should allow a user to:

load historical data;
inspect grain and lineage;
retrieve point-in-time features;
compute or inspect cited metrics;
run chronological experiments;
compare against reference baselines;
export/use data in standard tools;
reproduce old results.
mlb-research
This package should be the flagship research interface.

Design goals
easy install;
no server requirement;
low dependency burden;
documented stable API;
versioned datasets;
explicit failures;
predictable caching;
SQL interoperability.
Recommended top-level API shape
Do not add everything immediately, but evolve toward a small coherent surface.

Potential shape:

python

import mlb_research as mr

mr.load(...)
mr.tables()
mr.describe(...)
mr.get_historical_features(...)
mr.verify(...)
mr.backtest
mr.elo
Avoid re-exporting dozens of unrelated helpers.

Dataset abstraction
A future dataset object could improve coherence:

python

ds = mr.dataset(version="latest")

games = ds.load("batting_game", season=2025)
info = ds.describe("batting_game")
Potential methods:

text

load
describe
schema
coverage
sources
rights
version_info
Only introduce this if it simplifies the API rather than creating wrapper clutter.

Versioning
Separate concepts clearly:

Package version
The installed Python package.

Dataset version
The published data release.

Feature schema version
The structure/meaning of feat.*.

Database migration version
The operator database schema.

Model version
A specific algorithm/config artifact.

These should not be conflated.

Document compatibility rules.

Example:

text

mlb-research 0.3.x supports dataset schema v1
feature_store v1 is compatible with dataset releases >= 0.2
Dataset metadata
Every release should include a machine-readable manifest.

Suggested fields:

json

{
  "dataset_version": "v0.2.0",
  "generated_at": "...",
  "git_commit": "...",
  "schema_version": "...",
  "relations": {},
  "sources": [],
  "coverage": {},
  "rights_profile": "public_safe",
  "verification": {},
  "limitations": []
}
Table documentation
Every public relation should document:

grain;
primary key;
source(s);
coverage period;
important null semantics;
known gaps;
update cadence;
rights;
examples.
Feature documentation
Every feature should document:

feature name;
view;
entity;
time semantics;
lookback window;
formula;
source relation;
missingness behavior;
feature version;
validation test.
Point-in-time API
The existing Feast-shaped retrieval API is a strong choice.

Keep the concept, not necessarily all Feast terminology.

Core guarantees should be explicit:

retrieval is as-of historical time;
no future observations;
no implicit zero filling;
deterministic row preservation;
clear failure for unknown features.
Backtesting
The public backtesting API should remain model-agnostic.

Do not force one ML framework.

Support:

sklearn;
XGBoost;
LightGBM/CatBoost when user chooses;
custom models;
sequential models;
pure NumPy.
The caller owns model dependencies.

The framework owns chronology and evaluation correctness.

Reference models
Ship few, strong, understandable reference models.

Recommended philosophy:

text

baseline quality > baseline quantity
A transparent Elo model is better than 15 half-supported baseline models.

Potential long-term reference ladder:

home-field prior;
Elo;
regularized logistic regression;
simple run model.
Do not publish tuned "best model" results if that conflicts with the public/private product boundary.

Metric catalog
This can become one of the project's flagship research features.

A generated public metric page could expose:

text

Metric
Definition
Formula
Source citation
Input data
Grain
Implementation permalink
Validation status
Validation test
Known limitations
That is a major credibility signal.

Research status vocabulary
Standardize metric/model maturity terms.

Suggested:

experimental
Implementation exists but is not independently validated.

published
Formula/definition is intentionally public.

validated
Implementation has been reviewed and tied out against an independent source/test.

deprecated
Known replacement exists.

negative_result
Experiment intentionally preserved because it did not add value.

Avoid vague labels like "done."

Interoperability
Design outputs to work well with:

pandas;
Polars;
R;
Arrow;
Parquet;
DuckDB;
PostgreSQL;
Jupyter;
Marimo;
CLI exports.
High-value improvement
Document direct DuckDB/Parquet usage without Python.

A researcher should be able to:

sql

SELECT *
FROM read_parquet('...');
and use the dataset.

Publication
Keep public dataset publication independent from the operator database.

A user should not need PostgreSQL just to consume released data.

Recommended publication targets:

Hugging Face dataset;
release mirror;
PyPI package;
docs site;
browser query surface.
Rights presentation
Every public table should expose rights/provenance information.

Avoid forcing users to read legal notes scattered across docs.

A describe() call could include:

text

redistribution: allowed
source: Retrosheet-derived
license_note: ...
Research notebooks
Notebooks should be examples, not hidden business logic.

All important computations should live in packages/SQL.

Notebook goals:

teach usage;
demonstrate questions;
reproduce results;
remain deterministic.
Recommended recipe categories:

player trends;
team comparisons;
park effects;
era adjustments;
point-in-time model dataset;
Elo baseline reproduction;
model comparison/calibration;
source-coverage diagnostics.
Onboarding
Create an obvious path for three personas.

Persona A: dataset consumer
bash

Run

$
pip install mlb-research
Then load data.

Persona B: researcher/modeler
Load data + point-in-time features + backtest.

Persona C: database operator/contributor
Clone full repo, configure PostgreSQL, bootstrap sources, conform, report, build, verify.

Do not make Persona A read Persona C documentation first.

Website
The public consumer website should remain paused until the research platform is strong.

The docs/query site is valuable because it directly serves the research product.

A subscriber betting/odds product is a separate later product.

Do not mix their requirements prematurely.

Commercial opportunity
The open research system can support a future commercial Engine without giving away every derived answer.

Public:

data pipeline;
dataset;
documented metrics;
feature-store mechanics;
baseline models;
evaluation framework.
Private:

tuned models;
proprietary combinations;
ranked signals;
market edge;
premium reports;
commercial predictions.
This is a defensible boundary.

Public API acceptance criteria
The public research product is ready when:

installation is simple;
first useful query is fast;
every public table has documented grain/provenance;
dataset release is versioned and reproducible;
feature retrieval is point-in-time safe;
baseline model is reproducible;
chronological backtest is easy;
errors are actionable;
rights are visible;
no public API points to an obsolete architecture.
Implementation Roadmap
Execution principle
Do not treat this roadmap as permission for a giant refactor.

Each item should become its own bounded OpenSpec change and PR where appropriate.

Preferred pattern:

text

inspect
-> characterize
-> propose
-> implement narrowly
-> test
-> verify on representative data
-> review
-> merge
-> archive change
P0: Architecture coherence
P0.1 Canonical feature architecture
Goal
Make it unambiguous that:

text

PostgreSQL = authoritative raw/core/gold warehouse
DuckDB = point-in-time feature/research layer
Inspect
openspec/project.md
docs/ARCHITECTURE.md
README.md
docs/PUBLIC_API.md
docs/FEATURE_STORE.md
mlb_baseball/feat.py
mlb_baseball/public.py
mlb_baseball/__init__.py
legacy feature/model entry points
Changes
reconcile contradictory docs;
resolve build_features() naming/semantics;
explicitly mark legacy paths if retained;
update CLI/help examples.
Acceptance
one canonical description everywhere;
no ambiguous public feature-builder API;
tests cover new public semantics.
P0.2 Research/model inventory
Goal
Classify every mlb_baseball/model/ module before adding more.

Deliverable
Machine-readable inventory with fields:

text

module
category
visibility
status
inputs
outputs
citation
validation
replacement
notes
Categories
metric;
feature;
baseline;
predictive_model;
simulation;
experiment;
utility;
legacy.
Status
experimental;
published;
validated;
negative_result;
deprecated;
obsolete.
Acceptance
every module accounted for;
no unclassified new modules allowed;
metric catalog integration where appropriate.
P0.3 Repository metadata
Update:

GitHub description;
root pyproject.toml description;
package landing copy.
Use current research-platform positioning.

This is low-risk and should happen early.

P0: Structural refactors
P0.4 Split cli.py
Scope
Mechanical split only.

Non-goals
no command redesign;
no new CLI framework;
no command renaming unless separately approved.
Sequence
extract parser creation;
extract dispatch;
move command families one at a time;
preserve mlb_baseball.cli:main;
keep tests green after each move.
Acceptance
CLI behavior unchanged;
significantly smaller entry module;
command handlers independently testable.
P0.5 Split connectors/mlb_api.py
Scope
Internal decomposition only.

Acceptance
exact connector-facing API retained;
no behavior change;
analytics replay unchanged;
fixture integration tests match.
P0.6 Split conform.py
Precondition
Only after characterization tests are strong enough.

Sequence
prerequisites;
identity;
teams;
players;
games;
plays/pitches;
standings/markets;
pipeline.
Acceptance
representative row counts identical;
doctor/audit pass;
no identity regressions.
P1: Public product
P1.1 Harden mlb-research
Work
review top-level exports;
define stable/provisional/internal API;
improve error messages;
ensure package docs match current capabilities;
verify lightweight dependency policy.
Acceptance
A new analyst can install and load useful data in under 10 minutes.

P1.2 Release manifest
Add machine-readable release metadata:

dataset version;
commit;
schema version;
source set;
coverage;
rights;
verification checks;
relation manifest.
Acceptance
A published dataset can be independently tied back to code and validation.

P1.3 Feature manifest
For every public feature:

feature version;
entity;
grain;
time semantics;
SQL implementation;
source inputs;
missingness;
tests.
Acceptance
No public feature exists without a defined point-in-time contract.

P1.4 Experiment provenance
Extend backtest/model-card outputs to capture:

dataset version;
feature version;
code commit;
fold plan;
model config;
training cutoff.
Acceptance
A result can be reproduced from recorded metadata.

P1: Research integrity
P1.5 Metric triage batches
Do not audit 150 modules in one PR.

Use batches of 10-20.

For each metric:

read implementation;
identify source/citation;
confirm formula;
confirm grain;
confirm input semantics;
run/tighten tests;
independent tie-out where possible;
assign status.
Acceptance
A validated label means more than "tests pass."

P1.6 Rights lineage
Extend rights enforcement beyond source profiles.

Build enough lineage to determine whether derived tables are publishable.

Acceptance
Publication preset can explain why each table is allowed.

P1: Operational quality
P1.7 Structured logging
Scope
Start with ingestion and build pipeline.

Use
stdlib logging.

Acceptance
human output remains pleasant;
JSON logs possible;
run IDs/source/stage/error fields available.
P1.8 Hardware-aware database settings
Move large DB session tuning into explicit config.

Acceptance
Defaults are safe on modest hardware.

P1.9 Benchmarks
Create a small benchmark suite for important operations:

fresh migration;
representative conform;
gold report;
feature build;
common research query;
export.
Do not make microbenchmarks a CI blocker unless stable.

P2: Installation and distribution
P2.1 Fresh-install baseline schema
Precondition: v1 schema stabilizes.

Create baseline for new installs while preserving upgrade migrations.

CI
Test:

baseline fresh install;
migration chain upgrade from representative older state.
P2.2 Optional root-package extras
Only if install weight becomes a real problem.

Potential:

text

[export]
[modeling]
[docs]
[all]
Avoid fragmenting source-specific functionality unnecessarily.

P2: Internal Engine readiness
Do not start until Phase A exit criteria are met.

P2.3 Engine separation
After model inventory:

move proprietary/tuned work into clear internal namespace;
preserve public reusable mechanics;
define artifact storage/versioning;
enforce no accidental publication.
P2.4 Model ladder
Only after research platform is stable.

Suggested discipline:

simple linear/logistic baselines;
count/run models;
tabular tree challenger;
simulation;
only then complex ensembles/deep models if justified.
Every model must beat a simpler baseline on chronological holdout before complexity is justified.

Suggested PR order
A practical sequence:

PR A
Metadata and documentation architecture reconciliation.

PR B
Public feature API naming cleanup/deprecation.

PR C
Model/module inventory tooling.

PR D
CLI parser/dispatch extraction.

PR E
CLI command-family extraction.

PR F
MLB API connector decomposition.

PR G
Conform characterization tests.

PR H/I/J
Conform extraction by domain.

PR K
Release manifest.

PR L
Feature manifest/provenance.

PR M
Backtest provenance.

PR N+
Metric validation batches.

This order reduces ambiguity before the largest refactors.

Definition of done for every refactor PR
OpenSpec change exists if non-trivial.
Tests written/updated first where practical.
No unexplained behavior change.
Ruff clean.
mypy clean.
SQLFluff clean where SQL touched.
SQL ownership check clean.
unit tests green.
relevant integration tests green.
docs updated.
public API compatibility reviewed.
production/representative verification performed where appropriate.
review comments addressed.
change archived after merge.
Things explicitly not to do
Do not:

restart the repository;
move to a new language;
rewrite warehouse logic in an ORM;
add Airflow/Dagster/Prefect without a measured need;
move everything to DuckDB;
move everything to PostgreSQL;
resume subscriber-site development before public research goals are done;
add dozens of new metrics before catalog triage;
treat tests as proof of scientific validity;
split into many repositories prematurely;
create speculative abstraction layers;
perform giant mechanical renames without bounded tests.
Claude Code Execution Handoff
Mission
Use the review bundle to improve cbwinslow/mlb-baseball without destabilizing it.

The project is already valuable and technically mature.

Your job is not to redesign it from scratch.

Your job is to make the current architecture explicit, coherent, maintainable and easy for outside researchers to use.

First principles
Preserve correctness before elegance.
Preserve domain knowledge and production lessons.
Avoid giant rewrites.
Use OpenSpec for non-trivial changes.
One logical change per PR.
Keep existing public behavior unless a change explicitly deprecates it.
Favor evidence from the code, tests, production verification and database behavior.
Do not invent infrastructure because a pattern "looks enterprise."
Use existing assets before creating new ones.
When architecture and old documentation conflict, current openspec/project.md is the product authority.
Canonical target architecture
Treat this as the working architecture unless repository evidence shows an intentional newer decision:

text

Sources
  |
  v
PostgreSQL
  raw
  core
  gold
  |
  v
DuckDB
  feat.*
  |
  +--> public mlb-research
  +--> internal Engine
PostgreSQL is authoritative.

DuckDB feature data is derived/rebuildable.

mlb-research is the lightweight public consumer surface.

Immediate work order
1. Inspect current state
Before changing anything:

read openspec/project.md;
read README.md;
read docs/ARCHITECTURE.md;
read docs/FEATURE_STORE.md;
read docs/PUBLIC_API.md;
inspect pyproject.toml;
inspect mlb_baseball/__init__.py;
inspect mlb_baseball/public.py;
inspect mlb_baseball/feat.py;
inspect mlb_baseball/cli.py;
inspect mlb_baseball/model/;
inspect mlb_baseball/connectors/mlb_api.py;
inspect mlb_baseball/conform.py;
inspect current OpenSpec changes and PRs.
Do not assume this review is newer than repository changes. Reconcile against current main.

2. Confirm the public feature API drift
Determine whether:

python

mlb_baseball.build_features()
still points at the older PostgreSQL feature path while the canonical feature-store path is DuckDB.

If yes, propose a bounded OpenSpec change.

Do not silently change semantics.

Recommend:

explicit build_feature_store() name;
compatibility/deprecation plan for older function;
tests;
documentation update.
3. Reconcile architecture docs
Update only current authoritative docs.

Do not rewrite frozen historical decision records.

Goal:

README;
project constitution;
architecture;
public API;
must describe the same system.

4. Build model/module inventory
Before moving model/, catalog it.

Do not guess categories from filenames alone.

Read modules.

Record:

text

category
visibility
status
citation
inputs
outputs
validation
Use the existing metric catalog where appropriate.

No new model/metric modules should be created until classification policy is clear.

5. Structural refactors
Proceed in small PRs.

CLI
Extract parser/dispatch first.

Then move command families.

Preserve command behavior.

MLB API connector
Split internal responsibilities without changing connector interface.

Conform
Add characterization tests before extracting domains.

Never rewrite source-identity logic merely to "clean it up."

Required testing posture
Use the existing repository standards.

For every change:

run targeted tests during implementation;
run broader relevant suite before PR;
use real PostgreSQL integration tests for database behavior;
run doctor/audit or representative production verification when touching conformance/reporting;
preserve point-in-time/leakage tests when touching feature code.
For research metrics, remember:

passing tests do not prove the formula is correct.

Read the implementation and source.

Dependency policy
Do not add a library until answering:

what current problem does it solve?
why existing dependency/tooling is insufficient?
what ongoing maintenance cost does it add?
can the same result be achieved with existing stack?
does it belong in operator package or public package?
Be especially conservative with:

orchestration frameworks;
ORMs;
distributed compute;
ML platforms.
Public API policy
Treat documented exports as contracts.

Before renaming/moving:

search usages;
search docs;
search tests;
identify downstream package imports;
provide compatibility shim/deprecation if appropriate.
Keep mlb-research independent from mlb_baseball.

Data-rights policy
Do not weaken fail-closed publication behavior.

When adding derived public output:

trace source lineage;
inspect source rights;
add or update rights tests;
ensure public presets remain allow-listed.
Refactor anti-patterns
Do not:

perform a "clean architecture" rewrite;
introduce interfaces solely because interfaces sound cleaner;
convert every function into a class;
replace explicit SQL with an ORM;
replace connector functions with a generic plugin framework;
move code without updating import compatibility/tests;
create duplicate implementations during migration and leave both indefinitely.
Preferred migration pattern
When replacing an old path:

text

new implementation
-> compatibility adapter
-> deprecation warning/docs
-> migration period
-> eventual removal
Only where compatibility matters.

Internal code can be cleaned more aggressively if no public contract exists.

Research validation standard
A metric/model can be marked validated only after:

implementation reviewed;
formula/source confirmed;
grain reviewed;
time semantics reviewed;
edge cases tested;
independent tie-out where feasible.
A unit test that asserts the same implementation's expected value is not an independent validation.

Outside-user test
For public-facing work, repeatedly ask:

Can a competent baseball analyst who has never met the maintainer understand and use this in ten minutes?

If not, improve naming/docs/examples before adding more capability.

Product sequencing
Do not restart website/subscriber/prediction expansion simply because old code exists.

Phase A research-platform quality remains the priority.

Resume speculative Engine/site work only when project gates in the current constitution say to do so.

Expected deliverables from Claude
For each major review recommendation:

confirm whether the finding still exists on current main;
cite exact files/symbols;
propose bounded change;
create OpenSpec artifacts if non-trivial;
implement with tests;
open PR;
address review findings;
merge only under repository merge rules;
archive OpenSpec change;
update progress/roadmap status.
Final objective
The repository should eventually be explainable in one sentence:

mlb-baseball builds and validates a canonical MLB research database; mlb-research gives analysts lightweight access to versioned data, point-in-time features and leakage-safe evaluation; proprietary modeling stays in the internal Engine.

Every architectural change should make that sentence more true.

Findings Checklist
Use this as a tracking document, not as a replacement for OpenSpec tasks.

Product/positioning
 GitHub description matches research-platform identity.
 Root pyproject.toml description updated.
 README matches project constitution.
 Public/internal boundary is obvious.
 Speculative website/prediction work remains gated.
Architecture
 PostgreSQL authoritative responsibilities documented.
 DuckDB feature-layer responsibilities documented.
 gold versus feat.* distinction documented.
 Architecture docs contain no current contradictions.
 Feature store is explicitly rebuildable.
Public API
 Review mlb_baseball.build_features() semantics.
 Canonical DuckDB feature builder has unambiguous name.
 Legacy feature behavior deprecated/renamed if necessary.
 Root exports reviewed.
 Stable/provisional/internal API policy documented.
mlb-research
 Lightweight dependencies preserved.
 Top-level API reviewed for coherence.
 Versioning policy documented.
 Dataset manifest shipped.
 Table descriptions expose grain/source/rights.
 Point-in-time retrieval contract documented.
 Backtest provenance improved.
 Reference baseline remains transparent.
Model/research inventory
 Every model/ module classified.
 Public/internal visibility assigned.
 Experimental/validated/deprecated status assigned.
 Citations recorded for publishable metrics.
 Validation references recorded.
 Negative results distinguished from dead code.
 New unclassified metric/model modules prohibited.
CLI
 Parser extracted.
 Dispatch extracted.
 Command handlers split by family.
 Console entry point preserved.
 CLI behavior regression-tested.
MLB API connector
 Internal concerns mapped.
 Module split plan approved.
 Client separated from transforms/loading.
 Analytics/replay behavior preserved.
 Connector contract unchanged.
Conform
 Call graph documented.
 Characterization tests added where weak.
 Identity logic reviewed before moves.
 Domain modules extracted incrementally.
 conform.run() compatibility preserved.
 Production/representative row-count parity verified.
Data rights
 Source rights remain fail-closed.
 Derived relation lineage is machine-readable enough for publication checks.
 Public export presets explain why relations are allowed.
 Rights surfaced to public users.
Migrations
 SQL migration approach retained.
 Fresh-install baseline deferred until schema stabilizes.
 Upgrade migration chain preserved.
 Migration CI remains healthy.
Configuration/performance
 Heavy PostgreSQL memory tuning configurable.
 Defaults safe for modest hardware.
 Global-state reduction applied only where useful.
 No unmeasured performance framework adopted.
Logging/operations
 Structured logging plan exists.
 Ingestion logs include source/run/stage/error context.
 Human-readable CLI output preserved.
 JSON log mode considered.
Testing/research integrity
 Real PostgreSQL integration tests preserved.
 Grain invariants tested.
 Identity invariants tested.
 Point-in-time leakage invariants tested.
 Replay/idempotency tested.
 Rights boundaries tested.
 External tie-outs retained/expanded.
 "Validated" never means only "unit tests pass."
CI/security
 Existing security workflows remain useful and non-duplicative.
 Blocking versus advisory checks documented.
 Actions remain pinned where required.
 No workflow added without clear value.
User experience
 Dataset consumer path takes under 10 minutes.
 Researcher/modeler path is documented separately.
 Full operator/contributor path is documented separately.
 Public docs do not require reading internal architecture first.
Final architecture quality test
 A new contributor can explain the system accurately in under two minutes.
 A new researcher can use public data without running PostgreSQL.
 A model can be evaluated chronologically without custom split code.
 A published metric can be traced to formula, source, implementation and test.
 A published dataset can be traced to code commit, source set, schema and verification.
