Yes. I reviewed the current `main` branch of `cbwinslow/mlb-baseball` at commit `93402ee` (October 5, 2026), including the architecture/constitution, current handoff and recovery work, raw/core/gold contracts, migrations, connectors, SQL resources, SQLMesh project, metric catalog and its Gemini-generated history, feature store, modeling code, market ingestion, health/audit/readiness systems, CI, tests, open issues, and the stable-ID/incremental-conform design.

My overall conclusion is:

**Do not rewrite this project. Do not switch databases. Do not add another orchestration framework. Do not start adding another hundred sabermetric formulas.**

The project has crossed the point where the main problem is lack of capability. The main problem is now **convergence**: making every important concept have one authoritative representation, one writer, one contract, one validation path, and one clear failure mode.

I think you are much closer to the research platform you described than it probably feels when `mlb doctor` is throwing dozens of failures.

# Overall verdict

Architecturally, I would put the project roughly here:

| Area | Current state | My assessment |
|---|---|---|
| Source ingestion | Strong | One of the better parts of the project |
| Raw preservation/provenance | Strong | Keep the general approach |
| Identity/conformance | Good design, problematic rebuild mechanics | **Highest database priority** |
| Historical baseball backbone | Strong and improving | Real research value already exists |
| Gold statistics | Valuable but fragmented | Needs canonical ownership |
| SQLMesh | Correct choice, incompletely adopted | Finish the migration deliberately |
| DuckDB feature store | Strong direction | Keep it |
| Point-in-time/leakage controls | Strong | Major differentiator |
| Metric catalog | Excellent concept | Needs a stricter trust/admission layer |
| Gemini metric batch | Correctly triaged | Do **not** resurrect it |
| `mlb doctor` | Excellent idea, overgrown implementation | Redesign internals, preserve UX |
| `mlb audit` | Good separation | Keep and expand |
| Model harness | Promising | Too much experimental code mixed together |
| Market data | Strategically important but under-normalized | **Major next data-model project** |
| Experiment reproducibility | Good foundation | Needs complete artifact lineage |
| Tests/CI | Strong | Better than most projects at this stage |
| Packaging/reusability | Very promising | Finish dependency separation |
| Agent automation | Premature for deep automation | Build after CLI/contracts stabilize |
| Commercial research readiness | Not yet | Database can get there before models do |

The biggest thing I want to emphasize is that you now have a **real data-engineering project**, not a pile of scripts. You have about 109 SQL migrations, 19 connectors, 136 named SQL resources, 18 SQLMesh models, around 50 surviving metric manifests, 62 modeling modules, and 229 unit/integration test modules. You also have real production lessons encoded into ADRs and tests.

That scale changes what “improvement” means.

From now on, **deleting duplication and establishing authority is more valuable than adding features**.

---

# The architecture I would ultimately aim for

I would make the conceptual architecture extremely simple:

```text
UPSTREAM SOURCES
      │
      ▼
┌─────────────┐
│     raw     │  Source-faithful evidence
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    core     │  Canonical baseball facts + identity
└──────┬──────┘
       │
       ├──────────────────────┐
       ▼                      ▼
┌─────────────┐       ┌───────────────┐
│    gold     │       │ market facts  │
│ statistics  │       │ + quote time  │
└──────┬──────┘       └───────┬───────┘
       │                       │
       └───────────┬───────────┘
                   ▼
            ┌─────────────┐
            │ DuckDB feat │
            │ point-in-   │
            │ time data   │
            └──────┬──────┘
                   │
                   ▼
          ┌──────────────────┐
          │ Models / Sim     │
          │ Python           │
          └────────┬─────────┘
                   │
                   ▼
          ┌──────────────────┐
          │ Predictions      │
          │ evaluations      │
          │ market research  │
          └────────┬─────────┘
                   │
                   ▼
          ┌──────────────────┐
          │ publish / serve  │
          │ research / web   │
          └──────────────────┘
```

And I would attach one governing rule to every layer:

**Raw preserves evidence. Core establishes truth. Gold calculates descriptive baseball knowledge. Feat answers “what was knowable then?” Python estimates uncertain future outcomes. Market data measures what someone could actually trade. Serve publishes results.**

That is the architecture I would optimize everything around.

---

# The database is fundamentally pointed in the right direction

PostgreSQL remains the right system of record.

I would **not move this to ClickHouse**. I would not replace PostgreSQL with DuckDB. And I would definitely not make SQLMesh responsible for identity reconciliation.

Your workload consists of identity resolution, foreign keys, source reconciliation, lineage, mutable ingestion state, historical facts, data-quality constraints, and moderately large analytical relations. PostgreSQL is very good at this.

DuckDB is also being used in exactly the place where it makes sense: portable analytical artifacts and model-ready point-in-time feature data. DuckDB can directly and efficiently query Parquet with projection/filter pushdown, which is particularly attractive for the public/research distribution side of this project. [DuckDB](https://duckdb.org/docs/current/guides/file_formats/query_parquet?utm_source=chatgpt.com)

So I strongly endorse:

```text
PostgreSQL = authoritative producer database
DuckDB/Parquet = portable analytical/research surface
Python = modeling + simulation
SQLMesh = deterministic transformation management
```

That combination is excellent.

---

# The single biggest database defect is unstable identity

This should be your highest architectural priority after the current pipeline-recovery defects.

The existing nightly `conform` behavior truncates and reconstructs a large chunk of `core`, which reissues IDs. That forces downstream relations to be rebuilt because a `core.game.id`, `core.player.id`, etc. isn't really an enduring identity.

The project itself has now identified this correctly in `stable-ids-incremental-conform`.

This is more important than performance.

Even if a full rebuild took five minutes, I would still tell you to change it.

An internal ID should mean:

> This entity got this ID once, and this ID remains its ID indefinitely.

A research paper, cached artifact, feature snapshot, model prediction, exported dataset, market match, or external consumer should never have to wonder whether yesterday's `game_id=12345` refers to tomorrow's `game_id=12345`.

The stable-ID proposal's general direction is correct:

```text
core.team
core.player
core.venue
core.game
```

should become persistent key maps themselves.

Incoming source rows should be **upserted**, not reconstructed from scratch.

Old rows that disappear from a provider should not automatically be deleted.

Conflicting identifiers should be surfaced.

Past seasons should be rebuilt because their **inputs changed**, not because today's calendar date changed.

This unlocks an enormous amount of simplification later.

It allows stable FKs, incremental gold builds, stable model artifacts, reliable caches, smaller nightly workloads, and meaningful historical lineage.

This is the change I would call the **database's architectural graduation point**.

---

# One modification I would make to the stable-ID design

The original fingerprint design was:

> row count + latest `_loaded_at`

I agree with the later pipeline-recovery review that this is insufficient.

Imagine:

```text
rows before = 1,000,000
rows after  = 1,000,000
_loaded_at unchanged
```

but somebody corrected one source value.

A row-count fingerprint misses it.

A trustworthy build signature should incorporate something like:

```text
source/version
season
row_count
content checksum
source artifact checksum
transform code version
reference-data version
schema version
```

You don't necessarily need to SHA every 50 GB table nightly.

You already download/archive source artifacts. Prefer hashing the immutable source artifact when available, then combine that with transformation version and relevant reference versions.

Conceptually:

```text
input_fingerprint =
    hash(
        source_artifact_sha256,
        transform_git_sha,
        schema_version,
        reference_versions
    )
```

Then rebuild only the partition whose effective fingerprint changed.

That gives you actual reproducibility.

---

# I would also make all big publishes atomic

You found the ugly consequence already: the current relationship between conform and report can leave downstream relations empty or unavailable if one stage dies.

The corrected pattern should universally be:

```text
build
   ↓
staging
   ↓
validate
   ↓
atomic publish
   ↓
analyze
```

not:

```text
TRUNCATE production
   ↓
hope the rebuild succeeds
```

For partitioned facts:

```text
build new season partition
validate new partition
short transaction / partition swap
ANALYZE
```

For ordinary tables:

```text
build shadow/staging relation
validate
short transactional replacement/upsert
```

For SQLMesh-controlled gold relations, this is one of the reasons SQLMesh becomes useful. SQLMesh plans can evaluate modified models and their blocking audits before promotion into the production environment; its incremental model types also directly support time-range, unique-key, and partition-oriented transformations. [SQLMesh](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/?utm_source=chatgpt.com)

That is a much better match for the gold layer than home-grown `TRUNCATE → INSERT`.

---

# Raw is mostly designed correctly

I like your philosophy here.

Source-faithful, append/scoped-replace where appropriate, minimally transformed, replayable, and tolerant of upstream schema changes is exactly what raw should be.

I would **not “clean up” raw by imposing a giant relational model on it**.

But your raw layer needs one thing strengthened: **schema-change observability**.

Allowing:

```text
ALTER TABLE ADD COLUMN
```

is useful because it means an upstream addition doesn't destroy ingestion.

But tolerance must not become invisibility.

Each connector should record a source schema fingerprint, for example:

```text
source
relation
observed_at
columns
required_columns
new_columns
missing_columns
inferred_types
artifact_hash
row_count
```

Then:

```text
new optional source column
→ INFO

expected column disappeared
→ ERROR

important field changed format
→ ERROR

new unused column
→ INFO

raw row count suddenly falls 97%
→ ERROR/WARN
```

`mlb source-check` is already moving toward this idea.

Expand that rather than adopting another data-quality framework.

---

# There is one deeper problem between raw and core

This may be the most important structural observation beyond stable IDs.

Today several important gold calculations still have to reach back into `raw.retrosheet_event`.

Why?

Because `core.play` does not preserve all the semantic information required downstream.

Your own production investigations proved examples:

```text
bat_event_fl
ab_fl
sf_fl
sh_fl
event_cd
outs_ct
start_bases_cd
responsible batter/pitcher
pitch sequence
runner events
```

are important.

And the recent bugs prove why centralizing the interpretation matters:

- mid-plate-appearance substitutions;
- repeated pitch sequences on runner events;
- responsible batter vs current batter;
- obstruction-run accounting;
- baserunning events;
- first-pitch strike double counting;
- catcher framing accidentally parsing `event_tx`.

These aren't random bugs.

They are telling you something about the data model:

**Retrosheet's event semantics deserve a canonical typed fact representation.**

I would seriously consider eventually creating:

```text
core.event
```

at one Retrosheet event-record grain, containing typed canonical state such as:

```text
game_id
event_index
batter_id
responsible_batter_id
pitcher_id
responsible_pitcher_id

is_batter_event
is_at_bat
is_sac_fly
is_sac_hit

event_type
outs_before
bases_before
runs_on_event

pitch_sequence
runner_advance flags
...
```

Then separately retain:

```text
core.play / core.plate_appearance
```

for the completed plate-appearance fact.

And:

```text
core.pitch
```

remains the pitch/tracking fact.

That gives you a beautiful three-level event spine:

```text
game
  ├── event
  ├── plate appearance
  └── pitch
```

I would **not rush this into the current recovery change**, because it touches a foundational grain.

But I think this is where the database ultimately wants to go.

It would dramatically reduce the number of downstream modules that independently reinterpret Retrosheet semantics.

---

# Your current historical statistical backbone is valuable

The new grain ladder is one of the strongest pieces of this repository.

Having:

```text
gold.batting_game
gold.pitching_game

gold.batting_season
gold.pitching_season

gold.batting_team
gold.pitching_team

gold.batting_career
gold.pitching_career

gold.batting_postseason
gold.pitching_postseason
```

is exactly the sort of boring, reusable research infrastructure that academics and analysts actually need.

I also like that you have refused to fabricate ERA where earned runs are not honestly reconstructable.

That philosophy is important:

```text
missing because unknowable
```

is vastly better than:

```text
plausible-looking number
```

The project should become almost fanatical about preserving that principle.

---

# The current-year / historical-source split needs an explicit rollover workflow

You currently have a sensible source split:

```text
Retrosheet       → historical finalized seasons
MLB box scores   → current season
```

because Retrosheet naturally lags the live season.

But every winter you will eventually hit:

```text
MLB 2026 version
vs.
Retrosheet 2026 version
```

You need a first-class annual reconciliation process.

Something like:

```text
mlb reconcile season 2026
```

should compare the two source versions across:

```text
games
PA
AB
H
2B
3B
HR
BB
HBP
SO
runs
pitching outs
...
```

Then produce:

```text
MATCH
EXPLAINED DIFFERENCE
SOURCE CORRECTION
UNRESOLVED
```

Only after the gate passes should historical ownership move from:

```text
mlb_boxscore
```

to:

```text
retrosheet_event
```

for that season.

That gives you an extraordinarily valuable research property:

**a season's historical interpretation changes through an explicit, audited source transition rather than silently one morning.**

---

# Gold needs a much sharper meaning

Currently `gold` means too many things:

- descriptive baseball statistics;
- reporting tables;
- pregame features;
- model feature columns;
- predictions;
- market baselines;
- evaluation outputs;
- experiments.

That worked while the project grew organically.

It is becoming confusing now.

I would define gold narrowly:

> **Gold is deterministic, reproducible baseball knowledge derived from canonical facts.**

Examples:

```text
batting_game
batting_season
pitching_game
pitching_season
RE24
win expectancy
park factors
team rolling rates
platoon splits
pitch movement aggregates
```

But I would stop thinking of learned model predictions as gold.

Long-term I prefer something conceptually like:

```text
raw.*
core.*
gold.*
meta.*

feat.*       -- DuckDB artifact
pred.*       -- predictions/model outputs
serve.*      -- consumer views
```

You don't have to rename `gold.prediction` tomorrow. That would generate unnecessary migration work.

But semantically, keep the distinction in new design.

---

# `gold.game_feature` should be frozen rather than expanded

This is one of the project's most important cleanup opportunities.

`gold.game_feature` became a kitchen-sink relation.

Many modules mutate it:

```text
starter
offense
bullpen
park
war
framing
speed
OAA
pitch discipline
movement
command
platoon
interaction terms
...
```

That is how you end up with:

```text
one enormous table
many partially independent writers
rebuild ordering requirements
many health checks
null semantics depending on feature family
```

You already built the correct escape hatch:

```text
DuckDB feat.*
```

I would now declare:

**No new broad feature family gets added to `gold.game_feature` unless necessary for compatibility.**

Treat it as legacy/internal compatibility.

New model-ready feature families should go through the versioned PIT feature system.

Eventually:

```text
feat.game
feat.team_form
feat.player_form
feat.pitcher_form
feat.market
feat.lineup
...
```

can replace its modeling role.

This is a far cleaner design.

---

# SQLMesh: keep it, but finish the decision

This has been an ongoing question in our previous discussions.

My answer after reviewing the current repo is much firmer now:

**Yes, SQLMesh should become the authoritative engine for deterministic gold transformations.**

But:

**No, SQLMesh should not own raw ingestion or core identity reconciliation.**

That boundary is correct.

SQLMesh has native incremental model strategies, planning/versioning, tests, audits, backfills, and environment semantics that fit deterministic analytical transformations very well. [SQLMesh](https://sqlmesh.readthedocs.io/en/latest/reference/model_configuration/?utm_source=chatgpt.com)

Your desired split should become:

```text
NETWORK / PARSING / IDENTITY
Python

raw → core identity reconciliation
Python orchestration + named SQL

core → gold deterministic transformations
SQLMesh

point-in-time DuckDB feature artifacts
SQL

training / Bayesian fitting / XGBoost / simulation
Python

serving
SQL/views + application layer
```

The problem today is that SQLMesh is simultaneously:

```text
adopted
```

and:

```text
still mostly a shadow implementation
```

Issue #70 reflects this.

That cannot remain permanent.

---

# The SQLMesh promotion process should be boring

Every existing deterministic Python/SQL feature should migrate individually.

The lifecycle should be:

```text
legacy writer
      │
      ├── run
      │
      ▼
expected output

SQLMesh candidate
      │
      ├── run same source data
      ▼
candidate output

compare:
  grain
  row count
  keys
  NULLs
  every output field
  historical ranges
  PIT samples
  performance

         PASS
           │
           ▼
make SQLMesh canonical
           │
           ▼
DELETE OLD WRITER
```

Never:

```text
Python writes table
AND
SQLMesh writes table
```

for an indefinite period.

You already have this doctrine in pieces.

Now enforce it mechanically.

---

# SQLMesh's current audit coverage is too small

I counted 18 SQLMesh models but only a tiny native audit surface.

That is nowhere near enough if SQLMesh becomes authoritative.

Every production gold model should have at least its applicable versions of:

```text
grain uniqueness
required-key NOT NULL
accepted domains
reasonable cardinality
referential coverage
source coverage
season coverage
no impossible values
no fanout
PIT restrictions when appropriate
```

SQLMesh audits are specifically designed to validate real model output after execution, and blocking audits can stop downstream propagation when they return invalid rows. [SQLMesh](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/?utm_source=chatgpt.com)

Use that.

Your current `health_check()` logic contains a huge amount of business knowledge that could become model-local audits.

That is another way to shrink `doctor`.

---

# The Gemini metric library: the project already made the right first move

This was one of the things you specifically asked me to settle.

I read `mlb_baseball/metrics/TRIAGE_BACKLOG.md`.

The original AI batch was roughly 151 metric catalog entries, around 135 produced by the external AI effort.

The later triage deleted **101** of those entries and their associated dead implementations.

That was correct.

Some weren't merely buggy.

Some invented:

```text
acronyms
coefficients
thresholds
composite statistics
```

that had no actual sabermetric basis.

Do not attempt to “repair the batch.”

Do not bring it back.

Do not ask another model to regenerate everything.

That would recreate the exact problem you have spent weeks undoing.

---

# What should happen to the surviving metrics

The **catalog itself is excellent**.

Keep:

```text
mlb_baseball/metrics/*.yaml
meta.metric
generated documentation
citation
formula owner
data source
grain
implementation
status
visibility
test_ref
```

That is valuable infrastructure.

But distinguish:

```text
cataloged
```

from:

```text
trusted
```

For example, the current `team_woba` entry is refreshingly honest. It says the calculation uses fixed weights across all seasons even though you now have era-specific FanGraphs Guts constants available. Its tests are self-consistency tests, not independent external tie-outs, so the catalog marks it `published`, not `validated`.

That's precisely the right mentality.

The current catcher-framing entry is even more illustrative: it honestly says its 0.33 and 0.125 constants are project-derived and the implementation is `implemented-untested`.

And your October 5 investigation has now gone farther: the underlying implementation is genuinely invalid because it interprets play-description text as pitch information.

That metric should **not merely remain “untested.”**

Its current-season outputs should be withheld until rebuilt properly.

I agree with the current recovery recommendation:

```text
KEEP
prior-season Savant framing value

WITHHOLD
project-derived in-season CSAE/framing runs

until a defensible model exists
```

The attempted Statcast reproduction only reaching modest correlation with the published framing data is evidence that you cannot reasonably call the approximation equivalent.

That is exactly the kind of intellectual honesty that will make this project credible.

---

# I would add one more concept to the metric catalog

Today the catalog describes quality/status, but I would add explicit **admission/use**.

Something conceptually like:

```yaml
usage:
  public_stat: true
  research: true
  model_feature: false
  production_prediction: false
```

or a single tier:

```text
reference
validated
research
experimental
disabled
```

because these are different questions:

> Is this formula documented?

> Is it independently validated?

> Is it acceptable to publish?

> Is it safe to feed into a model?

> Is it experimental?

A clever experimental feature can be perfectly legitimate in research without being something you should publish as established sabermetrics.

Conversely, Baseball Savant's source-native value may be safe as a feature even if you cannot reproduce their proprietary internal formula.

Don't try to encode all those meanings into `status` alone.

---

# I would also stop calling everything a “metric”

The surviving catalog contains things such as:

```text
Elo
Monte Carlo simulations
drift monitoring
player prop projections
Markov win probability
Stuff+ style engines
```

Those aren't all the same category.

The existing `model/` directory has the same problem.

Issue #203 already recognizes it.

You don't need a giant refactor immediately, but introduce an asset kind:

```text
statistic
feature
baseline
model
simulation
diagnostic
market_tool
```

Then the catalog and `doctor` can behave intelligently.

For example:

```text
batting average
→ statistic

rolling 30-day K%
→ feature

Elo
→ baseline model

Monte Carlo season simulation
→ simulation

calibration drift
→ diagnostic
```

That single distinction will clean up a surprising amount of conceptual confusion.

---

# There is an immediate metric quality gate I would impose

Until the Gemini fallout is completely resolved:

> **No `implemented-untested` AI-generated metric can become a production model input merely because it produces numbers.**

Admission should require either:

```text
published formula
+ verified implementation
+ PIT-safe data lineage
+ realistic fixture/tie-out
```

or, for novel/project-derived features:

```text
explicitly experimental status
+ documented derivation
+ chronological evaluation
+ ablation result
+ no leakage
```

The computer does not care whether a feature has a made-up coefficient.

It will happily fit on it.

That makes bad experimental features more dangerous, not less.

---

# `mlb doctor` is a fantastic product idea

Keep the command.

In fact, I think it could become one of the things people love about the project.

A new researcher should be able to run:

```bash
mlb doctor
```

and have the system explain:

```text
what is wrong
why it is wrong
how confident we are
where it lives
what command diagnoses it
what command fixes it
whether it is safe to continue
```

That is a legitimately differentiating feature.

But the current implementation needs to be redesigned internally.

---

# `mlb doctor` is currently doing too much

Right now `doctor.py` manually imports and checks:

```text
connectors
conform
model
report
feat
experiment
selection
serve
simulate
props
season
portfolio
research
export
calibration
drift
backtest
ROS
stack
parlay
stuff
heatmap
neural
pipeline
visual
hedge
bullpen
arm slot
BABIP
VAA
NRFI
tunnel
API
shop
daemon
backup
...
```

with repeated blocks resembling:

```python
try:
    checks.extend(foo.health_check())
except Exception:
    ...
```

That is fragile.

Adding a subsystem doesn't automatically make it visible to doctor.

Deleting one can leave stale registration.

And today an experimental model can make the database appear “unhealthy.”

That is partly why you can get something like:

```text
353 / 370 checks passing
```

after a successful production night.

A genuinely healthy production warehouse should not look red because an optional GBM artifact hasn't been trained.

---

# Doctor should become registry-driven

The modules should register their checks rather than doctor knowing them all.

Conceptually:

```python
@health_check(
    id="market.polymarket.snapshot_freshness",
    scope="market",
    severity="error",
    requires=["database"],
    remediation="mlb odds-capture",
)
def check_polymarket_snapshot_freshness(ctx): ...
```

Then doctor asks the registry what exists.

Each result should have structured fields:

```json
{
  "id": "gold.catcher_framing.domain",
  "status": "FAIL",
  "severity": "ERROR",
  "scope": "research",
  "component": "catcher_framing",
  "summary": "framing values violate validated domain",
  "cause": "...",
  "evidence": "...",
  "remediation": "...",
  "docs": "...",
  "duration_ms": 83
}
```

This makes it usable by humans **and AI agents**.

---

# And doctor should have scopes

You already have much of the functionality distributed among `doctor`, `audit`, `readiness`, etc.

Don't collapse everything together.

I would make the UX behave roughly like:

```text
mlb doctor
installation + operational health

mlb doctor --data
raw/core/gold freshness

mlb audit
data-contract integrity

mlb readiness ...
ML feature/target admission

mlb doctor --deep
all of the above summarized
```

The normal `mlb doctor` should answer:

> Can this installation operate normally?

It should not fail because:

```text
an optional model isn't trained
a historical optional backfill wasn't requested
an experimental metric is disabled
```

Those should be:

```text
INFO
SKIPPED
NOT_CONFIGURED
EXPERIMENTAL
```

not red errors.

That change alone will make the system feel vastly more dependable.

---

# Your recent doctor investigations are actually evidence that the philosophy works

Look at what it recently uncovered:

```text
away_woba being overwritten
pitch-sequence double counting
BRef postseason leakage
stale DuckDB feature schema
false backup assumptions
catcher framing computation defect
prediction-count semantics
optional history wrongly treated as required
```

Those are meaningful bugs.

And importantly, your current recovery standard has become:

> trace the problem to the source; do not widen the health bound merely to silence the check.

That is the right standard.

I would preserve that principle permanently.

A good health check is not:

```text
value was -14
bound says -10
change bound to -20
```

A good health check asks first:

```text
Is -14 impossible?
Is our calculation wrong?
Is our assumption wrong?
Is the source meaning different?
```

The recent first-pitch-strike investigation is a perfect example.

---

# I would preserve the distinction among doctor, audit, and readiness

You already have the right pieces.

`doctor`:

> Is the system functioning?

`audit`:

> Is the database consistent with its declared contracts?

`readiness`:

> Is this particular feature artifact safe to use for this modeling purpose?

That is an excellent three-level design.

Do not build a fourth generic “validation framework.”

Make those three clearer.

---

# The open `meta.ingestion_item` problem is important

This is higher priority than it may seem.

Your run-level ledger is good:

```text
meta.ingestion_run
```

but item-level durability is what lets you answer:

```text
Which game failed?
Which endpoint?
Why?
Was it unavailable or an error?
Did we retry it?
Do we have its archived payload?
Did it load?
```

The current handoff says the MLB API item ledger isn't being populated correctly.

Fix that before adding ingestion sophistication.

Once it works, it becomes the foundation for extremely good error diagnosis.

An AI agent could eventually ask:

```text
mlb doctor --json
```

see:

```text
mlb_api.analytics coverage missing 13 games
```

then query:

```text
meta.ingestion_item
```

and immediately say:

```text
11 source-unavailable
1 parse failure
1 HTTP timeout exhausted retries
```

That is what “just works” should mean.

---

# The workflow/orchestration design is mostly reasonable

I do not think you need Airflow.

I do not think you need Dagster.

I do not think Kubernetes belongs anywhere near this workflow right now.

You have:

```text
cron
flock
Postgres advisory locks
child-process isolation
retry policy
run ledger
step duration
health checks
```

That is enough for one-node operation.

`mlb nightly` was a good move because it gives the workflow a first-class supervisor rather than hiding logic in shell.

I would continue migrating intelligence **into the CLI**, leaving shell scripts thin.

Eventually:

```text
cron → mlb nightly
```

should be all that matters.

---

# One portability issue remains

Your public product is supposed to be reusable by strangers.

A Linux-only combination of:

```text
cron
flock
system binaries
```

is less friendly to Windows/macOS researchers.

This does not mean replacing your scheduler.

Instead support generated installation recipes:

```text
mlb schedule install --systemd
mlb schedule print --cron
```

and document Windows/macOS alternatives.

More importantly, users who only consume the published research dataset should not need the producer stack at all.

Which leads to one of the best architectural decisions you've already made.

---

# You should explicitly think of this as a producer and a consumer product

The **producer** is heavy:

```text
PostgreSQL
connectors
Retrosheet
Statcast
MLB API
SQLMesh
full transforms
market capture
```

The **consumer** should be extremely light:

```bash
pip install mlb-research
```

then:

```python
import mlb_research
```

and query:

```text
DuckDB
Parquet
feature utilities
backtest harness
```

A researcher should not need:

```text
Postgres
psycopg
XGBoost
Chadwick binaries
Kalshi credentials
```

just to analyze batting data.

Your `packages/mlb-research` + Parquet/Hugging Face + DuckDB direction is exactly right.

DuckDB's direct Parquet query path and lightweight Python API are a very strong fit for that consumer product. [DuckDB](https://duckdb.org/docs/stable/clients/python/overview?utm_source=chatgpt.com)

---

# `retrosheetpy` may be one of the project's most valuable standalone contributions

This deserves special mention.

You previously wanted a pip-installable replacement/port of Chadwick so users could avoid installing native tooling.

You now have:

```text
packages/retrosheetpy
```

and differential tests against a pinned Chadwick development commit.

That is exactly how I would attempt such a port.

Not:

> It seems right.

But:

```text
same source input
Chadwick output
Python output
byte/field parity
```

If you can achieve comprehensive parity, I would eventually make:

```text
retrosheetpy
```

its own installable package with a narrow, stable API.

The MLB project can consume it.

Other baseball researchers can consume it.

And Chadwick can optionally remain a reference/backend.

That is genuine ecosystem value beyond your prediction project.

---

# The package import graph still needs decoupling

Open issue #111 is important.

`mlb_baseball.model.__init__` eagerly importing psycopg and dozens of model modules is the opposite of how a reusable research library should behave.

A user should be able to do:

```python
from mlb_research.markov import ...
```

without initializing:

```text
database code
market connectors
XGBoost
neural modules
Postgres
```

This should eventually lead to extras along the lines of:

```text
mlb-research
mlb-baseball[builder]
mlb-baseball[markets]
mlb-baseball[ml]
mlb-baseball[gpu]
```

not necessarily those exact package names, but that dependency topology.

This matters a lot for adoption.

---

# Your testing approach is excellent

The rule:

> mock the network, not PostgreSQL

has produced a much stronger database project than a mock-heavy test suite would.

You currently have:

```text
unit tests
real Postgres integration tests
pgTAP
SQL lint
SQL ownership lint
mypy
ruff
docs build
metric catalog gate
Retrosheet-vs-Chadwick differential tests
gitleaks
CodeQL
Semgrep
SBOM / scorecard workflows
```

That is very solid.

I especially like the external tie-out philosophy.

The key distinction is:

```text
self-consistency test:
my code gives the number my own formula predicts

independent validation:
my code reproduces an independently published result
```

Your metric catalog now understands that distinction.

Keep pushing it.

I care more about this than an arbitrary “100% code coverage” target.

---

# The pipeline needs a tiny reference-database acceptance test

You have many excellent focused tests.

I would add one intentionally small end-to-end research database fixture.

Something like:

```text
2 seasons
a few teams
trades
doubleheaders
postseason
one weird baserunning event
one player substitution
one starter change
one market
one missing field
```

Run:

```text
migrate
→ ingest fixture
→ conform
→ gold
→ build features
→ readiness
→ baseline model
→ export
```

and compare the resulting canonical tables/artifacts against versioned expected results.

That gives you a project-level invariant:

> Can the whole machine still build a coherent baseball research database?

Individual module tests cannot completely answer that.

---

# Gold should become contract-driven

I think this would be the most useful metadata addition after stable IDs.

For every important published relation, define a machine-readable contract describing:

```text
relation
description
grain
business key
writer
inputs
build strategy
coverage
freshness expectation
source rights
null policy
PIT classification
formula/version
validation
public eligibility
```

For example conceptually:

```yaml
relation: gold.batting_game
grain:
  - game_id
  - player_id
  - team_id

owner: sqlmesh:gold.batting_game

coverage:
  start: 1910

point_in_time: false

public_safe: true

business_key:
  - game_id
  - player_id
  - team_id

quality:
  source_tieout: retrosheet
  required_audits:
    - unique_grain
    - nonnegative_counts
    - source_game_coverage
```

But do **not** create another pile of YAML that duplicates five docs.

Use it to generate parts of:

```text
TABLE_CONTRACTS
data dictionary
doctor/audit registration
docs
export eligibility
```

Then it earns its existence.

---

# Gold should have exactly one writer per relation

I would enforce this in CI.

You are already close to this doctrine.

Turn it into a hard invariant.

A machine should be able to answer:

```text
gold.team_woba
→ owner = transforms/models/team_woba.sql
```

and nothing else is allowed to mutate it.

If Python orchestration runs SQLMesh, fine.

If Python selects parameters and invokes one named SQL resource, fine during migration.

But there must be one canonical computational implementation.

This is especially important because you currently have formula risks such as:

```text
wOBA in Python + SQLMesh
FIP logic in multiple modules
pitch-discipline logic in production SQL + stale SQLMesh copy
```

The October 5 Retrosheet pitch fix is proof of the danger: the production SQL was corrected, but the unpromoted SQLMesh copy still contains the old wrong logic.

That cannot happen after SQLMesh promotion.

Canonical ownership fixes it.

---

# The wOBA issue should be one of your first metric cleanups

Your metric catalog itself documents the problem beautifully.

Production currently uses a fixed set of wOBA weights across eras.

But you now possess:

```text
gold.fangraphs_guts
```

with season-specific constants.

So the project is knowingly doing:

```text
1915
1975
2000
2025
```

with the same weights even though the run environment differs.

I would fix this before claiming a polished all-history sabermetric surface.

A canonical wOBA implementation should resolve:

```text
season
→ season's weights
```

and should have a documented fallback/coverage rule.

Then every downstream use—team rolling wOBA, wRC+, player metrics—should use the same owner.

This is exactly the kind of formula SQLMesh should own.

---

# Now to the ML architecture

The database should not be designed around one model.

It should be designed around **prediction questions**.

Today you already have:

```text
home_win
run_differential
```

in the experiment/target concepts.

Expand that idea.

Every model target should have a versioned contract.

For example:

```text
target: game.home_win
grain: game
cutoff: scheduled_first_pitch
label: home_score > away_score
eligibility: regular season
type: binary
```

Or your player example:

```text
target: player.hits_exactly_3
grain: player-game
cutoff: prediction timestamp
label: H == 3
```

But your specific “3-for-3” example is even more precise:

```text
H = 3
AND
AB = 3
```

which is not the same thing as:

```text
at least 3 hits
```

or:

```text
3 hits in 4 AB
```

Taking Chipper Jones simply as the hypothetical player in your example, the research system should be able to ask exactly that sort of event-probability question.

---

# Player props should probably be generative rather than one giant classifier

For a future player event such as:

> exactly 3 hits in exactly 3 official at-bats

I would eventually model the underlying process.

Something like:

```text
P(player starts)
       ×
P(lineup position)
       ×
P(number of PA)
       ×
P(AB | PA)
       ×
P(each PA outcome | context)
```

Context can include:

```text
batter talent
handedness
starter
starter arsenal
starter quality
bullpen
platoon
park
weather
lineup strength
umpire
recent workload
defense
```

Then simulate the game.

That gives you:

```text
P(H = 3 AND AB = 3)
```

naturally.

It also gives you:

```text
P(H >= 2)
P(HR >= 1)
P(RBI >= 2)
P(team wins)
P(total > 8.5)
P(player HR AND team wins)
```

from the same underlying simulation.

That is far more coherent for parlays than multiplying separately trained probabilities.

---

# Your Markov/simulation direction is therefore strategically important

Issue #88 is pointed in the right direction.

A player/team-aware PA model feeding a state simulation can eventually produce joint probabilities directly.

For example:

```text
P(Yankees win AND Judge HR)
```

should come from the same simulated worlds.

Not:

```text
P(Yankees win)
×
P(Judge HR)
×
guessed correlation adjustment
```

That distinction will matter enormously when you move into correlated parlays.

Your project already recognizes this.

I agree with it.

---

# I would build a target registry before building many more models

This is one of my strongest ML recommendations.

The model should not own the definition of what it predicts.

The research platform should.

For every target:

```text
target name
target version
population
observation cutoff
prediction horizon
label calculation
void/censored conditions
evaluation metrics
market equivalents
```

Then:

```text
Elo
GBM
CatBoost
Bayesian model
Markov
neural model
```

can compete on exactly the same target.

That eliminates a huge amount of accidental apples-to-oranges comparison.

---

# Your point-in-time feature architecture is a major strength

This may ultimately distinguish the project more than having another xwOBA implementation.

Lots of baseball projects contain stats.

Far fewer rigorously answer:

> What could this model actually have known at 5:00 PM before a 7:05 PM game?

Your DuckDB feature store, explicit availability/cutoff concepts, leakage checks, and chronological folds are exactly where your research credibility comes from.

I would make `available_at` or an equivalent knowledge-time rule mandatory for every model feature family.

Not just:

```text
event happened at T
```

but:

```text
value became knowable at T
```

Those are not always the same.

For example:

```text
final-season WAR
scorer corrections
post-game weather
published leaderboard values
revised data
probable starter
confirmed lineup
```

all have different information availability.

That is the difference between a statistical database and a legitimate forecasting database.

---

# Feature readiness should become target-specific

A feature can be valid for one target and leakage for another.

For example:

```text
game final score
```

is perfectly good for historical descriptive research.

It is impossible as a pregame game-win feature.

So your current `readiness.py` approach is conceptually excellent.

Eventually I would want:

```bash
mlb readiness \
  --target game.home_win \
  --as-of 2026-07-01T17:00:00Z
```

to produce:

```text
feature availability
coverage
unexplained NULLs
future leakage
source rights
data version
target eligibility
backbone tie-out
```

That becomes a powerful research gate.

---

# Modeling evaluation should have two completely separate questions

Never combine these.

First:

> Is the model a good probabilistic forecaster?

Measure:

```text
log loss
Brier
calibration
calibration slope/intercept
reliability curves
discrimination
stability by season
```

Then:

> Is it economically useful relative to a market?

Measure:

```text
model probability
market executable probability
spread
fees
slippage
liquidity
expected value
realistic fill
closing-line comparison
```

A model can be statistically good but economically useless.

A mediocre model might still identify a narrow badly-priced market.

Those should remain separate analyses.

---

# This leads to the biggest missing piece for your commercial objective: market normalization

Your market layer is not yet good enough for the long-term goal.

`core.market` currently collapses a market/game/source down to essentially one useful pregame observation.

Issue #113 already exposes the consequence:

```text
open
24h
6h
close
```

cannot all be evaluated honestly when you only retain one canonical pregame value in `core.market`.

The new 15-minute raw snapshot capture is a very good correction.

Now finish the data model.

I would eventually replace the conceptual role of `core.market` with several normalized objects:

```text
market_contract
market_game_map
market_quote
market_settlement
```

You do not necessarily need those exact names.

But you need those concepts.

---

# A market contract is not a quote

A contract says:

```text
provider
provider_market_id
event
question
outcome
side
line
open_time
close_time
settlement rule
status
```

A quote says:

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
```

A settlement says:

```text
final result
settlement price
settled_at
resolution source
void reason
```

That separation matters.

Kalshi's current API representation exposes distinct yes/no bid and ask prices, sizes, open interest, liquidity, timestamps and other market state fields rather than just one probability number. [API Documentation](https://docs.kalshi.com/api-reference/events/get-multivariate-events?utm_source=chatgpt.com)

That is what your normalized schema should preserve.

---

# Do not compare your model to a single “market probability”

Suppose the model says:

```text
P(win) = 0.58
```

and the market screen appears to say:

```text
0.54
```

That does not automatically mean:

```text
edge = +4%
```

What can you actually buy?

Maybe:

```text
bid = .53
ask = .56
```

Then your executable price is closer to `.56`.

And after:

```text
fees
spread
slippage
size
```

your supposed edge may be gone.

Polymarket itself describes market prices as probability-like prices formed by supply and demand; that's useful conceptually, but a real trading strategy still has to model the price at which your order can execute. [Polymarket Documentation](https://docs.polymarket.com/faq?utm_source=chatgpt.com)

That distinction should be first-class in your research system.

---

# Also: mispricing and arbitrage are different things

This is important language for the eventual paid research product.

If your model estimates:

```text
true probability = 60%
market ask = 52%
```

you believe you found **positive expected value / mispricing**.

That is not necessarily arbitrage.

True arbitrage means you can construct positions whose combined outcomes lock in profit regardless of result, after fees/execution constraints.

Your future site should distinguish:

```text
model edge
value opportunity
cross-market discrepancy
true arbitrage
```

That will make the research much more credible.

---

# The market mapping should eventually be target-driven

This is where your target registry becomes incredibly useful.

Instead of:

```text
Kalshi market
→ some game
```

you want:

```text
provider contract
     │
     ▼
canonical target + settlement semantics
```

For example:

```text
KALSHI-XYZ
→ game.home_win:v1
```

or:

```text
Polymarket ABC
→ game.total_runs_gt:8.5:v1
```

or:

```text
DraftKings player prop
→ player.hits_gte:2:v1
```

Then model predictions and market quotes speak the same semantic language.

This is how you eventually support:

```text
Kalshi
Polymarket
The Odds API
DraftKings
FanDuel
...
```

without hardcoding separate research logic for every provider.

---

# Be extremely careful with market settlement semantics

Your model target has to match the actual contract.

Questions that matter:

```text
Does postponement void it?
Does extra innings count?
Does player need to start?
What if player has zero PA?
What if lineup changes?
Does an abandoned game settle?
What official source resolves the event?
```

A technically accurate baseball probability is useless if it predicts a subtly different event from the contract you are pricing.

So contract normalization should include resolution semantics, not just text matching.

---

# The current 15-minute odds capture is a good starting cadence

You measured current snapshot volumes before selecting the cadence.

That is exactly what you should do.

Do not optimize it further yet.

Let the week of real data answer:

```text
How fast do prices meaningfully change?
How many duplicate observations?
How much storage?
How often do we miss meaningful movement?
```

Then perhaps switch from:

```text
capture every quote
```

to:

```text
append only when price/size/status changes
```

if volume becomes wasteful.

---

# You need a generalized run lineage record

You already have good lineage ingredients scattered through:

```text
meta.ingestion_run
meta.ingestion_item
meta.model
meta.experiment
snapshots
feature versions
git SHA
metric permalinks
```

Eventually every published research result should be reconstructable from something resembling:

```text
research_run_id

git_commit
schema_version
data_snapshot
source_artifact_hashes
feature_set_version
feature_artifact_hash
target_version
model_version
model_artifact_hash
hyperparameters
training_cutoff
evaluation_period
environment/lock hash
generated_at
```

Then an article can say:

```text
Research run: 8e512...
```

and you can reproduce it.

That's enormously valuable if you eventually charge for research.

---

# Model artifacts should always be content-addressed

Issues #108 and #120 show why.

Never let model identity mean:

```text
models/gbm-v2.json
```

alone.

Prefer:

```text
models/artifacts/
    sha256-or-run-id/
        model.json
        metadata.json
```

Then a human-friendly alias can point to:

```text
champion
candidate
```

But the immutable artifact remains immutable.

And all writes should be:

```text
temporary file
fsync if appropriate
atomic os.replace()
```

Never write directly over a model artifact.

---

# “Champion” should be a promotion decision, not simply the latest model

The existing GBM behavior is actually philosophically correct in one respect:

If it doesn't beat the baselines, it should not become champion.

Keep that.

The baseline ladder should look something like:

```text
market naïve
historical home-rate
Log5
Elo
regularized logistic
Poisson / run model
CatBoost / XGBoost
Markov
Bayesian player model
ensemble
```

A more complicated model earns promotion.

Complexity alone is not progress.

---

# I would not prioritize neural networks

Not yet.

For structured baseball data of your current scale, I would rather have:

```text
clean targets
perfect PIT features
calibrated logistic model
CatBoost
hierarchical Bayesian components
well-constructed simulation
```

than a sophisticated neural network with uncertain input semantics.

Your major risk is still data semantics, not insufficient model capacity.

---

# The public dataset should remain more conservative than the internal Engine

This separation is correct even if we ignore the existing constitution and reason from scratch.

Your public research package should be:

```text
reproducible
citable
documented
portable
legally redistributable
honest about limitations
```

Your private/internal Engine can contain:

```text
tuned hyperparameters
experimental features
market execution research
novel composites
subscriber rankings
model weights
current edges
```

That split simultaneously helps open-source credibility and preserves the possibility of a commercial product.

---

# Source rights should become mechanically enforced

You already distinguish things like:

```text
public_safe
local_research
```

Excellent.

Don't leave that only in documentation.

The exporter should traverse declared lineage.

If:

```text
gold.foo
```

depends on a source that cannot be redistributed, then:

```text
mlb export --preset public
```

should refuse it automatically.

Not:

> We remembered not to include it.

But:

```text
ERROR:
gold.foo depends on raw.provider_x
rights policy = local_research
```

That's how you avoid future licensing mistakes.

---

# The open Negro League issue should not be handled as an incidental filter

Issue #258 matters conceptually.

A research database spanning baseball history needs explicit competition/game classification.

You shouldn't depend on:

```text
league IS NOT NULL
```

or arbitrary year filters to distinguish populations.

The game dimension should make it possible to ask:

```text
MLB regular season
MLB postseason
Negro Leagues
All-Star
exhibition
spring training
other
```

explicitly.

Then target definitions specify:

```text
eligible_competition = MLB
eligible_game_type = regular
```

This is important both academically and for ML.

---

# Your public “easy install” goal needs bootstrap profiles

A full everything bootstrap is a large job.

A new user shouldn't have to ingest every Statcast pitch and market snapshot to answer:

> What was Ted Williams' OBP?

I would eventually provide conceptual profiles such as:

```text
research-core
research-full
statcast
markets
modeling
everything
```

For example:

```bash
mlb bootstrap --preset research-core
```

might load enough for:

```text
games
players
teams
batting/pitching
standard metrics
```

while:

```bash
mlb bootstrap --preset modeling
```

adds:

```text
Statcast
features
advanced sources
```

This materially improves adoption.

Your existing `preflight` command is a great place to tell users:

```text
estimated disk
required dependencies
enabled sources
missing credentials
next commands
```

---

# The docs architecture is strong

The combination of:

```text
MkDocs
data dictionary
grain ladder
formula citations
honest limitations
notebooks
generated metric catalog
```

is exactly what a research platform needs.

I would make one principle non-negotiable:

> If metadata can be generated from the actual contract/code, don't maintain a second prose copy manually.

The amount of documentation in this repo is now large enough that doc drift itself is a risk.

Generate:

```text
relation docs
metric docs
source coverage
feature catalog
CLI reference
```

where feasible.

Keep ADRs and research reasoning hand-written.

---

# AI agents and skills should come later—but they can become extremely powerful

I absolutely see the end state you're describing.

A user could tell Claude:

> Build me a model estimating the probability that Aaron Judge gets at least two hits tomorrow and compare it to any corresponding market.

And the agent could perform:

```text
inspect target
check data readiness
select admissible features
build PIT artifact
train chronological model
calibrate
backtest
retrieve market contract
compare executable quotes
write research report
```

But the key insight is:

**The skill should not contain the baseball logic.**

The skill should teach the agent how to operate the CLI and interpret structured outputs.

That way humans and agents use the same platform.

---

# The eventual skills I would build

Once the CLI contracts stabilize, I would build skills around workflows such as:

1. `mlb-diagnose` — interpret structured doctor/audit failures, run only safe diagnostic commands, point to root cause and remediation.
2. `mlb-add-source` — source research → connector contract → fixtures → ingestion → health checks → lineage.
3. `mlb-add-metric` — citation → grain → formula → SQLMesh → audits → tie-out → catalog → docs.
4. `mlb-add-target` — define event semantics, cutoff, labels, eligibility, settlement mapping and evaluation.
5. `mlb-build-feature-set` — inspect available features, enforce PIT rules, run readiness, build immutable DuckDB artifact.
6. `mlb-run-research` — train/baseline/backtest/calibrate/compare and create a fully reproducible run.
7. `mlb-market-study` — normalize a market, find matching model target, retrieve the correct historical quote cutoff and calculate executable EV.
8. `mlb-publish-research` — turn an immutable research run into tables/charts/Markdown/web content with citations.

These skills should operate machine-readable commands.

That's why fixing `doctor --json`, readiness JSON, run IDs, and target contracts now pays off later.

---

# What I would do next, in exact order

This is the sequence I would use rather than starting another broad refactor:

1. **Finish the current `pipeline-recovery` change.** Resolve the remaining real doctor defects at their source: catcher framing should be withheld/rebuilt rather than bounds widened; repair the MLB analytics item ledger; fix the stale feature artifact UX; correct prediction-count semantics; fix false backup awareness using the verified host backup; finish odds capture/backfill/cron and classify every remaining failure. Goal: a healthy normal installation produces an actually trustworthy doctor result.

2. **Complete stable IDs + incremental conform.** Incorporate the pipeline-recovery corrections: content-aware fingerprints, transformation versioning, no delete/reinsert of `core.game`, full-column equivalence checks, staging/atomic publication, and incremental/full parity. This is the highest-value database architecture change.

3. **Create the canonical transformation ownership gate.** Every mutable derived relation gets exactly one registered writer. CI should detect duplicate writers. Freeze new writes to `gold.game_feature`.

4. **Start the real SQLMesh cutover with two or three easy models.** I would use well-understood relations such as park factor and team wOBA—but fix era-specific wOBA constants first. Add proper SQLMesh tests and blocking audits, shadow-run, tie out, promote, delete the old writer. Then repeat. SQLMesh remains outside raw/core identity.

5. **Establish the trusted-metric gate.** Keep the current catalog, add asset/admission semantics, mark invalid catcher framing disabled/withheld, and prevent experimental/AI-generated unvalidated metrics from silently becoming production model features. Do not resurrect the 101 deleted Gemini metrics.

6. **Strengthen the canonical event spine.** Design—carefully, as its own proposal—the typed event/PA relationship needed to eliminate repeated direct interpretation of `raw.retrosheet_event`. Decide whether that means enriching `core.play` plus adding `core.event`, rather than forcing every sabermetric SQL model to understand Retrosheet quirks independently.

7. **Finish the public research backbone and source rollover system.** Add automated current-year MLB → Retrosheet season reconciliation, resolve box-only historical games, explicitly classify Negro League/game populations, and make public export eligibility lineage-driven.

8. **Normalize market history.** Separate market identity/contracts from timestamped observations and settlement. Preserve bid/ask/size/liquidity. Map contracts onto canonical targets. Once this exists, `open`, `24h`, `6h`, and `close` evaluations become truthful instead of aliases of the same quote.

9. **Formalize the target registry.** Expand beyond `home_win` and `run_differential`. Targets own labels, eligibility, cutoff, horizon, void/censoring semantics, metrics and market mappings.

10. **Then build the model ladder.** Start boring: Elo/log5 → regularized logistic → runs models → CatBoost/XGBoost → player hierarchical/PA models → Markov/Monte Carlo. Require chronological evaluation and calibration at every promotion. Do not promote on accuracy alone.

11. **Turn research runs into immutable artifacts.** Every prediction or published result should point to the input snapshot, feature set, target, code commit, model artifact and evaluation period. Fix remaining model-artifact atomicity/path issues.

12. **Only after these contracts stabilize, build the AI skills and subscriber-facing research workflow.** At that point the AI doesn't need to improvise database behavior; it simply knows how to drive a deterministic research machine.

---

# Where I think this can end up

I don't think the best version of this project is merely:

> a baseball database with a bunch of advanced stats.

That is crowded territory.

The more compelling product is:

> **A reproducible baseball forecasting research platform where every number is traceable from raw event → canonical fact → validated statistic → point-in-time feature → model → calibrated prediction → timestamped market price → research result.**

That is meaningfully different.

Pybaseball is excellent for accessing baseball data.

Baseball Reference/FanGraphs/Savant are excellent statistical resources.

Baseball.computer is a useful research/database reference.

Odds sites expose markets.

Your opportunity is to connect those worlds while preserving provenance and time.

The chain is the product:

```text
SOURCE
  ↓
RAW EVIDENCE
  ↓
CANONICAL BASEBALL FACTS
  ↓
VALIDATED STATISTICS
  ↓
POINT-IN-TIME FEATURES
  ↓
TARGET
  ↓
MODEL
  ↓
CALIBRATION
  ↓
PREDICTION
  ↓
MARKET QUOTE AT SAME TIME
  ↓
EDGE / EV / ARBITRAGE ANALYSIS
  ↓
REPRODUCIBLE RESEARCH
```

That is what I would optimize the repository around.

And importantly, **you do not need to tear down what you have to get there**. The current project has already built most of the hard primitives. What it needs now is a period of ruthless convergence: stable identity, single writers, trusted metrics, atomic builds, normalized market history, and machine-readable contracts.

Once those are established, adding models becomes fun again instead of dangerous.

The next concrete move I would make in the repo is **finish `pipeline-recovery`, then execute `stable-ids-incremental-conform`, and treat those two as the gate before doing further metric/model expansion**. After that, I would make the gold/SQLMesh consolidation the next architectural program. [SQLMesh](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/?utm_source=chatgpt.com)Yes. I reviewed the current `main` branch of `cbwinslow/mlb-baseball` at commit `93402ee` (October 5, 2026), including the architecture/constitution, current handoff and recovery work, raw/core/gold contracts, migrations, connectors, SQL resources, SQLMesh project, metric catalog and its Gemini-generated history, feature store, modeling code, market ingestion, health/audit/readiness systems, CI, tests, open issues, and the stable-ID/incremental-conform design.

My overall conclusion is:

**Do not rewrite this project. Do not switch databases. Do not add another orchestration framework. Do not start adding another hundred sabermetric formulas.**

The project has crossed the point where the main problem is lack of capability. The main problem is now **convergence**: making every important concept have one authoritative representation, one writer, one contract, one validation path, and one clear failure mode.

I think you are much closer to the research platform you described than it probably feels when `mlb doctor` is throwing dozens of failures.

# Overall verdict

Architecturally, I would put the project roughly here:

| Area | Current state | My assessment |
|---|---|---|
| Source ingestion | Strong | One of the better parts of the project |
| Raw preservation/provenance | Strong | Keep the general approach |
| Identity/conformance | Good design, problematic rebuild mechanics | **Highest database priority** |
| Historical baseball backbone | Strong and improving | Real research value already exists |
| Gold statistics | Valuable but fragmented | Needs canonical ownership |
| SQLMesh | Correct choice, incompletely adopted | Finish the migration deliberately |
| DuckDB feature store | Strong direction | Keep it |
| Point-in-time/leakage controls | Strong | Major differentiator |
| Metric catalog | Excellent concept | Needs a stricter trust/admission layer |
| Gemini metric batch | Correctly triaged | Do **not** resurrect it |
| `mlb doctor` | Excellent idea, overgrown implementation | Redesign internals, preserve UX |
| `mlb audit` | Good separation | Keep and expand |
| Model harness | Promising | Too much experimental code mixed together |
| Market data | Strategically important but under-normalized | **Major next data-model project** |
| Experiment reproducibility | Good foundation | Needs complete artifact lineage |
| Tests/CI | Strong | Better than most projects at this stage |
| Packaging/reusability | Very promising | Finish dependency separation |
| Agent automation | Premature for deep automation | Build after CLI/contracts stabilize |
| Commercial research readiness | Not yet | Database can get there before models do |

The biggest thing I want to emphasize is that you now have a **real data-engineering project**, not a pile of scripts. You have about 109 SQL migrations, 19 connectors, 136 named SQL resources, 18 SQLMesh models, around 50 surviving metric manifests, 62 modeling modules, and 229 unit/integration test modules. You also have real production lessons encoded into ADRs and tests.

That scale changes what “improvement” means.

From now on, **deleting duplication and establishing authority is more valuable than adding features**.

---

# The architecture I would ultimately aim for

I would make the conceptual architecture extremely simple:

```text
UPSTREAM SOURCES
      │
      ▼
┌─────────────┐
│     raw     │  Source-faithful evidence
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    core     │  Canonical baseball facts + identity
└──────┬──────┘
       │
       ├──────────────────────┐
       ▼                      ▼
┌─────────────┐       ┌───────────────┐
│    gold     │       │ market facts  │
│ statistics  │       │ + quote time  │
└──────┬──────┘       └───────┬───────┘
       │                       │
       └───────────┬───────────┘
                   ▼
            ┌─────────────┐
            │ DuckDB feat │
            │ point-in-   │
            │ time data   │
            └──────┬──────┘
                   │
                   ▼
          ┌──────────────────┐
          │ Models / Sim     │
          │ Python           │
          └────────┬─────────┘
                   │
                   ▼
          ┌──────────────────┐
          │ Predictions      │
          │ evaluations      │
          │ market research  │
          └────────┬─────────┘
                   │
                   ▼
          ┌──────────────────┐
          │ publish / serve  │
          │ research / web   │
          └──────────────────┘
```

And I would attach one governing rule to every layer:

**Raw preserves evidence. Core establishes truth. Gold calculates descriptive baseball knowledge. Feat answers “what was knowable then?” Python estimates uncertain future outcomes. Market data measures what someone could actually trade. Serve publishes results.**

That is the architecture I would optimize everything around.

---

# The database is fundamentally pointed in the right direction

PostgreSQL remains the right system of record.

I would **not move this to ClickHouse**. I would not replace PostgreSQL with DuckDB. And I would definitely not make SQLMesh responsible for identity reconciliation.

Your workload consists of identity resolution, foreign keys, source reconciliation, lineage, mutable ingestion state, historical facts, data-quality constraints, and moderately large analytical relations. PostgreSQL is very good at this.

DuckDB is also being used in exactly the place where it makes sense: portable analytical artifacts and model-ready point-in-time feature data. DuckDB can directly and efficiently query Parquet with projection/filter pushdown, which is particularly attractive for the public/research distribution side of this project. [DuckDB](https://duckdb.org/docs/current/guides/file_formats/query_parquet?utm_source=chatgpt.com)

So I strongly endorse:

```text
PostgreSQL = authoritative producer database
DuckDB/Parquet = portable analytical/research surface
Python = modeling + simulation
SQLMesh = deterministic transformation management
```

That combination is excellent.

---

# The single biggest database defect is unstable identity

This should be your highest architectural priority after the current pipeline-recovery defects.

The existing nightly `conform` behavior truncates and reconstructs a large chunk of `core`, which reissues IDs. That forces downstream relations to be rebuilt because a `core.game.id`, `core.player.id`, etc. isn't really an enduring identity.

The project itself has now identified this correctly in `stable-ids-incremental-conform`.

This is more important than performance.

Even if a full rebuild took five minutes, I would still tell you to change it.

An internal ID should mean:

> This entity got this ID once, and this ID remains its ID indefinitely.

A research paper, cached artifact, feature snapshot, model prediction, exported dataset, market match, or external consumer should never have to wonder whether yesterday's `game_id=12345` refers to tomorrow's `game_id=12345`.

The stable-ID proposal's general direction is correct:

```text
core.team
core.player
core.venue
core.game
```

should become persistent key maps themselves.

Incoming source rows should be **upserted**, not reconstructed from scratch.

Old rows that disappear from a provider should not automatically be deleted.

Conflicting identifiers should be surfaced.

Past seasons should be rebuilt because their **inputs changed**, not because today's calendar date changed.

This unlocks an enormous amount of simplification later.

It allows stable FKs, incremental gold builds, stable model artifacts, reliable caches, smaller nightly workloads, and meaningful historical lineage.

This is the change I would call the **database's architectural graduation point**.

---

# One modification I would make to the stable-ID design

The original fingerprint design was:

> row count + latest `_loaded_at`

I agree with the later pipeline-recovery review that this is insufficient.

Imagine:

```text
rows before = 1,000,000
rows after  = 1,000,000
_loaded_at unchanged
```

but somebody corrected one source value.

A row-count fingerprint misses it.

A trustworthy build signature should incorporate something like:

```text
source/version
season
row_count
content checksum
source artifact checksum
transform code version
reference-data version
schema version
```

You don't necessarily need to SHA every 50 GB table nightly.

You already download/archive source artifacts. Prefer hashing the immutable source artifact when available, then combine that with transformation version and relevant reference versions.

Conceptually:

```text
input_fingerprint =
    hash(
        source_artifact_sha256,
        transform_git_sha,
        schema_version,
        reference_versions
    )
```

Then rebuild only the partition whose effective fingerprint changed.

That gives you actual reproducibility.

---

# I would also make all big publishes atomic

You found the ugly consequence already: the current relationship between conform and report can leave downstream relations empty or unavailable if one stage dies.

The corrected pattern should universally be:

```text
build
   ↓
staging
   ↓
validate
   ↓
atomic publish
   ↓
analyze
```

not:

```text
TRUNCATE production
   ↓
hope the rebuild succeeds
```

For partitioned facts:

```text
build new season partition
validate new partition
short transaction / partition swap
ANALYZE
```

For ordinary tables:

```text
build shadow/staging relation
validate
short transactional replacement/upsert
```

For SQLMesh-controlled gold relations, this is one of the reasons SQLMesh becomes useful. SQLMesh plans can evaluate modified models and their blocking audits before promotion into the production environment; its incremental model types also directly support time-range, unique-key, and partition-oriented transformations. [SQLMesh](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/?utm_source=chatgpt.com)

That is a much better match for the gold layer than home-grown `TRUNCATE → INSERT`.

---

# Raw is mostly designed correctly

I like your philosophy here.

Source-faithful, append/scoped-replace where appropriate, minimally transformed, replayable, and tolerant of upstream schema changes is exactly what raw should be.

I would **not “clean up” raw by imposing a giant relational model on it**.

But your raw layer needs one thing strengthened: **schema-change observability**.

Allowing:

```text
ALTER TABLE ADD COLUMN
```

is useful because it means an upstream addition doesn't destroy ingestion.

But tolerance must not become invisibility.

Each connector should record a source schema fingerprint, for example:

```text
source
relation
observed_at
columns
required_columns
new_columns
missing_columns
inferred_types
artifact_hash
row_count
```

Then:

```text
new optional source column
→ INFO

expected column disappeared
→ ERROR

important field changed format
→ ERROR

new unused column
→ INFO

raw row count suddenly falls 97%
→ ERROR/WARN
```

`mlb source-check` is already moving toward this idea.

Expand that rather than adopting another data-quality framework.

---

# There is one deeper problem between raw and core

This may be the most important structural observation beyond stable IDs.

Today several important gold calculations still have to reach back into `raw.retrosheet_event`.

Why?

Because `core.play` does not preserve all the semantic information required downstream.

Your own production investigations proved examples:

```text
bat_event_fl
ab_fl
sf_fl
sh_fl
event_cd
outs_ct
start_bases_cd
responsible batter/pitcher
pitch sequence
runner events
```

are important.

And the recent bugs prove why centralizing the interpretation matters:

- mid-plate-appearance substitutions;
- repeated pitch sequences on runner events;
- responsible batter vs current batter;
- obstruction-run accounting;
- baserunning events;
- first-pitch strike double counting;
- catcher framing accidentally parsing `event_tx`.

These aren't random bugs.

They are telling you something about the data model:

**Retrosheet's event semantics deserve a canonical typed fact representation.**

I would seriously consider eventually creating:

```text
core.event
```

at one Retrosheet event-record grain, containing typed canonical state such as:

```text
game_id
event_index
batter_id
responsible_batter_id
pitcher_id
responsible_pitcher_id

is_batter_event
is_at_bat
is_sac_fly
is_sac_hit

event_type
outs_before
bases_before
runs_on_event

pitch_sequence
runner_advance flags
...
```

Then separately retain:

```text
core.play / core.plate_appearance
```

for the completed plate-appearance fact.

And:

```text
core.pitch
```

remains the pitch/tracking fact.

That gives you a beautiful three-level event spine:

```text
game
  ├── event
  ├── plate appearance
  └── pitch
```

I would **not rush this into the current recovery change**, because it touches a foundational grain.

But I think this is where the database ultimately wants to go.

It would dramatically reduce the number of downstream modules that independently reinterpret Retrosheet semantics.

---

# Your current historical statistical backbone is valuable

The new grain ladder is one of the strongest pieces of this repository.

Having:

```text
gold.batting_game
gold.pitching_game

gold.batting_season
gold.pitching_season

gold.batting_team
gold.pitching_team

gold.batting_career
gold.pitching_career

gold.batting_postseason
gold.pitching_postseason
```

is exactly the sort of boring, reusable research infrastructure that academics and analysts actually need.

I also like that you have refused to fabricate ERA where earned runs are not honestly reconstructable.

That philosophy is important:

```text
missing because unknowable
```

is vastly better than:

```text
plausible-looking number
```

The project should become almost fanatical about preserving that principle.

---

# The current-year / historical-source split needs an explicit rollover workflow

You currently have a sensible source split:

```text
Retrosheet       → historical finalized seasons
MLB box scores   → current season
```

because Retrosheet naturally lags the live season.

But every winter you will eventually hit:

```text
MLB 2026 version
vs.
Retrosheet 2026 version
```

You need a first-class annual reconciliation process.

Something like:

```text
mlb reconcile season 2026
```

should compare the two source versions across:

```text
games
PA
AB
H
2B
3B
HR
BB
HBP
SO
runs
pitching outs
...
```

Then produce:

```text
MATCH
EXPLAINED DIFFERENCE
SOURCE CORRECTION
UNRESOLVED
```

Only after the gate passes should historical ownership move from:

```text
mlb_boxscore
```

to:

```text
retrosheet_event
```

for that season.

That gives you an extraordinarily valuable research property:

**a season's historical interpretation changes through an explicit, audited source transition rather than silently one morning.**

---

# Gold needs a much sharper meaning

Currently `gold` means too many things:

- descriptive baseball statistics;
- reporting tables;
- pregame features;
- model feature columns;
- predictions;
- market baselines;
- evaluation outputs;
- experiments.

That worked while the project grew organically.

It is becoming confusing now.

I would define gold narrowly:

> **Gold is deterministic, reproducible baseball knowledge derived from canonical facts.**

Examples:

```text
batting_game
batting_season
pitching_game
pitching_season
RE24
win expectancy
park factors
team rolling rates
platoon splits
pitch movement aggregates
```

But I would stop thinking of learned model predictions as gold.

Long-term I prefer something conceptually like:

```text
raw.*
core.*
gold.*
meta.*

feat.*       -- DuckDB artifact
pred.*       -- predictions/model outputs
serve.*      -- consumer views
```

You don't have to rename `gold.prediction` tomorrow. That would generate unnecessary migration work.

But semantically, keep the distinction in new design.

---

# `gold.game_feature` should be frozen rather than expanded

This is one of the project's most important cleanup opportunities.

`gold.game_feature` became a kitchen-sink relation.

Many modules mutate it:

```text
starter
offense
bullpen
park
war
framing
speed
OAA
pitch discipline
movement
command
platoon
interaction terms
...
```

That is how you end up with:

```text
one enormous table
many partially independent writers
rebuild ordering requirements
many health checks
null semantics depending on feature family
```

You already built the correct escape hatch:

```text
DuckDB feat.*
```

I would now declare:

**No new broad feature family gets added to `gold.game_feature` unless necessary for compatibility.**

Treat it as legacy/internal compatibility.

New model-ready feature families should go through the versioned PIT feature system.

Eventually:

```text
feat.game
feat.team_form
feat.player_form
feat.pitcher_form
feat.market
feat.lineup
...
```

can replace its modeling role.

This is a far cleaner design.

---

# SQLMesh: keep it, but finish the decision

This has been an ongoing question in our previous discussions.

My answer after reviewing the current repo is much firmer now:

**Yes, SQLMesh should become the authoritative engine for deterministic gold transformations.**

But:

**No, SQLMesh should not own raw ingestion or core identity reconciliation.**

That boundary is correct.

SQLMesh has native incremental model strategies, planning/versioning, tests, audits, backfills, and environment semantics that fit deterministic analytical transformations very well. [SQLMesh](https://sqlmesh.readthedocs.io/en/latest/reference/model_configuration/?utm_source=chatgpt.com)

Your desired split should become:

```text
NETWORK / PARSING / IDENTITY
Python

raw → core identity reconciliation
Python orchestration + named SQL

core → gold deterministic transformations
SQLMesh

point-in-time DuckDB feature artifacts
SQL

training / Bayesian fitting / XGBoost / simulation
Python

serving
SQL/views + application layer
```

The problem today is that SQLMesh is simultaneously:

```text
adopted
```

and:

```text
still mostly a shadow implementation
```

Issue #70 reflects this.

That cannot remain permanent.

---

# The SQLMesh promotion process should be boring

Every existing deterministic Python/SQL feature should migrate individually.

The lifecycle should be:

```text
legacy writer
      │
      ├── run
      │
      ▼
expected output

SQLMesh candidate
      │
      ├── run same source data
      ▼
candidate output

compare:
  grain
  row count
  keys
  NULLs
  every output field
  historical ranges
  PIT samples
  performance

         PASS
           │
           ▼
make SQLMesh canonical
           │
           ▼
DELETE OLD WRITER
```

Never:

```text
Python writes table
AND
SQLMesh writes table
```

for an indefinite period.

You already have this doctrine in pieces.

Now enforce it mechanically.

---

# SQLMesh's current audit coverage is too small

I counted 18 SQLMesh models but only a tiny native audit surface.

That is nowhere near enough if SQLMesh becomes authoritative.

Every production gold model should have at least its applicable versions of:

```text
grain uniqueness
required-key NOT NULL
accepted domains
reasonable cardinality
referential coverage
source coverage
season coverage
no impossible values
no fanout
PIT restrictions when appropriate
```

SQLMesh audits are specifically designed to validate real model output after execution, and blocking audits can stop downstream propagation when they return invalid rows. [SQLMesh](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/?utm_source=chatgpt.com)

Use that.

Your current `health_check()` logic contains a huge amount of business knowledge that could become model-local audits.

That is another way to shrink `doctor`.

---

# The Gemini metric library: the project already made the right first move

This was one of the things you specifically asked me to settle.

I read `mlb_baseball/metrics/TRIAGE_BACKLOG.md`.

The original AI batch was roughly 151 metric catalog entries, around 135 produced by the external AI effort.

The later triage deleted **101** of those entries and their associated dead implementations.

That was correct.

Some weren't merely buggy.

Some invented:

```text
acronyms
coefficients
thresholds
composite statistics
```

that had no actual sabermetric basis.

Do not attempt to “repair the batch.”

Do not bring it back.

Do not ask another model to regenerate everything.

That would recreate the exact problem you have spent weeks undoing.

---

# What should happen to the surviving metrics

The **catalog itself is excellent**.

Keep:

```text
mlb_baseball/metrics/*.yaml
meta.metric
generated documentation
citation
formula owner
data source
grain
implementation
status
visibility
test_ref
```

That is valuable infrastructure.

But distinguish:

```text
cataloged
```

from:

```text
trusted
```

For example, the current `team_woba` entry is refreshingly honest. It says the calculation uses fixed weights across all seasons even though you now have era-specific FanGraphs Guts constants available. Its tests are self-consistency tests, not independent external tie-outs, so the catalog marks it `published`, not `validated`.

That's precisely the right mentality.

The current catcher-framing entry is even more illustrative: it honestly says its 0.33 and 0.125 constants are project-derived and the implementation is `implemented-untested`.

And your October 5 investigation has now gone farther: the underlying implementation is genuinely invalid because it interprets play-description text as pitch information.

That metric should **not merely remain “untested.”**

Its current-season outputs should be withheld until rebuilt properly.

I agree with the current recovery recommendation:

```text
KEEP
prior-season Savant framing value

WITHHOLD
project-derived in-season CSAE/framing runs

until a defensible model exists
```

The attempted Statcast reproduction only reaching modest correlation with the published framing data is evidence that you cannot reasonably call the approximation equivalent.

That is exactly the kind of intellectual honesty that will make this project credible.

---

# I would add one more concept to the metric catalog

Today the catalog describes quality/status, but I would add explicit **admission/use**.

Something conceptually like:

```yaml
usage:
  public_stat: true
  research: true
  model_feature: false
  production_prediction: false
```

or a single tier:

```text
reference
validated
research
experimental
disabled
```

because these are different questions:

> Is this formula documented?

> Is it independently validated?

> Is it acceptable to publish?

> Is it safe to feed into a model?

> Is it experimental?

A clever experimental feature can be perfectly legitimate in research without being something you should publish as established sabermetrics.

Conversely, Baseball Savant's source-native value may be safe as a feature even if you cannot reproduce their proprietary internal formula.

Don't try to encode all those meanings into `status` alone.

---

# I would also stop calling everything a “metric”

The surviving catalog contains things such as:

```text
Elo
Monte Carlo simulations
drift monitoring
player prop projections
Markov win probability
Stuff+ style engines
```

Those aren't all the same category.

The existing `model/` directory has the same problem.

Issue #203 already recognizes it.

You don't need a giant refactor immediately, but introduce an asset kind:

```text
statistic
feature
baseline
model
simulation
diagnostic
market_tool
```

Then the catalog and `doctor` can behave intelligently.

For example:

```text
batting average
→ statistic

rolling 30-day K%
→ feature

Elo
→ baseline model

Monte Carlo season simulation
→ simulation

calibration drift
→ diagnostic
```

That single distinction will clean up a surprising amount of conceptual confusion.

---

# There is an immediate metric quality gate I would impose

Until the Gemini fallout is completely resolved:

> **No `implemented-untested` AI-generated metric can become a production model input merely because it produces numbers.**

Admission should require either:

```text
published formula
+ verified implementation
+ PIT-safe data lineage
+ realistic fixture/tie-out
```

or, for novel/project-derived features:

```text
explicitly experimental status
+ documented derivation
+ chronological evaluation
+ ablation result
+ no leakage
```

The computer does not care whether a feature has a made-up coefficient.

It will happily fit on it.

That makes bad experimental features more dangerous, not less.

---

# `mlb doctor` is a fantastic product idea

Keep the command.

In fact, I think it could become one of the things people love about the project.

A new researcher should be able to run:

```bash
mlb doctor
```

and have the system explain:

```text
what is wrong
why it is wrong
how confident we are
where it lives
what command diagnoses it
what command fixes it
whether it is safe to continue
```

That is a legitimately differentiating feature.

But the current implementation needs to be redesigned internally.

---

# `mlb doctor` is currently doing too much

Right now `doctor.py` manually imports and checks:

```text
connectors
conform
model
report
feat
experiment
selection
serve
simulate
props
season
portfolio
research
export
calibration
drift
backtest
ROS
stack
parlay
stuff
heatmap
neural
pipeline
visual
hedge
bullpen
arm slot
BABIP
VAA
NRFI
tunnel
API
shop
daemon
backup
...
```

with repeated blocks resembling:

```python
try:
    checks.extend(foo.health_check())
except Exception:
    ...
```

That is fragile.

Adding a subsystem doesn't automatically make it visible to doctor.

Deleting one can leave stale registration.

And today an experimental model can make the database appear “unhealthy.”

That is partly why you can get something like:

```text
353 / 370 checks passing
```

after a successful production night.

A genuinely healthy production warehouse should not look red because an optional GBM artifact hasn't been trained.

---

# Doctor should become registry-driven

The modules should register their checks rather than doctor knowing them all.

Conceptually:

```python
@health_check(
    id="market.polymarket.snapshot_freshness",
    scope="market",
    severity="error",
    requires=["database"],
    remediation="mlb odds-capture",
)
def check_polymarket_snapshot_freshness(ctx): ...
```

Then doctor asks the registry what exists.

Each result should have structured fields:

```json
{
  "id": "gold.catcher_framing.domain",
  "status": "FAIL",
  "severity": "ERROR",
  "scope": "research",
  "component": "catcher_framing",
  "summary": "framing values violate validated domain",
  "cause": "...",
  "evidence": "...",
  "remediation": "...",
  "docs": "...",
  "duration_ms": 83
}
```

This makes it usable by humans **and AI agents**.

---

# And doctor should have scopes

You already have much of the functionality distributed among `doctor`, `audit`, `readiness`, etc.

Don't collapse everything together.

I would make the UX behave roughly like:

```text
mlb doctor
installation + operational health

mlb doctor --data
raw/core/gold freshness

mlb audit
data-contract integrity

mlb readiness ...
ML feature/target admission

mlb doctor --deep
all of the above summarized
```

The normal `mlb doctor` should answer:

> Can this installation operate normally?

It should not fail because:

```text
an optional model isn't trained
a historical optional backfill wasn't requested
an experimental metric is disabled
```

Those should be:

```text
INFO
SKIPPED
NOT_CONFIGURED
EXPERIMENTAL
```

not red errors.

That change alone will make the system feel vastly more dependable.

---

# Your recent doctor investigations are actually evidence that the philosophy works

Look at what it recently uncovered:

```text
away_woba being overwritten
pitch-sequence double counting
BRef postseason leakage
stale DuckDB feature schema
false backup assumptions
catcher framing computation defect
prediction-count semantics
optional history wrongly treated as required
```

Those are meaningful bugs.

And importantly, your current recovery standard has become:

> trace the problem to the source; do not widen the health bound merely to silence the check.

That is the right standard.

I would preserve that principle permanently.

A good health check is not:

```text
value was -14
bound says -10
change bound to -20
```

A good health check asks first:

```text
Is -14 impossible?
Is our calculation wrong?
Is our assumption wrong?
Is the source meaning different?
```

The recent first-pitch-strike investigation is a perfect example.

---

# I would preserve the distinction among doctor, audit, and readiness

You already have the right pieces.

`doctor`:

> Is the system functioning?

`audit`:

> Is the database consistent with its declared contracts?

`readiness`:

> Is this particular feature artifact safe to use for this modeling purpose?

That is an excellent three-level design.

Do not build a fourth generic “validation framework.”

Make those three clearer.

---

# The open `meta.ingestion_item` problem is important

This is higher priority than it may seem.

Your run-level ledger is good:

```text
meta.ingestion_run
```

but item-level durability is what lets you answer:

```text
Which game failed?
Which endpoint?
Why?
Was it unavailable or an error?
Did we retry it?
Do we have its archived payload?
Did it load?
```

The current handoff says the MLB API item ledger isn't being populated correctly.

Fix that before adding ingestion sophistication.

Once it works, it becomes the foundation for extremely good error diagnosis.

An AI agent could eventually ask:

```text
mlb doctor --json
```

see:

```text
mlb_api.analytics coverage missing 13 games
```

then query:

```text
meta.ingestion_item
```

and immediately say:

```text
11 source-unavailable
1 parse failure
1 HTTP timeout exhausted retries
```

That is what “just works” should mean.

---

# The workflow/orchestration design is mostly reasonable

I do not think you need Airflow.

I do not think you need Dagster.

I do not think Kubernetes belongs anywhere near this workflow right now.

You have:

```text
cron
flock
Postgres advisory locks
child-process isolation
retry policy
run ledger
step duration
health checks
```

That is enough for one-node operation.

`mlb nightly` was a good move because it gives the workflow a first-class supervisor rather than hiding logic in shell.

I would continue migrating intelligence **into the CLI**, leaving shell scripts thin.

Eventually:

```text
cron → mlb nightly
```

should be all that matters.

---

# One portability issue remains

Your public product is supposed to be reusable by strangers.

A Linux-only combination of:

```text
cron
flock
system binaries
```

is less friendly to Windows/macOS researchers.

This does not mean replacing your scheduler.

Instead support generated installation recipes:

```text
mlb schedule install --systemd
mlb schedule print --cron
```

and document Windows/macOS alternatives.

More importantly, users who only consume the published research dataset should not need the producer stack at all.

Which leads to one of the best architectural decisions you've already made.

---

# You should explicitly think of this as a producer and a consumer product

The **producer** is heavy:

```text
PostgreSQL
connectors
Retrosheet
Statcast
MLB API
SQLMesh
full transforms
market capture
```

The **consumer** should be extremely light:

```bash
pip install mlb-research
```

then:

```python
import mlb_research
```

and query:

```text
DuckDB
Parquet
feature utilities
backtest harness
```

A researcher should not need:

```text
Postgres
psycopg
XGBoost
Chadwick binaries
Kalshi credentials
```

just to analyze batting data.

Your `packages/mlb-research` + Parquet/Hugging Face + DuckDB direction is exactly right.

DuckDB's direct Parquet query path and lightweight Python API are a very strong fit for that consumer product. [DuckDB](https://duckdb.org/docs/stable/clients/python/overview?utm_source=chatgpt.com)

---

# `retrosheetpy` may be one of the project's most valuable standalone contributions

This deserves special mention.

You previously wanted a pip-installable replacement/port of Chadwick so users could avoid installing native tooling.

You now have:

```text
packages/retrosheetpy
```

and differential tests against a pinned Chadwick development commit.

That is exactly how I would attempt such a port.

Not:

> It seems right.

But:

```text
same source input
Chadwick output
Python output
byte/field parity
```

If you can achieve comprehensive parity, I would eventually make:

```text
retrosheetpy
```

its own installable package with a narrow, stable API.

The MLB project can consume it.

Other baseball researchers can consume it.

And Chadwick can optionally remain a reference/backend.

That is genuine ecosystem value beyond your prediction project.

---

# The package import graph still needs decoupling

Open issue #111 is important.

`mlb_baseball.model.__init__` eagerly importing psycopg and dozens of model modules is the opposite of how a reusable research library should behave.

A user should be able to do:

```python
from mlb_research.markov import ...
```

without initializing:

```text
database code
market connectors
XGBoost
neural modules
Postgres
```

This should eventually lead to extras along the lines of:

```text
mlb-research
mlb-baseball[builder]
mlb-baseball[markets]
mlb-baseball[ml]
mlb-baseball[gpu]
```

not necessarily those exact package names, but that dependency topology.

This matters a lot for adoption.

---

# Your testing approach is excellent

The rule:

> mock the network, not PostgreSQL

has produced a much stronger database project than a mock-heavy test suite would.

You currently have:

```text
unit tests
real Postgres integration tests
pgTAP
SQL lint
SQL ownership lint
mypy
ruff
docs build
metric catalog gate
Retrosheet-vs-Chadwick differential tests
gitleaks
CodeQL
Semgrep
SBOM / scorecard workflows
```

That is very solid.

I especially like the external tie-out philosophy.

The key distinction is:

```text
self-consistency test:
my code gives the number my own formula predicts

independent validation:
my code reproduces an independently published result
```

Your metric catalog now understands that distinction.

Keep pushing it.

I care more about this than an arbitrary “100% code coverage” target.

---

# The pipeline needs a tiny reference-database acceptance test

You have many excellent focused tests.

I would add one intentionally small end-to-end research database fixture.

Something like:

```text
2 seasons
a few teams
trades
doubleheaders
postseason
one weird baserunning event
one player substitution
one starter change
one market
one missing field
```

Run:

```text
migrate
→ ingest fixture
→ conform
→ gold
→ build features
→ readiness
→ baseline model
→ export
```

and compare the resulting canonical tables/artifacts against versioned expected results.

That gives you a project-level invariant:

> Can the whole machine still build a coherent baseball research database?

Individual module tests cannot completely answer that.

---

# Gold should become contract-driven

I think this would be the most useful metadata addition after stable IDs.

For every important published relation, define a machine-readable contract describing:

```text
relation
description
grain
business key
writer
inputs
build strategy
coverage
freshness expectation
source rights
null policy
PIT classification
formula/version
validation
public eligibility
```

For example conceptually:

```yaml
relation: gold.batting_game
grain:
  - game_id
  - player_id
  - team_id

owner: sqlmesh:gold.batting_game

coverage:
  start: 1910

point_in_time: false

public_safe: true

business_key:
  - game_id
  - player_id
  - team_id

quality:
  source_tieout: retrosheet
  required_audits:
    - unique_grain
    - nonnegative_counts
    - source_game_coverage
```

But do **not** create another pile of YAML that duplicates five docs.

Use it to generate parts of:

```text
TABLE_CONTRACTS
data dictionary
doctor/audit registration
docs
export eligibility
```

Then it earns its existence.

---

# Gold should have exactly one writer per relation

I would enforce this in CI.

You are already close to this doctrine.

Turn it into a hard invariant.

A machine should be able to answer:

```text
gold.team_woba
→ owner = transforms/models/team_woba.sql
```

and nothing else is allowed to mutate it.

If Python orchestration runs SQLMesh, fine.

If Python selects parameters and invokes one named SQL resource, fine during migration.

But there must be one canonical computational implementation.

This is especially important because you currently have formula risks such as:

```text
wOBA in Python + SQLMesh
FIP logic in multiple modules
pitch-discipline logic in production SQL + stale SQLMesh copy
```

The October 5 Retrosheet pitch fix is proof of the danger: the production SQL was corrected, but the unpromoted SQLMesh copy still contains the old wrong logic.

That cannot happen after SQLMesh promotion.

Canonical ownership fixes it.

---

# The wOBA issue should be one of your first metric cleanups

Your metric catalog itself documents the problem beautifully.

Production currently uses a fixed set of wOBA weights across eras.

But you now possess:

```text
gold.fangraphs_guts
```

with season-specific constants.

So the project is knowingly doing:

```text
1915
1975
2000
2025
```

with the same weights even though the run environment differs.

I would fix this before claiming a polished all-history sabermetric surface.

A canonical wOBA implementation should resolve:

```text
season
→ season's weights
```

and should have a documented fallback/coverage rule.

Then every downstream use—team rolling wOBA, wRC+, player metrics—should use the same owner.

This is exactly the kind of formula SQLMesh should own.

---

# Now to the ML architecture

The database should not be designed around one model.

It should be designed around **prediction questions**.

Today you already have:

```text
home_win
run_differential
```

in the experiment/target concepts.

Expand that idea.

Every model target should have a versioned contract.

For example:

```text
target: game.home_win
grain: game
cutoff: scheduled_first_pitch
label: home_score > away_score
eligibility: regular season
type: binary
```

Or your player example:

```text
target: player.hits_exactly_3
grain: player-game
cutoff: prediction timestamp
label: H == 3
```

But your specific “3-for-3” example is even more precise:

```text
H = 3
AND
AB = 3
```

which is not the same thing as:

```text
at least 3 hits
```

or:

```text
3 hits in 4 AB
```

Taking Chipper Jones simply as the hypothetical player in your example, the research system should be able to ask exactly that sort of event-probability question.

---

# Player props should probably be generative rather than one giant classifier

For a future player event such as:

> exactly 3 hits in exactly 3 official at-bats

I would eventually model the underlying process.

Something like:

```text
P(player starts)
       ×
P(lineup position)
       ×
P(number of PA)
       ×
P(AB | PA)
       ×
P(each PA outcome | context)
```

Context can include:

```text
batter talent
handedness
starter
starter arsenal
starter quality
bullpen
platoon
park
weather
lineup strength
umpire
recent workload
defense
```

Then simulate the game.

That gives you:

```text
P(H = 3 AND AB = 3)
```

naturally.

It also gives you:

```text
P(H >= 2)
P(HR >= 1)
P(RBI >= 2)
P(team wins)
P(total > 8.5)
P(player HR AND team wins)
```

from the same underlying simulation.

That is far more coherent for parlays than multiplying separately trained probabilities.

---

# Your Markov/simulation direction is therefore strategically important

Issue #88 is pointed in the right direction.

A player/team-aware PA model feeding a state simulation can eventually produce joint probabilities directly.

For example:

```text
P(Yankees win AND Judge HR)
```

should come from the same simulated worlds.

Not:

```text
P(Yankees win)
×
P(Judge HR)
×
guessed correlation adjustment
```

That distinction will matter enormously when you move into correlated parlays.

Your project already recognizes this.

I agree with it.

---

# I would build a target registry before building many more models

This is one of my strongest ML recommendations.

The model should not own the definition of what it predicts.

The research platform should.

For every target:

```text
target name
target version
population
observation cutoff
prediction horizon
label calculation
void/censored conditions
evaluation metrics
market equivalents
```

Then:

```text
Elo
GBM
CatBoost
Bayesian model
Markov
neural model
```

can compete on exactly the same target.

That eliminates a huge amount of accidental apples-to-oranges comparison.

---

# Your point-in-time feature architecture is a major strength

This may ultimately distinguish the project more than having another xwOBA implementation.

Lots of baseball projects contain stats.

Far fewer rigorously answer:

> What could this model actually have known at 5:00 PM before a 7:05 PM game?

Your DuckDB feature store, explicit availability/cutoff concepts, leakage checks, and chronological folds are exactly where your research credibility comes from.

I would make `available_at` or an equivalent knowledge-time rule mandatory for every model feature family.

Not just:

```text
event happened at T
```

but:

```text
value became knowable at T
```

Those are not always the same.

For example:

```text
final-season WAR
scorer corrections
post-game weather
published leaderboard values
revised data
probable starter
confirmed lineup
```

all have different information availability.

That is the difference between a statistical database and a legitimate forecasting database.

---

# Feature readiness should become target-specific

A feature can be valid for one target and leakage for another.

For example:

```text
game final score
```

is perfectly good for historical descriptive research.

It is impossible as a pregame game-win feature.

So your current `readiness.py` approach is conceptually excellent.

Eventually I would want:

```bash
mlb readiness \
  --target game.home_win \
  --as-of 2026-07-01T17:00:00Z
```

to produce:

```text
feature availability
coverage
unexplained NULLs
future leakage
source rights
data version
target eligibility
backbone tie-out
```

That becomes a powerful research gate.

---

# Modeling evaluation should have two completely separate questions

Never combine these.

First:

> Is the model a good probabilistic forecaster?

Measure:

```text
log loss
Brier
calibration
calibration slope/intercept
reliability curves
discrimination
stability by season
```

Then:

> Is it economically useful relative to a market?

Measure:

```text
model probability
market executable probability
spread
fees
slippage
liquidity
expected value
realistic fill
closing-line comparison
```

A model can be statistically good but economically useless.

A mediocre model might still identify a narrow badly-priced market.

Those should remain separate analyses.

---

# This leads to the biggest missing piece for your commercial objective: market normalization

Your market layer is not yet good enough for the long-term goal.

`core.market` currently collapses a market/game/source down to essentially one useful pregame observation.

Issue #113 already exposes the consequence:

```text
open
24h
6h
close
```

cannot all be evaluated honestly when you only retain one canonical pregame value in `core.market`.

The new 15-minute raw snapshot capture is a very good correction.

Now finish the data model.

I would eventually replace the conceptual role of `core.market` with several normalized objects:

```text
market_contract
market_game_map
market_quote
market_settlement
```

You do not necessarily need those exact names.

But you need those concepts.

---

# A market contract is not a quote

A contract says:

```text
provider
provider_market_id
event
question
outcome
side
line
open_time
close_time
settlement rule
status
```

A quote says:

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
```

A settlement says:

```text
final result
settlement price
settled_at
resolution source
void reason
```

That separation matters.

Kalshi's current API representation exposes distinct yes/no bid and ask prices, sizes, open interest, liquidity, timestamps and other market state fields rather than just one probability number. [API Documentation](https://docs.kalshi.com/api-reference/events/get-multivariate-events?utm_source=chatgpt.com)

That is what your normalized schema should preserve.

---

# Do not compare your model to a single “market probability”

Suppose the model says:

```text
P(win) = 0.58
```

and the market screen appears to say:

```text
0.54
```

That does not automatically mean:

```text
edge = +4%
```

What can you actually buy?

Maybe:

```text
bid = .53
ask = .56
```

Then your executable price is closer to `.56`.

And after:

```text
fees
spread
slippage
size
```

your supposed edge may be gone.

Polymarket itself describes market prices as probability-like prices formed by supply and demand; that's useful conceptually, but a real trading strategy still has to model the price at which your order can execute. [Polymarket Documentation](https://docs.polymarket.com/faq?utm_source=chatgpt.com)

That distinction should be first-class in your research system.

---

# Also: mispricing and arbitrage are different things

This is important language for the eventual paid research product.

If your model estimates:

```text
true probability = 60%
market ask = 52%
```

you believe you found **positive expected value / mispricing**.

That is not necessarily arbitrage.

True arbitrage means you can construct positions whose combined outcomes lock in profit regardless of result, after fees/execution constraints.

Your future site should distinguish:

```text
model edge
value opportunity
cross-market discrepancy
true arbitrage
```

That will make the research much more credible.

---

# The market mapping should eventually be target-driven

This is where your target registry becomes incredibly useful.

Instead of:

```text
Kalshi market
→ some game
```

you want:

```text
provider contract
     │
     ▼
canonical target + settlement semantics
```

For example:

```text
KALSHI-XYZ
→ game.home_win:v1
```

or:

```text
Polymarket ABC
→ game.total_runs_gt:8.5:v1
```

or:

```text
DraftKings player prop
→ player.hits_gte:2:v1
```

Then model predictions and market quotes speak the same semantic language.

This is how you eventually support:

```text
Kalshi
Polymarket
The Odds API
DraftKings
FanDuel
...
```

without hardcoding separate research logic for every provider.

---

# Be extremely careful with market settlement semantics

Your model target has to match the actual contract.

Questions that matter:

```text
Does postponement void it?
Does extra innings count?
Does player need to start?
What if player has zero PA?
What if lineup changes?
Does an abandoned game settle?
What official source resolves the event?
```

A technically accurate baseball probability is useless if it predicts a subtly different event from the contract you are pricing.

So contract normalization should include resolution semantics, not just text matching.

---

# The current 15-minute odds capture is a good starting cadence

You measured current snapshot volumes before selecting the cadence.

That is exactly what you should do.

Do not optimize it further yet.

Let the week of real data answer:

```text
How fast do prices meaningfully change?
How many duplicate observations?
How much storage?
How often do we miss meaningful movement?
```

Then perhaps switch from:

```text
capture every quote
```

to:

```text
append only when price/size/status changes
```

if volume becomes wasteful.

---

# You need a generalized run lineage record

You already have good lineage ingredients scattered through:

```text
meta.ingestion_run
meta.ingestion_item
meta.model
meta.experiment
snapshots
feature versions
git SHA
metric permalinks
```

Eventually every published research result should be reconstructable from something resembling:

```text
research_run_id

git_commit
schema_version
data_snapshot
source_artifact_hashes
feature_set_version
feature_artifact_hash
target_version
model_version
model_artifact_hash
hyperparameters
training_cutoff
evaluation_period
environment/lock hash
generated_at
```

Then an article can say:

```text
Research run: 8e512...
```

and you can reproduce it.

That's enormously valuable if you eventually charge for research.

---

# Model artifacts should always be content-addressed

Issues #108 and #120 show why.

Never let model identity mean:

```text
models/gbm-v2.json
```

alone.

Prefer:

```text
models/artifacts/
    sha256-or-run-id/
        model.json
        metadata.json
```

Then a human-friendly alias can point to:

```text
champion
candidate
```

But the immutable artifact remains immutable.

And all writes should be:

```text
temporary file
fsync if appropriate
atomic os.replace()
```

Never write directly over a model artifact.

---

# “Champion” should be a promotion decision, not simply the latest model

The existing GBM behavior is actually philosophically correct in one respect:

If it doesn't beat the baselines, it should not become champion.

Keep that.

The baseline ladder should look something like:

```text
market naïve
historical home-rate
Log5
Elo
regularized logistic
Poisson / run model
CatBoost / XGBoost
Markov
Bayesian player model
ensemble
```

A more complicated model earns promotion.

Complexity alone is not progress.

---

# I would not prioritize neural networks

Not yet.

For structured baseball data of your current scale, I would rather have:

```text
clean targets
perfect PIT features
calibrated logistic model
CatBoost
hierarchical Bayesian components
well-constructed simulation
```

than a sophisticated neural network with uncertain input semantics.

Your major risk is still data semantics, not insufficient model capacity.

---

# The public dataset should remain more conservative than the internal Engine

This separation is correct even if we ignore the existing constitution and reason from scratch.

Your public research package should be:

```text
reproducible
citable
documented
portable
legally redistributable
honest about limitations
```

Your private/internal Engine can contain:

```text
tuned hyperparameters
experimental features
market execution research
novel composites
subscriber rankings
model weights
current edges
```

That split simultaneously helps open-source credibility and preserves the possibility of a commercial product.

---

# Source rights should become mechanically enforced

You already distinguish things like:

```text
public_safe
local_research
```

Excellent.

Don't leave that only in documentation.

The exporter should traverse declared lineage.

If:

```text
gold.foo
```

depends on a source that cannot be redistributed, then:

```text
mlb export --preset public
```

should refuse it automatically.

Not:

> We remembered not to include it.

But:

```text
ERROR:
gold.foo depends on raw.provider_x
rights policy = local_research
```

That's how you avoid future licensing mistakes.

---

# The open Negro League issue should not be handled as an incidental filter

Issue #258 matters conceptually.

A research database spanning baseball history needs explicit competition/game classification.

You shouldn't depend on:

```text
league IS NOT NULL
```

or arbitrary year filters to distinguish populations.

The game dimension should make it possible to ask:

```text
MLB regular season
MLB postseason
Negro Leagues
All-Star
exhibition
spring training
other
```

explicitly.

Then target definitions specify:

```text
eligible_competition = MLB
eligible_game_type = regular
```

This is important both academically and for ML.

---

# Your public “easy install” goal needs bootstrap profiles

A full everything bootstrap is a large job.

A new user shouldn't have to ingest every Statcast pitch and market snapshot to answer:

> What was Ted Williams' OBP?

I would eventually provide conceptual profiles such as:

```text
research-core
research-full
statcast
markets
modeling
everything
```

For example:

```bash
mlb bootstrap --preset research-core
```

might load enough for:

```text
games
players
teams
batting/pitching
standard metrics
```

while:

```bash
mlb bootstrap --preset modeling
```

adds:

```text
Statcast
features
advanced sources
```

This materially improves adoption.

Your existing `preflight` command is a great place to tell users:

```text
estimated disk
required dependencies
enabled sources
missing credentials
next commands
```

---

# The docs architecture is strong

The combination of:

```text
MkDocs
data dictionary
grain ladder
formula citations
honest limitations
notebooks
generated metric catalog
```

is exactly what a research platform needs.

I would make one principle non-negotiable:

> If metadata can be generated from the actual contract/code, don't maintain a second prose copy manually.

The amount of documentation in this repo is now large enough that doc drift itself is a risk.

Generate:

```text
relation docs
metric docs
source coverage
feature catalog
CLI reference
```

where feasible.

Keep ADRs and research reasoning hand-written.

---

# AI agents and skills should come later—but they can become extremely powerful

I absolutely see the end state you're describing.

A user could tell Claude:

> Build me a model estimating the probability that Aaron Judge gets at least two hits tomorrow and compare it to any corresponding market.

And the agent could perform:

```text
inspect target
check data readiness
select admissible features
build PIT artifact
train chronological model
calibrate
backtest
retrieve market contract
compare executable quotes
write research report
```

But the key insight is:

**The skill should not contain the baseball logic.**

The skill should teach the agent how to operate the CLI and interpret structured outputs.

That way humans and agents use the same platform.

---

# The eventual skills I would build

Once the CLI contracts stabilize, I would build skills around workflows such as:

1. `mlb-diagnose` — interpret structured doctor/audit failures, run only safe diagnostic commands, point to root cause and remediation.
2. `mlb-add-source` — source research → connector contract → fixtures → ingestion → health checks → lineage.
3. `mlb-add-metric` — citation → grain → formula → SQLMesh → audits → tie-out → catalog → docs.
4. `mlb-add-target` — define event semantics, cutoff, labels, eligibility, settlement mapping and evaluation.
5. `mlb-build-feature-set` — inspect available features, enforce PIT rules, run readiness, build immutable DuckDB artifact.
6. `mlb-run-research` — train/baseline/backtest/calibrate/compare and create a fully reproducible run.
7. `mlb-market-study` — normalize a market, find matching model target, retrieve the correct historical quote cutoff and calculate executable EV.
8. `mlb-publish-research` — turn an immutable research run into tables/charts/Markdown/web content with citations.

These skills should operate machine-readable commands.

That's why fixing `doctor --json`, readiness JSON, run IDs, and target contracts now pays off later.

---

# What I would do next, in exact order

This is the sequence I would use rather than starting another broad refactor:

1. **Finish the current `pipeline-recovery` change.** Resolve the remaining real doctor defects at their source: catcher framing should be withheld/rebuilt rather than bounds widened; repair the MLB analytics item ledger; fix the stale feature artifact UX; correct prediction-count semantics; fix false backup awareness using the verified host backup; finish odds capture/backfill/cron and classify every remaining failure. Goal: a healthy normal installation produces an actually trustworthy doctor result.

2. **Complete stable IDs + incremental conform.** Incorporate the pipeline-recovery corrections: content-aware fingerprints, transformation versioning, no delete/reinsert of `core.game`, full-column equivalence checks, staging/atomic publication, and incremental/full parity. This is the highest-value database architecture change.

3. **Create the canonical transformation ownership gate.** Every mutable derived relation gets exactly one registered writer. CI should detect duplicate writers. Freeze new writes to `gold.game_feature`.

4. **Start the real SQLMesh cutover with two or three easy models.** I would use well-understood relations such as park factor and team wOBA—but fix era-specific wOBA constants first. Add proper SQLMesh tests and blocking audits, shadow-run, tie out, promote, delete the old writer. Then repeat. SQLMesh remains outside raw/core identity.

5. **Establish the trusted-metric gate.** Keep the current catalog, add asset/admission semantics, mark invalid catcher framing disabled/withheld, and prevent experimental/AI-generated unvalidated metrics from silently becoming production model features. Do not resurrect the 101 deleted Gemini metrics.

6. **Strengthen the canonical event spine.** Design—carefully, as its own proposal—the typed event/PA relationship needed to eliminate repeated direct interpretation of `raw.retrosheet_event`. Decide whether that means enriching `core.play` plus adding `core.event`, rather than forcing every sabermetric SQL model to understand Retrosheet quirks independently.

7. **Finish the public research backbone and source rollover system.** Add automated current-year MLB → Retrosheet season reconciliation, resolve box-only historical games, explicitly classify Negro League/game populations, and make public export eligibility lineage-driven.

8. **Normalize market history.** Separate market identity/contracts from timestamped observations and settlement. Preserve bid/ask/size/liquidity. Map contracts onto canonical targets. Once this exists, `open`, `24h`, `6h`, and `close` evaluations become truthful instead of aliases of the same quote.

9. **Formalize the target registry.** Expand beyond `home_win` and `run_differential`. Targets own labels, eligibility, cutoff, horizon, void/censoring semantics, metrics and market mappings.

10. **Then build the model ladder.** Start boring: Elo/log5 → regularized logistic → runs models → CatBoost/XGBoost → player hierarchical/PA models → Markov/Monte Carlo. Require chronological evaluation and calibration at every promotion. Do not promote on accuracy alone.

11. **Turn research runs into immutable artifacts.** Every prediction or published result should point to the input snapshot, feature set, target, code commit, model artifact and evaluation period. Fix remaining model-artifact atomicity/path issues.

12. **Only after these contracts stabilize, build the AI skills and subscriber-facing research workflow.** At that point the AI doesn't need to improvise database behavior; it simply knows how to drive a deterministic research machine.

---

# Where I think this can end up

I don't think the best version of this project is merely:

> a baseball database with a bunch of advanced stats.

That is crowded territory.

The more compelling product is:

> **A reproducible baseball forecasting research platform where every number is traceable from raw event → canonical fact → validated statistic → point-in-time feature → model → calibrated prediction → timestamped market price → research result.**

That is meaningfully different.

Pybaseball is excellent for accessing baseball data.

Baseball Reference/FanGraphs/Savant are excellent statistical resources.

Baseball.computer is a useful research/database reference.

Odds sites expose markets.

Your opportunity is to connect those worlds while preserving provenance and time.

The chain is the product:

```text
SOURCE
  ↓
RAW EVIDENCE
  ↓
CANONICAL BASEBALL FACTS
  ↓
VALIDATED STATISTICS
  ↓
POINT-IN-TIME FEATURES
  ↓
TARGET
  ↓
MODEL
  ↓
CALIBRATION
  ↓
PREDICTION
  ↓
MARKET QUOTE AT SAME TIME
  ↓
EDGE / EV / ARBITRAGE ANALYSIS
  ↓
REPRODUCIBLE RESEARCH
```

That is what I would optimize the repository around.

And importantly, **you do not need to tear down what you have to get there**. The current project has already built most of the hard primitives. What it needs now is a period of ruthless convergence: stable identity, single writers, trusted metrics, atomic builds, normalized market history, and machine-readable contracts.

Once those are established, adding models becomes fun again instead of dangerous.

The next concrete move I would make in the repo is **finish `pipeline-recovery`, then execute `stable-ids-incremental-conform`, and treat those two as the gate before doing further metric/model expansion**. After that, I would make the gold/SQLMesh consolidation the next architectural program. [SQLMesh](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/?utm_source=chatgpt.com)
