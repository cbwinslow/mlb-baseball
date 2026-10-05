Yes. The earlier review established the architecture and identified the major problems; what was missing was a single **execution contract** that says what to fix, in what order, what “good” looks like, and when we are allowed to move to the next phase.

I would use the following as the project's convergence blueprint.

# MLB Baseball — Project North Star and Convergence Blueprint

## 1. Project North Star

`cbwinslow/mlb-baseball` should become a **trustworthy, reproducible baseball research and forecasting platform** that allows a researcher, developer, or AI agent to go from raw public baseball/market data to validated statistics, point-in-time features, calibrated predictions, market comparisons, and publishable research without having to understand or manually repair the internal plumbing.

The defining workflow is:

```text
SOURCE DATA
    ↓
RAW EVIDENCE
    ↓
CANONICAL BASEBALL FACTS
    ↓
VALIDATED STATISTICS
    ↓
POINT-IN-TIME FEATURES
    ↓
DECLARED PREDICTION TARGET
    ↓
MODEL / SIMULATION
    ↓
CALIBRATED PROBABILITY
    ↓
TIMESTAMP-MATCHED MARKET QUOTE
    ↓
EDGE / EV / ARBITRAGE RESEARCH
    ↓
REPRODUCIBLE PUBLISHED RESULT
```

The system succeeds when a user can ask a research question such as:

> What is the probability that a particular player goes exactly 3-for-3 in his next game, using only information available before the prediction timestamp?

or:

> What is the probability the home team wins tonight, and how does that compare with the executable Kalshi and Polymarket prices available at the same time?

and the platform can produce the answer while preserving:

- exactly which source data was used;
- exactly what was knowable at prediction time;
- exactly which formulas and feature versions were used;
- exactly which model artifact generated the probability;
- exactly which market quote was compared;
- exactly how the model was evaluated;
- enough provenance to reproduce the result later.

That traceability is the primary competitive advantage of the project.

---

# 2. The fundamental engineering laws

These should become non-negotiable project rules.

## Law 1 — Raw preserves evidence

`raw` is not where we “fix” baseball.

Raw stores what providers gave us with enough metadata to prove where it came from.

Never manually edit raw data to make downstream tests pass.

When a source is incorrect, retain the incorrect source record and correct its interpretation downstream.

---

## Law 2 — Core establishes identity and canonical facts

`core` answers:

> What real-world baseball entity or event is this?

Examples:

- player;
- team;
- franchise;
- venue;
- game;
- event;
- plate appearance;
- pitch;
- market contract.

Core IDs must become permanent.

Once:

```text
core.game.id = 12345
```

means a particular game, that ID must never silently refer to another game after tomorrow's rebuild.

---

## Law 3 — Gold contains deterministic baseball knowledge

Gold answers questions that can be deterministically recalculated from canonical facts.

Examples:

- batting lines;
- pitching lines;
- rolling rates;
- wOBA;
- FIP;
- RE24;
- park factors;
- platoon splits;
- pitch movement summaries.

A gold relation has:

- one grain;
- one owner;
- one writer;
- one formula/version;
- explicit source dependencies;
- explicit null semantics;
- validation.

No permanent multi-writer relations.

---

## Law 4 — Point-in-time features answer “what was knowable then?”

Pregame modeling data must not simply be historically correct.

It must be historically **available**.

The feature system must answer:

```text
What was known at 6:00 PM before a 7:05 PM game?
```

not:

```text
What do we now know about that game?
```

This is why the DuckDB `feat.*` layer should remain a first-class boundary.

---

## Law 5 — Targets define the prediction problem

Models do not get to invent their own labels.

Targets are versioned contracts.

Examples:

```text
game.home_win:v1
game.total_runs:v1
player.hits_gte_2:v1
player.exact_3_for_3:v1
pitcher.strikeouts_gte_7:v1
```

Each target defines:

- grain;
- eligible population;
- prediction cutoff;
- horizon;
- exact label calculation;
- void/censoring behavior;
- evaluation metrics;
- compatible market settlement semantics.

---

## Law 6 — Models estimate uncertainty; they do not redefine facts

Deterministic aggregations belong in SQL/SQLMesh.

Sequential fitting, optimization, Bayesian inference, machine learning, and simulation belong in Python.

Do not implement a deterministic baseball statistic in Python merely because Python can do it.

Do not force Markov simulation or gradient boosting into SQL merely because SQLMesh exists.

---

## Law 7 — A number is not trusted because code produced it

Every calculated asset should have an explicit trust state.

At minimum distinguish:

```text
experimental
implemented
published/citable
validated
disabled
```

A metric producing plausible-looking values is not evidence of correctness.

---

## Law 8 — Every production relation has one canonical writer

The project should eventually be able to answer automatically:

```text
Who owns gold.team_woba?
```

with exactly one answer.

For example:

```text
SQLMesh model transforms/models/team_woba.sql
```

There must not also be an active Python implementation and a second SQL implementation modifying the same relation.

---

## Law 9 — Build first, validate second, publish third

Never destroy the currently valid state before the replacement is known to be valid.

Preferred pattern:

```text
BUILD STAGING
      ↓
VALIDATE
      ↓
ATOMIC PUBLISH
      ↓
ANALYZE
```

Avoid:

```text
TRUNCATE PRODUCTION
      ↓
TRY TO REBUILD IT
```

---

## Law 10 — Failure must be actionable

Every important failure should answer four questions:

```text
WHAT failed?
WHY is it considered wrong?
WHERE should I look?
WHAT should I do next?
```

That is the purpose of `mlb doctor`.

---

# 3. Project-level completion criteria

The platform should not be considered “finished enough to build aggressively on top of” until these conditions hold.

## Operational completion

A normal healthy production installation must produce:

```text
mlb doctor
```

with:

```text
0 required ERROR conditions
```

Optional functionality may report:

```text
INFO
SKIPPED
NOT_CONFIGURED
EXPERIMENTAL
```

without making the installation appear broken.

---

## Database completion

The following must be true:

- core entity IDs remain stable across repeated conform runs;
- incremental conform and full conform produce equivalent canonical data;
- historical source corrections trigger the appropriate season rebuild;
- no manual raw-table corrections are required;
- every important core table has a documented natural/business key;
- every important gold relation has a documented grain;
- duplicate business keys are zero unless explicitly documented;
- required FK/orphan checks pass;
- one writer owns each derived relation;
- long rebuilds cannot leave readers seeing partially emptied datasets.

---

## Research completion

A declared research feature set must pass:

```text
backbone tie-out
feature coverage
null policy
point-in-time validation
future leakage checks
target eligibility
artifact integrity
```

before it may feed a production model.

---

## Model completion

A model promoted for research use must have:

- immutable artifact;
- target version;
- feature-set version;
- chronological training/evaluation;
- baseline comparison;
- calibration evaluation;
- no future leakage;
- model card;
- reproducible run ID.

A more complex model is not promoted merely because it exists.

---

## Market completion

A market comparison must identify:

- provider;
- exact contract;
- canonical target;
- exact settlement semantics;
- quote timestamp;
- bid/ask where available;
- executable side/price;
- fees where relevant;
- liquidity/size when available.

Research must distinguish:

```text
model disagreement
positive expected value
cross-market discrepancy
true arbitrage
```

These terms must not be used interchangeably.

---

## Publishing completion

Any published probability/research result should be traceable to a research run containing at least:

```text
git commit
data snapshot/version
source hashes
target version
feature-set version
feature artifact hash
model version
model artifact hash
training cutoff
evaluation period
market quote timestamp
generated_at
```

---

# 4. Phase 0 — Stop expanding until the foundation converges

## North Star

No additional architectural surface area is added while existing correctness problems remain unresolved.

## Instructions

Temporarily freeze:

- new speculative metrics;
- new composite “Engine” statistics;
- additional neural architectures;
- new serving layers;
- new databases;
- ClickHouse migration;
- Airflow/Dagster/Kubernetes orchestration;
- broad website development.

Allowed work:

- correctness fixes;
- validation;
- data contracts;
- stable IDs;
- pipeline recovery;
- SQL ownership;
- market normalization;
- feature readiness;
- baseline modeling necessary to verify the platform.

## Exit criterion

The current pipeline recovery and stable-ID program are complete.

---

# 5. Phase 1 — Finish pipeline recovery

This should happen before anything else.

## North Star

A successful nightly run leaves the research database in an explainably healthy state.

`mlb doctor` should distinguish an actual broken system from optional or unconfigured functionality.

---

## 5.1 Catcher framing

### Current problem

The in-season CSAE/framing calculation is not trustworthy.

The implementation interpreted Retrosheet play-description text as pitch information and used uncited flat constants.

The attempted Statcast reconstruction also failed to reproduce Baseball Savant closely enough to call it equivalent.

### Fix

Immediately withhold the current in-season fields from model-ready feature sets.

Do not widen health-check bounds.

Keep the prior-season Savant-derived framing value because it is source-native.

Mark the project-derived in-season metric something equivalent to:

```text
status: disabled
reason: invalid source interpretation / failed external tie-out
```

If `disabled` is not yet a catalog state, add a suitable equivalent deliberately rather than pretending the metric remains merely “implemented-untested.”

### Rebuild path

A future framing metric must be reconstructed from real pitch-level observations:

```text
called_strike
ball
pitch location
count
batter handedness
pitcher handedness
catcher
umpire if available
park
```

and validated against an independent published framing dataset.

### Completion criteria

The feature is not production eligible until:

- pitch-level inputs are correct;
- no play-text proxy remains;
- PIT semantics are documented;
- an independent tie-out exists;
- acceptable tolerance is established;
- its SQL/model has tests;
- `mlb readiness` admits it.

---

## 5.2 MLB API ingestion-item ledger

### Current problem

Run-level ingestion tracking exists, but the item-level analytics ledger is incomplete.

### Required behavior

Every durable analytics item should terminate in one of:

```text
loaded
unavailable
failed
```

with enough information to diagnose it.

Recommended fields/semantics:

```text
source
item_key
endpoint
season
status
attempt_count
first_seen_at
last_attempt_at
loaded_at
artifact_path
artifact_sha256
http/status information
error_class
error_message
```

### Fix procedure

Trace all MLB analytics code paths that:

1. download an item;
2. archive it;
3. parse it;
4. load it;
5. detect source unavailability;
6. exhaust retries.

Ensure each terminal path updates `meta.ingestion_item`.

Then backfill the ledger from already archived/raw artifacts where possible rather than redownloading everything.

### Completion criteria

For every expected analytics item in a tested season:

```text
expected =
loaded + confirmed_unavailable + failed
```

No item silently disappears.

A rerun skips durable successes.

A failed item can be identified by one query.

---

## 5.3 Stale DuckDB feature artifact

### Current problem

`mlb doctor` can crash or emit a low-level DuckDB binder error when the local feature artifact was created with an older schema.

### Fix

Each DuckDB feature artifact should contain a build manifest such as:

```text
feature_schema_version
feature_set_version
git_commit
built_at
source_database_snapshot
```

`feat.health_check()` compares the expected schema/version against the artifact.

Instead of:

```text
Binder Error: home_pa_30d does not exist
```

return:

```text
STALE FEATURE ARTIFACT

Artifact schema: v17
Required schema: v18

Run:
mlb build
```

### Completion criteria

An old artifact never generates an opaque SQL/DuckDB exception from `doctor`.

---

## 5.4 Prediction-count checks

### Current problem

Prediction health checks counted rows, while `gold.prediction` intentionally stores multiple temporal predictions for the same game.

### Fix

Define the grain that the check actually wants.

If checking game coverage:

```sql
COUNT(DISTINCT game)
```

or canonical game-instance identity.

If checking latest available prediction:

select one prediction per:

```text
game
model_version
cutoff
```

using the latest valid prediction before the cutoff.

Then separately investigate the remaining real Polymarket game-coverage discrepancy instead of hiding it.

### Completion criteria

Health checks test declared prediction coverage rather than incidental physical row count.

---

## 5.5 Backup health

### Current problem

The project-level backup check thinks backups do not exist because backups are performed by validated host infrastructure instead of `mlb backup`.

### Fix

Do not hard-code knowledge of one backup implementation into doctor.

Have the host backup process publish a small machine-readable status artifact, for example:

```json
{
  "database": "mlb",
  "last_success": "...",
  "dump": "...",
  "sha256_verified": true,
  "restore_tested_at": "...",
  "format": "pg_dump custom"
}
```

Configure the path in normal configuration.

Doctor reads the status contract.

### Completion criteria

Doctor reports healthy when a verified external backup satisfies the backup policy.

A restore test remains part of disaster-recovery validation.

---

## 5.6 Metric catalog empty state

### Fix

The catalog is code metadata and should stay synchronized with the checkout.

`mlb catalog build` should occur automatically in an appropriate maintenance stage after migrations/code deployment rather than depend on a human remembering it.

Doctor should compare:

```text
catalog rows
catalog YAML count
catalog git commit
```

if practical.

### Completion criteria

A normal nightly/deployment cannot leave `meta.metric` empty while metric manifests exist.

---

## 5.7 Never-vacuumed relations

Perform the required one-time `VACUUM (ANALYZE)` on affected relations after confirming they are not actively undergoing a large load.

Then investigate why autovacuum did not reach them.

Tune autovacuum per high-churn relation if evidence warrants it.

Do not globally disable or aggressively retune autovacuum based on one table.

### Completion criteria

No significant table has accumulating dead tuples with no visible vacuum path.

---

## 5.8 Optional model artifacts

A missing experimental GBM/stack/neural artifact should not make the database installation unhealthy.

Doctor semantics should be:

```text
required configured production model missing
→ ERROR

optional model never trained
→ NOT_CONFIGURED

candidate model unavailable
→ INFO/WARN

champion artifact referenced in metadata but missing
→ ERROR
```

---

## Phase 1 exit gate

Do not leave Phase 1 until:

```text
mlb nightly
```

completes successfully and:

```text
mlb doctor
```

reports zero required operational errors.

Any remaining warnings have written explanations and do not represent silent correctness failures.

---

# 6. Phase 2 — Stable identities and incremental conform

## North Star

Canonical identity survives forever, and only changed data is rebuilt.

This is the most important structural database change.

---

## 6.1 Stable identity

Convert:

```text
core.team
core.player
core.venue
core.game
```

from truncate/recreate semantics to persistent entities.

Use real natural/source keys and upserts.

Never automatically merge two existing player entities merely because a later source creates an ambiguous mapping.

Identity conflicts should be explicit.

---

## 6.2 Fingerprinting

Do not use only:

```text
row_count + max(_loaded_at)
```

as the change detector.

Use a build fingerprint that includes enough information to detect meaningful changes.

Conceptually:

```text
source artifact/content fingerprint
+ transform code version
+ schema version
+ relevant reference-data version
```

If immutable downloaded source artifacts already have SHA256 values, use those rather than hashing massive tables repeatedly.

---

## 6.3 Rebuild unit

Prefer season/partition-level replacement for historical facts.

A corrected 1974 source archive should not require rebuilding 1910–2026.

Changed input:

```text
1974
```

should dirty:

```text
1974
```

and any known downstream state dependent on later history.

---

## 6.4 Publish atomically

Build changed data into staging.

Validate.

Perform a short transactional publication.

Use lock timeouts.

Readers should continue to see the last valid dataset while the replacement builds.

---

## 6.5 Full-build oracle

Retain:

```bash
mlb conform --full
```

as the correctness oracle.

Create an automated test where:

```text
incremental build
```

and:

```text
fresh full build
```

produce identical canonical contents aside from intentionally non-semantic metadata such as timestamps.

Compare **every relevant non-key column**, not merely row counts.

---

## 6.6 Stable-ID completion criteria

After two identical conform runs:

```text
core.team IDs unchanged
core.player IDs unchanged
core.venue IDs unchanged
core.game IDs unchanged
```

After modifying one historical source partition:

```text
only affected partitions + declared downstream dependents rebuild
```

After incremental and full builds:

```text
0 unexplained differences
```

---

# 7. Phase 3 — Strengthen the canonical baseball event model

## North Star

Downstream calculations should not repeatedly reinterpret provider-specific event semantics.

The database should provide one canonical representation of game events.

---

## Problem

Several recent defects were caused by separate downstream SQL implementations independently understanding fields such as:

```text
bat_event_fl
resp_bat_id
resp_pit_id
pitch_seq_tx
outs_ct
start_bases_cd
runner flags
event_cd
```

This includes:

- pitch sequence double counting;
- responsible batter substitution problems;
- obstruction runs;
- baserunning semantics;
- catcher framing;
- PA identification.

These are signs that important baseball semantics remain trapped in raw.

---

## Proposed direction

Evaluate creating a typed canonical:

```text
core.event
```

while retaining:

```text
core.play / plate appearance
core.pitch
```

This would give:

```text
core.game
  ├── core.event
  ├── core.play
  └── core.pitch
```

`core.event` could contain canonical typed fields such as:

```text
game_id
event_index
batter_id
responsible_batter_id
pitcher_id
responsible_pitcher_id

event_type
is_batter_event
is_at_bat
is_sac_fly
is_sac_hit

outs_before
bases_before
runs_scored

pitch_sequence
runner-event flags
```

This should be its own OpenSpec design/research change, not an opportunistic refactor.

---

## Completion criteria

A downstream deterministic statistic should no longer need to know obscure Retrosheet parsing behavior unless the provider-specific behavior itself is the subject of the calculation.

---

# 8. Phase 4 — Make gold canonical and SQLMesh-owned

## North Star

Gold is a collection of deterministic, documented, validated, single-writer baseball models.

---

## 8.1 Freeze `gold.game_feature`

Do not continue expanding the giant wide feature table.

Treat it as compatibility/internal infrastructure.

New model-ready feature families should flow into the point-in-time feature-store architecture instead.

---

## 8.2 SQLMesh ownership

Use SQLMesh for deterministic, set-based core→gold transformations.

Do not move:

```text
identity reconciliation
network ingestion
Elo sequential updates
GBM training
Markov simulation
Monte Carlo
Bayesian fitting
```

into SQLMesh.

---

## 8.3 Promotion process

For every migrated relation:

```text
current writer
       ↓
candidate SQLMesh model
       ↓
same inputs
       ↓
full-table comparison
       ↓
sample PIT comparison if relevant
       ↓
audits
       ↓
performance measurement
       ↓
promote SQLMesh
       ↓
DELETE old writer
```

Never leave both writers active indefinitely.

---

## 8.4 Recommended first migrations

Start with relatively understood deterministic families.

Suggested order:

1. era-correct wOBA;
2. park factors;
3. straightforward team rates;
4. pitching estimators;
5. pitch movement;
6. platoon splits;
7. remaining deterministic feature families.

Avoid starting with the most complicated or currently questionable metrics.

---

## 8.5 SQLMesh audits

Each promoted model gets applicable blocking audits for:

```text
business-key uniqueness
required-key NULLs
foreign-key/orphan coverage
source coverage
season coverage
value-domain validity
fanout
impossible values
```

Range checks must represent genuine domain knowledge rather than arbitrary “looks plausible” limits.

---

## Phase 4 completion criteria

For every canonical gold relation:

```text
one writer
one documented grain
one defined business key
one lineage path
one build strategy
required audits
known coverage
known null policy
```

CI detects duplicate writer ownership.

---

# 9. Phase 5 — Repair and formalize the metric library

## North Star

The metric catalog becomes a trustworthy registry of baseball/statistical knowledge, not a collection of things an AI once generated.

---

## 9.1 Do not resurrect the deleted Gemini batch

The deletion of approximately 101 fabricated/disconnected metrics was correct.

Do not regenerate them wholesale.

Real concepts preserved in `TRIAGE_BACKLOG.md` may return individually through normal research/admission.

---

## 9.2 Add asset classification

The catalog currently contains fundamentally different things.

Add a concept similar to:

```text
statistic
feature
baseline
model
simulation
diagnostic
market_tool
```

Examples:

```text
wOBA → statistic
rolling K% → feature
Elo → baseline
Monte Carlo season simulation → simulation
drift monitor → diagnostic
```

---

## 9.3 Add use/admission classification

Separate:

```text
documented
```

from:

```text
allowed in production model
```

A useful model might be:

```text
research_only
model_candidate
model_approved
public_stat
disabled
```

or equivalent booleans.

---

## 9.4 Production feature gate

No metric with status equivalent to:

```text
implemented-untested
```

may silently enter an approved production model.

Novel features are permitted, but must explicitly be experimental and pass:

```text
PIT validation
chronological evaluation
ablation
stability analysis
```

before promotion.

---

## 9.5 Fix era-specific wOBA

This should be an early flagship cleanup.

You already ingest FanGraphs Guts constants.

The canonical historical wOBA implementation should resolve the appropriate weight set by season instead of applying one modern constant set across all eras.

All dependent wRC+/rolling calculations should use that owner.

---

## Metric completion criteria

Every published metric has:

```text
name
definition
formula owner
citation
data sources
grain
coverage
implementation
trust status
visibility
known limitations
test/tie-out
```

Every model-used metric additionally has:

```text
point-in-time semantics
admission status
```

---

# 10. Phase 6 — Finish the point-in-time feature platform

## North Star

A model cannot accidentally use information from the future.

---

## Required feature contract

Every feature field/family should know:

```text
source relation
event time
availability time
lookback/window
coverage
null policy
feature version
target compatibility
```

The important time is **availability time**, not merely event time.

Examples where they differ:

- probable starters;
- lineups;
- revised statistics;
- final season WAR;
- weather;
- market quotes;
- source publication delays.

---

## Feature artifact

A built DuckDB artifact should be immutable and content-addressable.

Include:

```text
artifact hash
feature schema version
feature-set version
git commit
source snapshot
built_at
```

---

## Completion criteria

Before a feature set can be used:

```text
mlb readiness
```

must establish:

- all declared columns exist;
- coverage is expected;
- nulls obey policy;
- no PIT leakage;
- source backbone tie-out passes;
- feature artifact integrity passes.

---

# 11. Phase 7 — Create the canonical target registry

## North Star

Every model predicts an explicitly defined event.

---

## Target schema

Each target should contain concepts such as:

```text
name
version
entity grain
prediction cutoff
prediction horizon
label formula
eligible games
void/censoring rules
evaluation metrics
market mapping rules
```

---

## Examples

### Game winner

```text
name: game.home_win
version: v1
grain: game
label: home_score > away_score
cutoff: scheduled first pitch
eligible: MLB regular season
type: binary
```

### Exact player 3-for-3

```text
name: player.exact_3_for_3
version: v1
grain: player-game

label:
hits = 3
AND official_at_bats = 3

cutoff:
declared prediction timestamp

void/censoring:
must be specified explicitly
```

This is different from:

```text
hits >= 3
```

and from:

```text
3 hits in 4 AB
```

The distinction must live in the target definition, not in prose surrounding a model.

---

## Completion criteria

Two different models evaluated on the same target are guaranteed to be predicting the same thing.

---

# 12. Phase 8 — Build the model ladder

## North Star

Complexity is earned by measurable improvement over simpler baselines.

---

## Recommended progression

For game winners:

```text
naive historical baseline
↓
Log5
↓
Elo
↓
regularized logistic regression
↓
CatBoost / XGBoost
↓
run-distribution model
↓
player-aware simulation / Markov
↓
ensembles only if justified
```

Do not prioritize neural networks yet.

---

## Evaluation rules

Never random-split time-series baseball forecasting data.

Use:

```text
train on past
validate on later period
test on later untouched period
```

Report at minimum:

```text
log loss
Brier score
calibration
calibration slope/intercept
season-by-season results
```

A model that is poorly calibrated does not get promoted simply because its accuracy is higher.

---

## Champion promotion

A model is `champion` only when its promotion contract passes.

Example:

```text
artifact exists
PIT readiness passed
holdout completed
beats required baseline by practical threshold
calibration acceptable
artifact immutable
model card written
```

Otherwise:

```text
candidate
```

is the honest result.

---

# 13. Phase 9 — Build the player/event simulation engine

## North Star

Player props and parlays come from coherent simulated baseball worlds rather than disconnected probability calculators.

---

## Player model direction

For an event like exact 3-for-3, model underlying mechanisms:

```text
P(player starts)
P(lineup position)
P(number of PA)
P(official AB | PA)
P(PA outcome | matchup/context)
```

Context may include:

```text
batter skill
pitcher skill
handedness
arsenal
bullpen
park
weather
defense
umpire
lineup
rest/workload
```

Simulation then naturally estimates:

```text
P(H = 3 AND AB = 3)
```

and also:

```text
P(H >= 2)
P(HR >= 1)
P(team wins)
P(player HR AND team wins)
```

from the same simulated games.

---

## Joint parlay principle

Do not estimate:

```text
P(A AND B)
```

by blindly multiplying independently trained probabilities.

Use:

```text
number of simulated worlds satisfying A and B
-----------------------------------------------
total simulated worlds
```

when both outcomes can be represented by the same simulation.

---

# 14. Phase 10 — Normalize market history properly

## North Star

Market comparison uses the exact executable market state that existed when the model prediction was made.

---

## Separate market concepts

Do not treat one mutable row as “the market.”

Create conceptual entities equivalent to:

### Market contract

```text
provider
provider_market_id
event
question
outcome
side
line
open time
close time
resolution semantics
```

### Market observation

```text
contract
observed_at
retrieved_at

bid
bid_size
ask
ask_size
last
volume
open_interest
liquidity
status
```

### Settlement

```text
contract
result
settlement value
settled_at
resolution source
void reason
```

---

## Target mapping

Each provider contract maps to a canonical target.

Example:

```text
provider contract ABC
→ game.home_win:v1
```

or:

```text
provider contract XYZ
→ game.total_runs_gt:8.5:v1
```

This mapping is where settlement semantics must be verified.

---

## Market research rules

Always distinguish:

```text
model probability
market mid/implied probability
executable buy price
fees
slippage
liquidity
```

If:

```text
model = 0.58
market displayed = 0.54
ask = 0.56
```

the relevant comparison for a buy is closer to `.56`, not `.54`.

---

## Historical cutoffs

The market system must honestly support:

```text
open
24h
6h
1h
close
```

by selecting the actual quote that existed at or before each cutoff.

No cutoff may silently reuse closing price.

---

# 15. Phase 11 — Research-run reproducibility

## North Star

A published claim can be reconstructed months later.

---

## Research-run identity

Every important experiment/published result should eventually point to:

```text
research_run_id

git_commit
schema_version
source snapshot hashes
target version
feature set version
feature artifact hash
model version
model artifact hash
hyperparameters
training period
validation period
test period
prediction cutoff
market observation cutoff
generated_at
```

---

## Model artifacts

Never identify the only copy of an important model by:

```text
models/gbm-v2.json
```

alone.

Use immutable artifact directories:

```text
models/artifacts/<content-or-run-id>/
    model...
    metadata.json
```

Human aliases such as:

```text
champion
candidate
```

may reference immutable artifacts.

All model writes should use temp-file + atomic replacement.

---

# 16. Phase 12 — Public research product

## North Star

A researcher who does not want to operate your producer infrastructure can still use the output easily.

---

## Producer product

The full producer may require:

```text
PostgreSQL
Retrosheet
MLB API
Statcast
SQLMesh
market connectors
large historical build
```

That is acceptable.

---

## Consumer product

The consumer should ideally require:

```bash
pip install mlb-research
```

and operate primarily through:

```text
Parquet
DuckDB
Python
```

A researcher should not need PostgreSQL or Chadwick system binaries merely to query the published dataset.

---

## Bootstrap profiles

Eventually add supported profiles such as:

```text
research-core
research-full
statcast
markets
modeling
everything
```

A researcher interested in historical batting should not have to download every pitch and every market quote.

Do not add these commands until they are backed by clearly defined dependency groups.

---

# 17. Annual source rollover

## North Star

Current-season provisional data transitions into finalized historical data through an explicit reconciliation rather than silently changing source ownership.

---

## Workflow

When Retrosheet releases a completed season:

```text
MLB-current-season version
          ↓
       compare
          ↑
Retrosheet-finalized version
```

Compare important grains and aggregates.

Classify differences:

```text
MATCH
EXPLAINED SOURCE DIFFERENCE
SOURCE CORRECTION
UNRESOLVED
```

Only after the gate passes does historical ownership transition.

---

## Completion criteria

The source transition for a season is an auditable event.

---

# 18. Rebuild `mlb doctor` as a diagnostic registry

## North Star

`mlb doctor` becomes the project's operational expert.

---

## Check object

Every check should have stable structured metadata:

```text
id
scope
component
severity
status
summary
details
dependencies
remediation
documentation
duration
```

---

## Desired statuses

Use something richer than pass/fail:

```text
PASS
WARN
ERROR
INFO
SKIPPED
NOT_CONFIGURED
EXPERIMENTAL
```

---

## Registry approach

Subsystems register checks.

Doctor discovers the registry.

Do not manually import and invoke dozens of modules in `doctor.py`.

---

## Scopes

Recommended UX:

```text
mlb doctor
```

Operational installation health.

```text
mlb audit
```

Database/data-contract correctness.

```text
mlb readiness
```

Feature/target/model admission.

Optionally:

```text
mlb doctor --deep
```

summarizes all three.

---

## JSON

Every important diagnostic command should support machine-readable output.

For example:

```bash
mlb doctor --json
mlb audit --json
mlb readiness --json
mlb runs --json
```

This is essential for future AI automation.

---

# 19. End-to-end reference database acceptance test

## North Star

CI proves that the machine still works as a machine, not only as a set of modules.

Create one intentionally tiny fixture containing enough weirdness to exercise the architecture:

```text
multiple seasons
doubleheader
postseason
trade
mid-PA substitution
baserunning event
starter change
one missing source field
one market
one market price change
```

Run:

```text
migrate
↓
load fixtures
↓
conform
↓
gold
↓
feature build
↓
readiness
↓
baseline model
↓
export
```

Compare canonical outputs against versioned expected results.

## Completion criterion

CI can prove:

> A clean environment can produce a coherent, research-ready baseball database from source fixtures.

---

# 20. CI quality gates

The following should eventually be hard merge gates for relevant changes.

## General code

```text
ruff
mypy
tests
secret scanning
migration tests
docs build
```

Already largely present.

## Database

Add/strengthen:

```text
single-writer ownership lint
business-grain uniqueness
incremental/full equivalence
schema contracts
```

## Metrics

```text
catalog completeness
validated test reference
disabled metric cannot be production feature
```

## SQLMesh

Once production ownership begins:

```text
SQLMesh model tests
SQLMesh blocking audits
plan validation
```

## Feature store

```text
PIT leakage tests
artifact schema/version checks
feature readiness
```

## Models

```text
artifact-path safety
atomic writes
target compatibility
no production promotion without evaluation evidence
```

---

# 21. Definition of Done for every future feature

Every non-trivial new feature should answer this template before implementation.

## Problem

What exact research capability is missing?

## User

Who needs it?

```text
database researcher
model developer
market researcher
subscriber
AI agent
```

## Grain

What does one row/result mean?

## Source

Where does the input come from?

## Identity

How does it map to canonical players/teams/games/contracts?

## Time

When did the event occur?

When did the information become knowable?

## Formula/model

What calculates the result?

Is the implementation deterministic or learned?

## Owner

What single piece of code owns the output?

## Null semantics

What does NULL mean?

Never use zero to mean “unknown.”

## Coverage

What seasons/providers/populations are supported?

## Validation

What independent evidence can verify the output?

## Failure behavior

How will doctor/audit/readiness identify failure?

## Rights

Can the output be redistributed publicly?

## Performance

What expected build/query cost is acceptable?

## Completion

The feature is not done until:

- tests pass;
- contract exists;
- grain enforced;
- ownership declared;
- source lineage declared;
- PIT rule declared where applicable;
- validation passes;
- doctor/audit/readiness knows how to assess it;
- documentation is updated;
- old implementation is removed if this replaced one.

---

# 22. AI skills North Star

## North Star

AI agents operate the platform through the same deterministic interfaces humans use.

The agent should not contain hidden baseball logic.

---

## Skills should teach workflows

Eventually create skills such as:

```text
mlb-diagnose
mlb-add-source
mlb-add-metric
mlb-add-target
mlb-build-feature-set
mlb-run-research
mlb-market-study
mlb-publish-research
```

---

## Example `mlb-diagnose` behavior

Agent:

1. runs `mlb doctor --json`;
2. identifies failed dependency;
3. runs a read-only focused diagnostic;
4. identifies likely root cause;
5. recommends or performs the authorized repair;
6. reruns the failing check;
7. records evidence.

It should not randomly edit SQL until the check turns green.

---

# 23. The concrete implementation order from today's repository

This is the order I recommend following.

## Priority A — finish what is already open

1. Finish `pipeline-recovery`.
2. Complete odds-history capture/backfills and scheduling.
3. Resolve catcher framing by withholding broken current-season outputs.
4. Repair `meta.ingestion_item`.
5. Fix feature-artifact stale-schema diagnostics.
6. Correct prediction coverage checks.
7. Make backup health understand the real host backup.
8. Resolve legitimate domain checks using source/formula evidence.
9. Ensure the catalog rebuilds automatically.
10. Verify several consecutive clean nightly runs.

Do not open a large new architecture project while this remains unfinished.

---

## Priority B — database identity

11. Finish measurement for stable IDs.
12. Correct the fingerprint design.
13. Upsert team/player/venue/game.
14. Make IDs stable.
15. Implement changed-season rebuilds.
16. Implement atomic publication.
17. Prove incremental/full equivalence.
18. Run production-copy comparison.
19. Promote incremental nightly operation.

This is the most important architecture milestone.

---

## Priority C — gold convergence

20. Establish machine-readable writer ownership.
21. Freeze expansion of `gold.game_feature`.
22. Fix canonical era-specific wOBA.
23. Promote first real SQLMesh gold model.
24. Add blocking audits.
25. Delete the old writer.
26. Repeat model-by-model.
27. Remove stale SQLMesh shadow copies or bring them to parity before promotion.

---

## Priority D — canonical event semantics

28. Design the `core.event`/plate-appearance boundary.
29. Solve responsible batter/pitcher semantics centrally.
30. Solve runner/pitch-sequence semantics centrally.
31. Update downstream gold models to consume canonical facts.

Do this deliberately, not as a giant rewrite.

---

## Priority E — research platform

32. Finish target registry.
33. Strengthen feature-set contracts.
34. Produce immutable DuckDB artifacts.
35. Finish baseline Elo/log5 pipeline.
36. Add regularized logistic baseline.
37. Add CatBoost/XGBoost challenger.
38. Implement formal champion promotion.
39. Store complete research-run lineage.

---

## Priority F — market intelligence

40. Normalize market contracts.
41. Normalize quote history.
42. Normalize settlement.
43. Map market contracts to canonical targets.
44. Support real quote cutoffs.
45. Calculate executable edge rather than screen-price difference.
46. Add fees/liquidity/slippage assumptions.
47. Backtest market research chronologically.

---

## Priority G — advanced player/prop modeling

48. Build player/PA target family.
49. Build matchup model.
50. Feed it into a game simulation.
51. Produce joint probabilities from simulations.
52. Validate player props chronologically.
53. Compare them to matching market contracts.

---

## Priority H — productization

54. Harden `mlb-research`.
55. Finish `retrosheetpy` parity/package independence.
56. Publish stable Parquet releases.
57. Make public rights enforcement automatic.
58. Build reproducible research-report publishing.
59. Build subscriber-facing presentation.
60. Build AI skills over the stable CLI.

---

# 24. What “perfect shape” means

The project cannot literally become incapable of bugs. Upstream APIs change, providers correct historical records, and software evolves.

The achievable goal is much better:

> **The system detects when it is wrong, localizes why it is wrong, refuses to make unsupported claims, preserves enough evidence to repair itself, and can rebuild every derived result reproducibly.**

That means the platform is in excellent shape when:

```text
fresh installation
→ understandable

bootstrap
→ resumable

raw
→ preserved

core
→ stable

gold
→ deterministic

features
→ leak-free

models
→ calibrated and reproducible

markets
→ timestamp-correct

doctor
→ actionable

audit
→ trustworthy

research
→ reproducible

publishing
→ source-backed

AI agents
→ safe and deterministic
```

That is the system we should be building.

# 25. Immediate project milestone

I would name the current milestone something like:

**Platform Convergence**

Its completion criteria should be:

- pipeline recovery complete;
- required `mlb doctor` checks green;
- stable IDs implemented;
- full/incremental conform equivalent;
- normal nightly operation incremental and reliable;
- no known invalid metric feeding an approved model;
- writer ownership established;
- feature artifact/version diagnostics reliable;
- backup state verifiable;
- item-level ingestion ledger trustworthy;
- at least one gold model fully promoted to SQLMesh under the new one-writer/audit rules;
- a clean end-to-end fixture build passes in CI.

Only after that milestone should aggressive new modeling and commercial research development resume.

That gives the project a clear finish line instead of an endless series of interesting additions.

I would make this **the controlling execution order**, but I would avoid creating another pile of overlapping documentation. The best implementation is to fold the project-level North Star and milestone gates into `openspec/project.md`, use the existing `TABLE_CONTRACTS.md`, `SQL_OWNERSHIP.md`, `FEATURE_STORE.md`, `RESEARCH.md`, and audit/readiness docs for their respective contracts, and then let individual OpenSpec changes implement each phase. I would create at most one new cross-cutting document—something like `docs/ACCEPTANCE_GATES.md`—only if we find that the completion criteria cannot cleanly live in the existing constitution.

The three highest-value upgrades from here are therefore **stable immutable identity**, **single-writer/validated gold transformations**, and **structured diagnostics that distinguish broken from optional**. After those, the target/market/research-run architecture is what turns the database into the forecasting and commercial research platform you actually want.Yes. The earlier review established the architecture and identified the major problems; what was missing was a single **execution contract** that says what to fix, in what order, what “good” looks like, and when we are allowed to move to the next phase.

I would use the following as the project's convergence blueprint.

# MLB Baseball — Project North Star and Convergence Blueprint

## 1. Project North Star

`cbwinslow/mlb-baseball` should become a **trustworthy, reproducible baseball research and forecasting platform** that allows a researcher, developer, or AI agent to go from raw public baseball/market data to validated statistics, point-in-time features, calibrated predictions, market comparisons, and publishable research without having to understand or manually repair the internal plumbing.

The defining workflow is:

```text
SOURCE DATA
    ↓
RAW EVIDENCE
    ↓
CANONICAL BASEBALL FACTS
    ↓
VALIDATED STATISTICS
    ↓
POINT-IN-TIME FEATURES
    ↓
DECLARED PREDICTION TARGET
    ↓
MODEL / SIMULATION
    ↓
CALIBRATED PROBABILITY
    ↓
TIMESTAMP-MATCHED MARKET QUOTE
    ↓
EDGE / EV / ARBITRAGE RESEARCH
    ↓
REPRODUCIBLE PUBLISHED RESULT
```

The system succeeds when a user can ask a research question such as:

> What is the probability that a particular player goes exactly 3-for-3 in his next game, using only information available before the prediction timestamp?

or:

> What is the probability the home team wins tonight, and how does that compare with the executable Kalshi and Polymarket prices available at the same time?

and the platform can produce the answer while preserving:

- exactly which source data was used;
- exactly what was knowable at prediction time;
- exactly which formulas and feature versions were used;
- exactly which model artifact generated the probability;
- exactly which market quote was compared;
- exactly how the model was evaluated;
- enough provenance to reproduce the result later.

That traceability is the primary competitive advantage of the project.

---

# 2. The fundamental engineering laws

These should become non-negotiable project rules.

## Law 1 — Raw preserves evidence

`raw` is not where we “fix” baseball.

Raw stores what providers gave us with enough metadata to prove where it came from.

Never manually edit raw data to make downstream tests pass.

When a source is incorrect, retain the incorrect source record and correct its interpretation downstream.

---

## Law 2 — Core establishes identity and canonical facts

`core` answers:

> What real-world baseball entity or event is this?

Examples:

- player;
- team;
- franchise;
- venue;
- game;
- event;
- plate appearance;
- pitch;
- market contract.

Core IDs must become permanent.

Once:

```text
core.game.id = 12345
```

means a particular game, that ID must never silently refer to another game after tomorrow's rebuild.

---

## Law 3 — Gold contains deterministic baseball knowledge

Gold answers questions that can be deterministically recalculated from canonical facts.

Examples:

- batting lines;
- pitching lines;
- rolling rates;
- wOBA;
- FIP;
- RE24;
- park factors;
- platoon splits;
- pitch movement summaries.

A gold relation has:

- one grain;
- one owner;
- one writer;
- one formula/version;
- explicit source dependencies;
- explicit null semantics;
- validation.

No permanent multi-writer relations.

---

## Law 4 — Point-in-time features answer “what was knowable then?”

Pregame modeling data must not simply be historically correct.

It must be historically **available**.

The feature system must answer:

```text
What was known at 6:00 PM before a 7:05 PM game?
```

not:

```text
What do we now know about that game?
```

This is why the DuckDB `feat.*` layer should remain a first-class boundary.

---

## Law 5 — Targets define the prediction problem

Models do not get to invent their own labels.

Targets are versioned contracts.

Examples:

```text
game.home_win:v1
game.total_runs:v1
player.hits_gte_2:v1
player.exact_3_for_3:v1
pitcher.strikeouts_gte_7:v1
```

Each target defines:

- grain;
- eligible population;
- prediction cutoff;
- horizon;
- exact label calculation;
- void/censoring behavior;
- evaluation metrics;
- compatible market settlement semantics.

---

## Law 6 — Models estimate uncertainty; they do not redefine facts

Deterministic aggregations belong in SQL/SQLMesh.

Sequential fitting, optimization, Bayesian inference, machine learning, and simulation belong in Python.

Do not implement a deterministic baseball statistic in Python merely because Python can do it.

Do not force Markov simulation or gradient boosting into SQL merely because SQLMesh exists.

---

## Law 7 — A number is not trusted because code produced it

Every calculated asset should have an explicit trust state.

At minimum distinguish:

```text
experimental
implemented
published/citable
validated
disabled
```

A metric producing plausible-looking values is not evidence of correctness.

---

## Law 8 — Every production relation has one canonical writer

The project should eventually be able to answer automatically:

```text
Who owns gold.team_woba?
```

with exactly one answer.

For example:

```text
SQLMesh model transforms/models/team_woba.sql
```

There must not also be an active Python implementation and a second SQL implementation modifying the same relation.

---

## Law 9 — Build first, validate second, publish third

Never destroy the currently valid state before the replacement is known to be valid.

Preferred pattern:

```text
BUILD STAGING
      ↓
VALIDATE
      ↓
ATOMIC PUBLISH
      ↓
ANALYZE
```

Avoid:

```text
TRUNCATE PRODUCTION
      ↓
TRY TO REBUILD IT
```

---

## Law 10 — Failure must be actionable

Every important failure should answer four questions:

```text
WHAT failed?
WHY is it considered wrong?
WHERE should I look?
WHAT should I do next?
```

That is the purpose of `mlb doctor`.

---

# 3. Project-level completion criteria

The platform should not be considered “finished enough to build aggressively on top of” until these conditions hold.

## Operational completion

A normal healthy production installation must produce:

```text
mlb doctor
```

with:

```text
0 required ERROR conditions
```

Optional functionality may report:

```text
INFO
SKIPPED
NOT_CONFIGURED
EXPERIMENTAL
```

without making the installation appear broken.

---

## Database completion

The following must be true:

- core entity IDs remain stable across repeated conform runs;
- incremental conform and full conform produce equivalent canonical data;
- historical source corrections trigger the appropriate season rebuild;
- no manual raw-table corrections are required;
- every important core table has a documented natural/business key;
- every important gold relation has a documented grain;
- duplicate business keys are zero unless explicitly documented;
- required FK/orphan checks pass;
- one writer owns each derived relation;
- long rebuilds cannot leave readers seeing partially emptied datasets.

---

## Research completion

A declared research feature set must pass:

```text
backbone tie-out
feature coverage
null policy
point-in-time validation
future leakage checks
target eligibility
artifact integrity
```

before it may feed a production model.

---

## Model completion

A model promoted for research use must have:

- immutable artifact;
- target version;
- feature-set version;
- chronological training/evaluation;
- baseline comparison;
- calibration evaluation;
- no future leakage;
- model card;
- reproducible run ID.

A more complex model is not promoted merely because it exists.

---

## Market completion

A market comparison must identify:

- provider;
- exact contract;
- canonical target;
- exact settlement semantics;
- quote timestamp;
- bid/ask where available;
- executable side/price;
- fees where relevant;
- liquidity/size when available.

Research must distinguish:

```text
model disagreement
positive expected value
cross-market discrepancy
true arbitrage
```

These terms must not be used interchangeably.

---

## Publishing completion

Any published probability/research result should be traceable to a research run containing at least:

```text
git commit
data snapshot/version
source hashes
target version
feature-set version
feature artifact hash
model version
model artifact hash
training cutoff
evaluation period
market quote timestamp
generated_at
```

---

# 4. Phase 0 — Stop expanding until the foundation converges

## North Star

No additional architectural surface area is added while existing correctness problems remain unresolved.

## Instructions

Temporarily freeze:

- new speculative metrics;
- new composite “Engine” statistics;
- additional neural architectures;
- new serving layers;
- new databases;
- ClickHouse migration;
- Airflow/Dagster/Kubernetes orchestration;
- broad website development.

Allowed work:

- correctness fixes;
- validation;
- data contracts;
- stable IDs;
- pipeline recovery;
- SQL ownership;
- market normalization;
- feature readiness;
- baseline modeling necessary to verify the platform.

## Exit criterion

The current pipeline recovery and stable-ID program are complete.

---

# 5. Phase 1 — Finish pipeline recovery

This should happen before anything else.

## North Star

A successful nightly run leaves the research database in an explainably healthy state.

`mlb doctor` should distinguish an actual broken system from optional or unconfigured functionality.

---

## 5.1 Catcher framing

### Current problem

The in-season CSAE/framing calculation is not trustworthy.

The implementation interpreted Retrosheet play-description text as pitch information and used uncited flat constants.

The attempted Statcast reconstruction also failed to reproduce Baseball Savant closely enough to call it equivalent.

### Fix

Immediately withhold the current in-season fields from model-ready feature sets.

Do not widen health-check bounds.

Keep the prior-season Savant-derived framing value because it is source-native.

Mark the project-derived in-season metric something equivalent to:

```text
status: disabled
reason: invalid source interpretation / failed external tie-out
```

If `disabled` is not yet a catalog state, add a suitable equivalent deliberately rather than pretending the metric remains merely “implemented-untested.”

### Rebuild path

A future framing metric must be reconstructed from real pitch-level observations:

```text
called_strike
ball
pitch location
count
batter handedness
pitcher handedness
catcher
umpire if available
park
```

and validated against an independent published framing dataset.

### Completion criteria

The feature is not production eligible until:

- pitch-level inputs are correct;
- no play-text proxy remains;
- PIT semantics are documented;
- an independent tie-out exists;
- acceptable tolerance is established;
- its SQL/model has tests;
- `mlb readiness` admits it.

---

## 5.2 MLB API ingestion-item ledger

### Current problem

Run-level ingestion tracking exists, but the item-level analytics ledger is incomplete.

### Required behavior

Every durable analytics item should terminate in one of:

```text
loaded
unavailable
failed
```

with enough information to diagnose it.

Recommended fields/semantics:

```text
source
item_key
endpoint
season
status
attempt_count
first_seen_at
last_attempt_at
loaded_at
artifact_path
artifact_sha256
http/status information
error_class
error_message
```

### Fix procedure

Trace all MLB analytics code paths that:

1. download an item;
2. archive it;
3. parse it;
4. load it;
5. detect source unavailability;
6. exhaust retries.

Ensure each terminal path updates `meta.ingestion_item`.

Then backfill the ledger from already archived/raw artifacts where possible rather than redownloading everything.

### Completion criteria

For every expected analytics item in a tested season:

```text
expected =
loaded + confirmed_unavailable + failed
```

No item silently disappears.

A rerun skips durable successes.

A failed item can be identified by one query.

---

## 5.3 Stale DuckDB feature artifact

### Current problem

`mlb doctor` can crash or emit a low-level DuckDB binder error when the local feature artifact was created with an older schema.

### Fix

Each DuckDB feature artifact should contain a build manifest such as:

```text
feature_schema_version
feature_set_version
git_commit
built_at
source_database_snapshot
```

`feat.health_check()` compares the expected schema/version against the artifact.

Instead of:

```text
Binder Error: home_pa_30d does not exist
```

return:

```text
STALE FEATURE ARTIFACT

Artifact schema: v17
Required schema: v18

Run:
mlb build
```

### Completion criteria

An old artifact never generates an opaque SQL/DuckDB exception from `doctor`.

---

## 5.4 Prediction-count checks

### Current problem

Prediction health checks counted rows, while `gold.prediction` intentionally stores multiple temporal predictions for the same game.

### Fix

Define the grain that the check actually wants.

If checking game coverage:

```sql
COUNT(DISTINCT game)
```

or canonical game-instance identity.

If checking latest available prediction:

select one prediction per:

```text
game
model_version
cutoff
```

using the latest valid prediction before the cutoff.

Then separately investigate the remaining real Polymarket game-coverage discrepancy instead of hiding it.

### Completion criteria

Health checks test declared prediction coverage rather than incidental physical row count.

---

## 5.5 Backup health

### Current problem

The project-level backup check thinks backups do not exist because backups are performed by validated host infrastructure instead of `mlb backup`.

### Fix

Do not hard-code knowledge of one backup implementation into doctor.

Have the host backup process publish a small machine-readable status artifact, for example:

```json
{
  "database": "mlb",
  "last_success": "...",
  "dump": "...",
  "sha256_verified": true,
  "restore_tested_at": "...",
  "format": "pg_dump custom"
}
```

Configure the path in normal configuration.

Doctor reads the status contract.

### Completion criteria

Doctor reports healthy when a verified external backup satisfies the backup policy.

A restore test remains part of disaster-recovery validation.

---

## 5.6 Metric catalog empty state

### Fix

The catalog is code metadata and should stay synchronized with the checkout.

`mlb catalog build` should occur automatically in an appropriate maintenance stage after migrations/code deployment rather than depend on a human remembering it.

Doctor should compare:

```text
catalog rows
catalog YAML count
catalog git commit
```

if practical.

### Completion criteria

A normal nightly/deployment cannot leave `meta.metric` empty while metric manifests exist.

---

## 5.7 Never-vacuumed relations

Perform the required one-time `VACUUM (ANALYZE)` on affected relations after confirming they are not actively undergoing a large load.

Then investigate why autovacuum did not reach them.

Tune autovacuum per high-churn relation if evidence warrants it.

Do not globally disable or aggressively retune autovacuum based on one table.

### Completion criteria

No significant table has accumulating dead tuples with no visible vacuum path.

---

## 5.8 Optional model artifacts

A missing experimental GBM/stack/neural artifact should not make the database installation unhealthy.

Doctor semantics should be:

```text
required configured production model missing
→ ERROR

optional model never trained
→ NOT_CONFIGURED

candidate model unavailable
→ INFO/WARN

champion artifact referenced in metadata but missing
→ ERROR
```

---

## Phase 1 exit gate

Do not leave Phase 1 until:

```text
mlb nightly
```

completes successfully and:

```text
mlb doctor
```

reports zero required operational errors.

Any remaining warnings have written explanations and do not represent silent correctness failures.

---

# 6. Phase 2 — Stable identities and incremental conform

## North Star

Canonical identity survives forever, and only changed data is rebuilt.

This is the most important structural database change.

---

## 6.1 Stable identity

Convert:

```text
core.team
core.player
core.venue
core.game
```

from truncate/recreate semantics to persistent entities.

Use real natural/source keys and upserts.

Never automatically merge two existing player entities merely because a later source creates an ambiguous mapping.

Identity conflicts should be explicit.

---

## 6.2 Fingerprinting

Do not use only:

```text
row_count + max(_loaded_at)
```

as the change detector.

Use a build fingerprint that includes enough information to detect meaningful changes.

Conceptually:

```text
source artifact/content fingerprint
+ transform code version
+ schema version
+ relevant reference-data version
```

If immutable downloaded source artifacts already have SHA256 values, use those rather than hashing massive tables repeatedly.

---

## 6.3 Rebuild unit

Prefer season/partition-level replacement for historical facts.

A corrected 1974 source archive should not require rebuilding 1910–2026.

Changed input:

```text
1974
```

should dirty:

```text
1974
```

and any known downstream state dependent on later history.

---

## 6.4 Publish atomically

Build changed data into staging.

Validate.

Perform a short transactional publication.

Use lock timeouts.

Readers should continue to see the last valid dataset while the replacement builds.

---

## 6.5 Full-build oracle

Retain:

```bash
mlb conform --full
```

as the correctness oracle.

Create an automated test where:

```text
incremental build
```

and:

```text
fresh full build
```

produce identical canonical contents aside from intentionally non-semantic metadata such as timestamps.

Compare **every relevant non-key column**, not merely row counts.

---

## 6.6 Stable-ID completion criteria

After two identical conform runs:

```text
core.team IDs unchanged
core.player IDs unchanged
core.venue IDs unchanged
core.game IDs unchanged
```

After modifying one historical source partition:

```text
only affected partitions + declared downstream dependents rebuild
```

After incremental and full builds:

```text
0 unexplained differences
```

---

# 7. Phase 3 — Strengthen the canonical baseball event model

## North Star

Downstream calculations should not repeatedly reinterpret provider-specific event semantics.

The database should provide one canonical representation of game events.

---

## Problem

Several recent defects were caused by separate downstream SQL implementations independently understanding fields such as:

```text
bat_event_fl
resp_bat_id
resp_pit_id
pitch_seq_tx
outs_ct
start_bases_cd
runner flags
event_cd
```

This includes:

- pitch sequence double counting;
- responsible batter substitution problems;
- obstruction runs;
- baserunning semantics;
- catcher framing;
- PA identification.

These are signs that important baseball semantics remain trapped in raw.

---

## Proposed direction

Evaluate creating a typed canonical:

```text
core.event
```

while retaining:

```text
core.play / plate appearance
core.pitch
```

This would give:

```text
core.game
  ├── core.event
  ├── core.play
  └── core.pitch
```

`core.event` could contain canonical typed fields such as:

```text
game_id
event_index
batter_id
responsible_batter_id
pitcher_id
responsible_pitcher_id

event_type
is_batter_event
is_at_bat
is_sac_fly
is_sac_hit

outs_before
bases_before
runs_scored

pitch_sequence
runner-event flags
```

This should be its own OpenSpec design/research change, not an opportunistic refactor.

---

## Completion criteria

A downstream deterministic statistic should no longer need to know obscure Retrosheet parsing behavior unless the provider-specific behavior itself is the subject of the calculation.

---

# 8. Phase 4 — Make gold canonical and SQLMesh-owned

## North Star

Gold is a collection of deterministic, documented, validated, single-writer baseball models.

---

## 8.1 Freeze `gold.game_feature`

Do not continue expanding the giant wide feature table.

Treat it as compatibility/internal infrastructure.

New model-ready feature families should flow into the point-in-time feature-store architecture instead.

---

## 8.2 SQLMesh ownership

Use SQLMesh for deterministic, set-based core→gold transformations.

Do not move:

```text
identity reconciliation
network ingestion
Elo sequential updates
GBM training
Markov simulation
Monte Carlo
Bayesian fitting
```

into SQLMesh.

---

## 8.3 Promotion process

For every migrated relation:

```text
current writer
       ↓
candidate SQLMesh model
       ↓
same inputs
       ↓
full-table comparison
       ↓
sample PIT comparison if relevant
       ↓
audits
       ↓
performance measurement
       ↓
promote SQLMesh
       ↓
DELETE old writer
```

Never leave both writers active indefinitely.

---

## 8.4 Recommended first migrations

Start with relatively understood deterministic families.

Suggested order:

1. era-correct wOBA;
2. park factors;
3. straightforward team rates;
4. pitching estimators;
5. pitch movement;
6. platoon splits;
7. remaining deterministic feature families.

Avoid starting with the most complicated or currently questionable metrics.

---

## 8.5 SQLMesh audits

Each promoted model gets applicable blocking audits for:

```text
business-key uniqueness
required-key NULLs
foreign-key/orphan coverage
source coverage
season coverage
value-domain validity
fanout
impossible values
```

Range checks must represent genuine domain knowledge rather than arbitrary “looks plausible” limits.

---

## Phase 4 completion criteria

For every canonical gold relation:

```text
one writer
one documented grain
one defined business key
one lineage path
one build strategy
required audits
known coverage
known null policy
```

CI detects duplicate writer ownership.

---

# 9. Phase 5 — Repair and formalize the metric library

## North Star

The metric catalog becomes a trustworthy registry of baseball/statistical knowledge, not a collection of things an AI once generated.

---

## 9.1 Do not resurrect the deleted Gemini batch

The deletion of approximately 101 fabricated/disconnected metrics was correct.

Do not regenerate them wholesale.

Real concepts preserved in `TRIAGE_BACKLOG.md` may return individually through normal research/admission.

---

## 9.2 Add asset classification

The catalog currently contains fundamentally different things.

Add a concept similar to:

```text
statistic
feature
baseline
model
simulation
diagnostic
market_tool
```

Examples:

```text
wOBA → statistic
rolling K% → feature
Elo → baseline
Monte Carlo season simulation → simulation
drift monitor → diagnostic
```

---

## 9.3 Add use/admission classification

Separate:

```text
documented
```

from:

```text
allowed in production model
```

A useful model might be:

```text
research_only
model_candidate
model_approved
public_stat
disabled
```

or equivalent booleans.

---

## 9.4 Production feature gate

No metric with status equivalent to:

```text
implemented-untested
```

may silently enter an approved production model.

Novel features are permitted, but must explicitly be experimental and pass:

```text
PIT validation
chronological evaluation
ablation
stability analysis
```

before promotion.

---

## 9.5 Fix era-specific wOBA

This should be an early flagship cleanup.

You already ingest FanGraphs Guts constants.

The canonical historical wOBA implementation should resolve the appropriate weight set by season instead of applying one modern constant set across all eras.

All dependent wRC+/rolling calculations should use that owner.

---

## Metric completion criteria

Every published metric has:

```text
name
definition
formula owner
citation
data sources
grain
coverage
implementation
trust status
visibility
known limitations
test/tie-out
```

Every model-used metric additionally has:

```text
point-in-time semantics
admission status
```

---

# 10. Phase 6 — Finish the point-in-time feature platform

## North Star

A model cannot accidentally use information from the future.

---

## Required feature contract

Every feature field/family should know:

```text
source relation
event time
availability time
lookback/window
coverage
null policy
feature version
target compatibility
```

The important time is **availability time**, not merely event time.

Examples where they differ:

- probable starters;
- lineups;
- revised statistics;
- final season WAR;
- weather;
- market quotes;
- source publication delays.

---

## Feature artifact

A built DuckDB artifact should be immutable and content-addressable.

Include:

```text
artifact hash
feature schema version
feature-set version
git commit
source snapshot
built_at
```

---

## Completion criteria

Before a feature set can be used:

```text
mlb readiness
```

must establish:

- all declared columns exist;
- coverage is expected;
- nulls obey policy;
- no PIT leakage;
- source backbone tie-out passes;
- feature artifact integrity passes.

---

# 11. Phase 7 — Create the canonical target registry

## North Star

Every model predicts an explicitly defined event.

---

## Target schema

Each target should contain concepts such as:

```text
name
version
entity grain
prediction cutoff
prediction horizon
label formula
eligible games
void/censoring rules
evaluation metrics
market mapping rules
```

---

## Examples

### Game winner

```text
name: game.home_win
version: v1
grain: game
label: home_score > away_score
cutoff: scheduled first pitch
eligible: MLB regular season
type: binary
```

### Exact player 3-for-3

```text
name: player.exact_3_for_3
version: v1
grain: player-game

label:
hits = 3
AND official_at_bats = 3

cutoff:
declared prediction timestamp

void/censoring:
must be specified explicitly
```

This is different from:

```text
hits >= 3
```

and from:

```text
3 hits in 4 AB
```

The distinction must live in the target definition, not in prose surrounding a model.

---

## Completion criteria

Two different models evaluated on the same target are guaranteed to be predicting the same thing.

---

# 12. Phase 8 — Build the model ladder

## North Star

Complexity is earned by measurable improvement over simpler baselines.

---

## Recommended progression

For game winners:

```text
naive historical baseline
↓
Log5
↓
Elo
↓
regularized logistic regression
↓
CatBoost / XGBoost
↓
run-distribution model
↓
player-aware simulation / Markov
↓
ensembles only if justified
```

Do not prioritize neural networks yet.

---

## Evaluation rules

Never random-split time-series baseball forecasting data.

Use:

```text
train on past
validate on later period
test on later untouched period
```

Report at minimum:

```text
log loss
Brier score
calibration
calibration slope/intercept
season-by-season results
```

A model that is poorly calibrated does not get promoted simply because its accuracy is higher.

---

## Champion promotion

A model is `champion` only when its promotion contract passes.

Example:

```text
artifact exists
PIT readiness passed
holdout completed
beats required baseline by practical threshold
calibration acceptable
artifact immutable
model card written
```

Otherwise:

```text
candidate
```

is the honest result.

---

# 13. Phase 9 — Build the player/event simulation engine

## North Star

Player props and parlays come from coherent simulated baseball worlds rather than disconnected probability calculators.

---

## Player model direction

For an event like exact 3-for-3, model underlying mechanisms:

```text
P(player starts)
P(lineup position)
P(number of PA)
P(official AB | PA)
P(PA outcome | matchup/context)
```

Context may include:

```text
batter skill
pitcher skill
handedness
arsenal
bullpen
park
weather
defense
umpire
lineup
rest/workload
```

Simulation then naturally estimates:

```text
P(H = 3 AND AB = 3)
```

and also:

```text
P(H >= 2)
P(HR >= 1)
P(team wins)
P(player HR AND team wins)
```

from the same simulated games.

---

## Joint parlay principle

Do not estimate:

```text
P(A AND B)
```

by blindly multiplying independently trained probabilities.

Use:

```text
number of simulated worlds satisfying A and B
-----------------------------------------------
total simulated worlds
```

when both outcomes can be represented by the same simulation.

---

# 14. Phase 10 — Normalize market history properly

## North Star

Market comparison uses the exact executable market state that existed when the model prediction was made.

---

## Separate market concepts

Do not treat one mutable row as “the market.”

Create conceptual entities equivalent to:

### Market contract

```text
provider
provider_market_id
event
question
outcome
side
line
open time
close time
resolution semantics
```

### Market observation

```text
contract
observed_at
retrieved_at

bid
bid_size
ask
ask_size
last
volume
open_interest
liquidity
status
```

### Settlement

```text
contract
result
settlement value
settled_at
resolution source
void reason
```

---

## Target mapping

Each provider contract maps to a canonical target.

Example:

```text
provider contract ABC
→ game.home_win:v1
```

or:

```text
provider contract XYZ
→ game.total_runs_gt:8.5:v1
```

This mapping is where settlement semantics must be verified.

---

## Market research rules

Always distinguish:

```text
model probability
market mid/implied probability
executable buy price
fees
slippage
liquidity
```

If:

```text
model = 0.58
market displayed = 0.54
ask = 0.56
```

the relevant comparison for a buy is closer to `.56`, not `.54`.

---

## Historical cutoffs

The market system must honestly support:

```text
open
24h
6h
1h
close
```

by selecting the actual quote that existed at or before each cutoff.

No cutoff may silently reuse closing price.

---

# 15. Phase 11 — Research-run reproducibility

## North Star

A published claim can be reconstructed months later.

---

## Research-run identity

Every important experiment/published result should eventually point to:

```text
research_run_id

git_commit
schema_version
source snapshot hashes
target version
feature set version
feature artifact hash
model version
model artifact hash
hyperparameters
training period
validation period
test period
prediction cutoff
market observation cutoff
generated_at
```

---

## Model artifacts

Never identify the only copy of an important model by:

```text
models/gbm-v2.json
```

alone.

Use immutable artifact directories:

```text
models/artifacts/<content-or-run-id>/
    model...
    metadata.json
```

Human aliases such as:

```text
champion
candidate
```

may reference immutable artifacts.

All model writes should use temp-file + atomic replacement.

---

# 16. Phase 12 — Public research product

## North Star

A researcher who does not want to operate your producer infrastructure can still use the output easily.

---

## Producer product

The full producer may require:

```text
PostgreSQL
Retrosheet
MLB API
Statcast
SQLMesh
market connectors
large historical build
```

That is acceptable.

---

## Consumer product

The consumer should ideally require:

```bash
pip install mlb-research
```

and operate primarily through:

```text
Parquet
DuckDB
Python
```

A researcher should not need PostgreSQL or Chadwick system binaries merely to query the published dataset.

---

## Bootstrap profiles

Eventually add supported profiles such as:

```text
research-core
research-full
statcast
markets
modeling
everything
```

A researcher interested in historical batting should not have to download every pitch and every market quote.

Do not add these commands until they are backed by clearly defined dependency groups.

---

# 17. Annual source rollover

## North Star

Current-season provisional data transitions into finalized historical data through an explicit reconciliation rather than silently changing source ownership.

---

## Workflow

When Retrosheet releases a completed season:

```text
MLB-current-season version
          ↓
       compare
          ↑
Retrosheet-finalized version
```

Compare important grains and aggregates.

Classify differences:

```text
MATCH
EXPLAINED SOURCE DIFFERENCE
SOURCE CORRECTION
UNRESOLVED
```

Only after the gate passes does historical ownership transition.

---

## Completion criteria

The source transition for a season is an auditable event.

---

# 18. Rebuild `mlb doctor` as a diagnostic registry

## North Star

`mlb doctor` becomes the project's operational expert.

---

## Check object

Every check should have stable structured metadata:

```text
id
scope
component
severity
status
summary
details
dependencies
remediation
documentation
duration
```

---

## Desired statuses

Use something richer than pass/fail:

```text
PASS
WARN
ERROR
INFO
SKIPPED
NOT_CONFIGURED
EXPERIMENTAL
```

---

## Registry approach

Subsystems register checks.

Doctor discovers the registry.

Do not manually import and invoke dozens of modules in `doctor.py`.

---

## Scopes

Recommended UX:

```text
mlb doctor
```

Operational installation health.

```text
mlb audit
```

Database/data-contract correctness.

```text
mlb readiness
```

Feature/target/model admission.

Optionally:

```text
mlb doctor --deep
```

summarizes all three.

---

## JSON

Every important diagnostic command should support machine-readable output.

For example:

```bash
mlb doctor --json
mlb audit --json
mlb readiness --json
mlb runs --json
```

This is essential for future AI automation.

---

# 19. End-to-end reference database acceptance test

## North Star

CI proves that the machine still works as a machine, not only as a set of modules.

Create one intentionally tiny fixture containing enough weirdness to exercise the architecture:

```text
multiple seasons
doubleheader
postseason
trade
mid-PA substitution
baserunning event
starter change
one missing source field
one market
one market price change
```

Run:

```text
migrate
↓
load fixtures
↓
conform
↓
gold
↓
feature build
↓
readiness
↓
baseline model
↓
export
```

Compare canonical outputs against versioned expected results.

## Completion criterion

CI can prove:

> A clean environment can produce a coherent, research-ready baseball database from source fixtures.

---

# 20. CI quality gates

The following should eventually be hard merge gates for relevant changes.

## General code

```text
ruff
mypy
tests
secret scanning
migration tests
docs build
```

Already largely present.

## Database

Add/strengthen:

```text
single-writer ownership lint
business-grain uniqueness
incremental/full equivalence
schema contracts
```

## Metrics

```text
catalog completeness
validated test reference
disabled metric cannot be production feature
```

## SQLMesh

Once production ownership begins:

```text
SQLMesh model tests
SQLMesh blocking audits
plan validation
```

## Feature store

```text
PIT leakage tests
artifact schema/version checks
feature readiness
```

## Models

```text
artifact-path safety
atomic writes
target compatibility
no production promotion without evaluation evidence
```

---

# 21. Definition of Done for every future feature

Every non-trivial new feature should answer this template before implementation.

## Problem

What exact research capability is missing?

## User

Who needs it?

```text
database researcher
model developer
market researcher
subscriber
AI agent
```

## Grain

What does one row/result mean?

## Source

Where does the input come from?

## Identity

How does it map to canonical players/teams/games/contracts?

## Time

When did the event occur?

When did the information become knowable?

## Formula/model

What calculates the result?

Is the implementation deterministic or learned?

## Owner

What single piece of code owns the output?

## Null semantics

What does NULL mean?

Never use zero to mean “unknown.”

## Coverage

What seasons/providers/populations are supported?

## Validation

What independent evidence can verify the output?

## Failure behavior

How will doctor/audit/readiness identify failure?

## Rights

Can the output be redistributed publicly?

## Performance

What expected build/query cost is acceptable?

## Completion

The feature is not done until:

- tests pass;
- contract exists;
- grain enforced;
- ownership declared;
- source lineage declared;
- PIT rule declared where applicable;
- validation passes;
- doctor/audit/readiness knows how to assess it;
- documentation is updated;
- old implementation is removed if this replaced one.

---

# 22. AI skills North Star

## North Star

AI agents operate the platform through the same deterministic interfaces humans use.

The agent should not contain hidden baseball logic.

---

## Skills should teach workflows

Eventually create skills such as:

```text
mlb-diagnose
mlb-add-source
mlb-add-metric
mlb-add-target
mlb-build-feature-set
mlb-run-research
mlb-market-study
mlb-publish-research
```

---

## Example `mlb-diagnose` behavior

Agent:

1. runs `mlb doctor --json`;
2. identifies failed dependency;
3. runs a read-only focused diagnostic;
4. identifies likely root cause;
5. recommends or performs the authorized repair;
6. reruns the failing check;
7. records evidence.

It should not randomly edit SQL until the check turns green.

---

# 23. The concrete implementation order from today's repository

This is the order I recommend following.

## Priority A — finish what is already open

1. Finish `pipeline-recovery`.
2. Complete odds-history capture/backfills and scheduling.
3. Resolve catcher framing by withholding broken current-season outputs.
4. Repair `meta.ingestion_item`.
5. Fix feature-artifact stale-schema diagnostics.
6. Correct prediction coverage checks.
7. Make backup health understand the real host backup.
8. Resolve legitimate domain checks using source/formula evidence.
9. Ensure the catalog rebuilds automatically.
10. Verify several consecutive clean nightly runs.

Do not open a large new architecture project while this remains unfinished.

---

## Priority B — database identity

11. Finish measurement for stable IDs.
12. Correct the fingerprint design.
13. Upsert team/player/venue/game.
14. Make IDs stable.
15. Implement changed-season rebuilds.
16. Implement atomic publication.
17. Prove incremental/full equivalence.
18. Run production-copy comparison.
19. Promote incremental nightly operation.

This is the most important architecture milestone.

---

## Priority C — gold convergence

20. Establish machine-readable writer ownership.
21. Freeze expansion of `gold.game_feature`.
22. Fix canonical era-specific wOBA.
23. Promote first real SQLMesh gold model.
24. Add blocking audits.
25. Delete the old writer.
26. Repeat model-by-model.
27. Remove stale SQLMesh shadow copies or bring them to parity before promotion.

---

## Priority D — canonical event semantics

28. Design the `core.event`/plate-appearance boundary.
29. Solve responsible batter/pitcher semantics centrally.
30. Solve runner/pitch-sequence semantics centrally.
31. Update downstream gold models to consume canonical facts.

Do this deliberately, not as a giant rewrite.

---

## Priority E — research platform

32. Finish target registry.
33. Strengthen feature-set contracts.
34. Produce immutable DuckDB artifacts.
35. Finish baseline Elo/log5 pipeline.
36. Add regularized logistic baseline.
37. Add CatBoost/XGBoost challenger.
38. Implement formal champion promotion.
39. Store complete research-run lineage.

---

## Priority F — market intelligence

40. Normalize market contracts.
41. Normalize quote history.
42. Normalize settlement.
43. Map market contracts to canonical targets.
44. Support real quote cutoffs.
45. Calculate executable edge rather than screen-price difference.
46. Add fees/liquidity/slippage assumptions.
47. Backtest market research chronologically.

---

## Priority G — advanced player/prop modeling

48. Build player/PA target family.
49. Build matchup model.
50. Feed it into a game simulation.
51. Produce joint probabilities from simulations.
52. Validate player props chronologically.
53. Compare them to matching market contracts.

---

## Priority H — productization

54. Harden `mlb-research`.
55. Finish `retrosheetpy` parity/package independence.
56. Publish stable Parquet releases.
57. Make public rights enforcement automatic.
58. Build reproducible research-report publishing.
59. Build subscriber-facing presentation.
60. Build AI skills over the stable CLI.

---

# 24. What “perfect shape” means

The project cannot literally become incapable of bugs. Upstream APIs change, providers correct historical records, and software evolves.

The achievable goal is much better:

> **The system detects when it is wrong, localizes why it is wrong, refuses to make unsupported claims, preserves enough evidence to repair itself, and can rebuild every derived result reproducibly.**

That means the platform is in excellent shape when:

```text
fresh installation
→ understandable

bootstrap
→ resumable

raw
→ preserved

core
→ stable

gold
→ deterministic

features
→ leak-free

models
→ calibrated and reproducible

markets
→ timestamp-correct

doctor
→ actionable

audit
→ trustworthy

research
→ reproducible

publishing
→ source-backed

AI agents
→ safe and deterministic
```

That is the system we should be building.

# 25. Immediate project milestone

I would name the current milestone something like:

**Platform Convergence**

Its completion criteria should be:

- pipeline recovery complete;
- required `mlb doctor` checks green;
- stable IDs implemented;
- full/incremental conform equivalent;
- normal nightly operation incremental and reliable;
- no known invalid metric feeding an approved model;
- writer ownership established;
- feature artifact/version diagnostics reliable;
- backup state verifiable;
- item-level ingestion ledger trustworthy;
- at least one gold model fully promoted to SQLMesh under the new one-writer/audit rules;
- a clean end-to-end fixture build passes in CI.

Only after that milestone should aggressive new modeling and commercial research development resume.

That gives the project a clear finish line instead of an endless series of interesting additions.

I would make this **the controlling execution order**, but I would avoid creating another pile of overlapping documentation. The best implementation is to fold the project-level North Star and milestone gates into `openspec/project.md`, use the existing `TABLE_CONTRACTS.md`, `SQL_OWNERSHIP.md`, `FEATURE_STORE.md`, `RESEARCH.md`, and audit/readiness docs for their respective contracts, and then let individual OpenSpec changes implement each phase. I would create at most one new cross-cutting document—something like `docs/ACCEPTANCE_GATES.md`—only if we find that the completion criteria cannot cleanly live in the existing constitution.

The three highest-value upgrades from here are therefore **stable immutable identity**, **single-writer/validated gold transformations**, and **structured diagnostics that distinguish broken from optional**. After those, the target/market/research-run architecture is what turns the database into the forecasting and commercial research platform you actually want.
