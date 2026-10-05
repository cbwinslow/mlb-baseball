Yes. After reviewing the current repository architecture, the metric code, the SQL ownership rules, the SQLMesh state, the statistic backbone, and the available external libraries, I think there is a fairly clear path forward.

## The decision I would make

**Do not build a giant Python sabermetrics engine and do not build a collection of PostgreSQL functions/UDFs.**

Instead, make **versioned SQL the canonical implementation of deterministic sabermetrics**, with SQLMesh eventually managing those SQL transformations where it provides real value. Keep Python for modeling, simulation, orchestration, and an optional lightweight researcher-facing calculation API.

In other words:

```text
SOURCE DATA
    ↓
raw
    source-faithful data
    ↓
core
    canonical baseball facts / identities / events
    ├── game
    ├── play / plate appearance
    └── pitch
    ↓
gold
    reusable descriptive baseball statistics
    ├── batting_game
    ├── pitching_game
    ├── batting_season
    ├── pitching_season
    ├── wOBA
    ├── FIP
    ├── xFIP
    ├── RE24
    ├── WPA
    ├── park factors
    └── etc.
    ↓
DuckDB feat.*
    point-in-time / rolling / pregame versions
    ↓
Python
    ML / simulation / backtesting / pricing / betting models
```

That architecture is actually very close to what your project has evolved toward. **I would refine what you have rather than tear it down.**

---

# The most important distinction: facts vs. statistics vs. features

I think this distinction resolves most of the confusion.

| Layer | What belongs there | Example |
|---|---|---|
| `raw` | What the source literally gave us | Retrosheet event, MLB pitch JSON |
| `core` | Canonical baseball facts | game, player, pitch, PA/play, outs, outcome |
| `gold` | Reusable baseball/sabermetric statistics | AVG, OBP, wOBA, FIP, RE24 |
| `feat.*` | Point-in-time model features | starter FIP entering game, trailing-30d K%, team rolling wOBA |
| Python models | Predictions / fitted behavior | win probability, run distribution, Monte Carlo |
| Market layer | Value/pricing | fair odds, EV, edge, Kelly |

So to your question:

> do we just need raw values? the core layer?

**No. We absolutely want Gold.**

Raw/core alone would force every researcher, notebook, model, and analysis to recreate sabermetrics repeatedly. That would undermine one of the things that can make `mlb-baseball` genuinely useful.

But **Core should not become a giant collection of sabermetric columns.**

Core should answer:

> What actually happened?

Gold should answer:

> What statistics can we derive from what happened?

Feat should answer:

> What did we know before this game that a model could legitimately use?

That is a very clean separation.

---

# I would definitely preserve the play/pitch separation

I agree with you that the decoupling you've created between plays and pitches is valuable.

A pitch is not a play, and a plate appearance/play is not just a collection of pitch statistics.

For example:

```text
game
 └── plate appearance / play
      ├── batter
      ├── pitcher
      ├── outcome
      ├── base/out state
      ├── runs
      │
      └── pitches
           ├── pitch type
           ├── velocity
           ├── spin
           ├── location
           ├── called strike
           ├── whiff
           └── movement
```

That lets us derive things like:

**Play/PA-derived**

```text
AVG
OBP
SLG
OPS
ISO
BABIP
wOBA
wRC+
FIP
K%
BB%
RE24
WPA
BaseRuns
```

while the pitch relation supports:

```text
CSW%
Whiff%
Chase%
Zone%
F-Strike%
pitch mix
velocity
spin
movement
platoon pitch behavior
pitch tunneling
```

We should **not flatten all of this together**.

One thing I would seriously consider eventually is a first-class canonical **plate-appearance/event fact grain** between `core.play` and Gold.

That is because I found a recurring architectural smell in the current project: some of the statistic backbone still has to reach directly back into `raw.retrosheet_event` because `core.play` does not preserve enough of Retrosheet's event classification.

Your own `statistic-backbone` spec explicitly documents this.

That isn't necessarily wrong, but it tells us something.

Instead of having ten Gold formulas independently reinterpret Retrosheet event codes, we could eventually establish:

```text
raw.retrosheet_event ─┐
                      ├── core.plate_appearance
raw.mlb_playbyplay ───┘
```

with normalized facts such as:

```text
is_ab
is_pa
is_hit
hit_bases
is_bb
is_ibb
is_hbp
is_sf
is_sh
is_so
is_hr
outs_on_play
runs_on_play
batter_id
pitcher_id
batting_team_id
pitching_team_id
```

Then sabermetric SQL becomes dramatically simpler and source-independent.

I would **not rush into that change**, because your current backbone is working and being tied out. But it's a very good architectural direction.

---

# There is already evidence in the repo that we need formula consolidation

This was probably the most important thing I found.

You already have excellent sabermetric work. The bigger problem isn't lack of formulas.

The problem is that **formula ownership and constants are starting to drift.**

For example, `model/offense.py` currently has fixed values such as:

```python
W_UBB = 0.690
W_HBP = 0.722
W_1B = 0.878
W_2B = 1.242
W_3B = 1.569
W_HR = 2.015

WOBA_SCALE = 1.20
```

Yet the comments correctly acknowledge that actual wOBA weights vary by season.

FanGraphs likewise documents that the linear weights vary from year to year and publishes yearly values through its Guts data. [Sabermetrics Library](https://library.fangraphs.com/offense/woba/?utm_source=chatgpt.com)

I found something similar in:

`team_pitcher_estimators_retrosheet_update.sql`

where xFIP currently contains:

```sql
13.0 * (0.105 * prior_fb)
...
+ 3.10
```

So:

```text
league HR/FB = .105
FIP constant = 3.10
```

are effectively hard-coded.

But the FIP constant is specifically designed to align league FIP with league ERA and therefore varies with the run environment. [Sabermetrics Library](https://library.fangraphs.com/pitching/fip/?utm_source=chatgpt.com)

The same SQL also has another set of hard-coded wOBA weights for platoon calculations.

**That is what I would fix before creating another hundred metrics.**

---

# We need a constants/reference-data layer

Instead of formulas carrying magic numbers, I'd make the parameters data.

Something conceptually like:

```text
raw.fangraphs_guts
        ↓
core.stat_constant
```

with records resembling:

| season | metric | parameter | value | source |
|---:|---|---|---:|---|
| 2024 | woba | bb_weight | … | published |
| 2024 | woba | hbp_weight | … | published |
| 2024 | woba | single_weight | … | published |
| 2024 | woba | scale | … | published |
| 2024 | fip | constant | … | derived/published |
| 2024 | xfip | league_hr_fb | … | derived |
| 2024 | run_env | runs_per_pa | … | derived |

Then SQL says conceptually:

```sql
SELECT ...
FROM batting_components b
JOIN core.stat_constant c
  ON c.season = b.season
```

instead of:

```sql
0.690 * bb
+ 0.722 * hbp
...
```

That becomes **much more reproducible and much easier to audit**.

Even better, some constants can be generated from our own database rather than fetched.

FIP's constant, league HR/FB, run environments, RE matrices and similar quantities can be calculated from the underlying league data.

That is particularly attractive because it makes `mlb-baseball` self-contained.

---

# One complication: descriptive metrics versus pregame metrics

This is an extremely important distinction for your ML project.

Suppose we're calculating:

```text
Aaron Judge 2024 final-season wOBA
```

Using the official 2024 wOBA coefficients is completely appropriate.

But suppose we're calculating:

```text
Aaron Judge wOBA entering May 10, 2024
```

for a historical model.

We cannot casually inject information that became known after May 10.

So we need two contracts:

```text
DESCRIPTIVE GOLD
final/historical metric
→ season-calibrated constants are fine

POINT-IN-TIME FEATURE
information available entering game
→ constants/baselines need explicit availability semantics
```

That means the Gold and `feat.*` versions of something named "wOBA" may legitimately have subtly different contracts.

That's not duplication if we explicitly define them.

It's:

```text
gold.player_season.woba
     descriptive historical statistic

feat.game.home_woba_30d
     point-in-time predictive feature
```

Different purpose.

---

# What should SQLMesh do?

Here's where I'd change the way we're thinking about SQLMesh.

**SQLMesh isn't the sabermetric library.**

SQL is the formula.

SQLMesh is the machinery around the SQL:

```text
lineage
incrementality
environments
planning
audits
restatements
dependency graph
materialization
```

SQLMesh's own model system is designed around exactly these kinds of deterministic transformations and incremental time-based processing. [SQLMesh](https://sqlmesh.readthedocs.io/en/latest/concepts/audits/?utm_source=chatgpt.com)

But your current repository has a very important constraint:

**SQLMesh is still spike-only.**

`docs/SQLMESH_OPERATIONS.md` says the current gateway targets disposable `mlb_spike`, with `team_woba`, `park_factor`, etc. still candidate models. Production cutover requires parity first.

Therefore I would **not stop the project and rewrite Gold in SQLMesh right now.**

Instead:

```text
TODAY
versioned .sql = canonical formula

LATER
SQLMesh takes ownership of stable deterministic Gold relations
after parity testing
```

That gives us the best of both worlds.

And definitely **do not add dbt alongside it**. Your current architecture already made the SQLMesh-vs-dbt decision, and I don't see a compelling technical reason to reopen it.

---

# What about a Python sabermetrics library?

I specifically looked around for this.

There are three relevant cases.

### pybaseball

`pybaseball` is excellent, but it is primarily a **data acquisition library**. Its season-stat functions retrieve FanGraphs/Baseball-Reference metrics rather than serving as a canonical local formula implementation over your own event database. [GitHub](https://github.com/jldbc/pybaseball?utm_source=chatgpt.com)

So I would absolutely use pybaseball as:

```text
independent comparison source
research convenience
possibly supplemental ingestion
```

but **not** as our metric engine.

### baseballr

`baseballr` is much closer conceptually to what you're describing. It contains functions for things like FIP/wOBA, run expectancy and linear weights in addition to data acquisition. It is also actively documented. [Bill Petti](https://billpetti.github.io/baseballr/?utm_source=chatgpt.com)

I'd use it heavily as a **reference implementation and validation source**.

But making an R package a runtime dependency of this Python/Postgres/DuckDB platform would add more complexity than it removes.

### pyhomerun

This was the interesting find.

`pyhomerun` now provides pure Python functions for:

```text
AVG
OBP
SLG
OPS
ISO
BABIP
wOBA
wRAA
wRC+
ERA
WHIP
FIP
xFIP
Pythagorean expectation
log5
RE24
...
```

and allows custom wOBA weights and FIP constants. [PyPI](https://pypi.org/project/pyhomerun/0.8.0/?utm_source=chatgpt.com)

That is almost exactly the API you were imagining.

However, I **would not make it the canonical dependency yet**.

It is a relatively young package, and one design choice already conflicts with your project: it generally converts zero-denominator rate situations to `0.0`, whereas your project deliberately treats unavailable/undefined measurement as `NULL`.

Your current policy is statistically safer for a research database.

So `pyhomerun` is valuable as:

> an API-design inspiration and another independent formula implementation for tests.

Not something I would hand ownership of your database to.

---

# I think we should build our own *small* Python stats facade too

This may sound contradictory, but it's not.

I wouldn't put the warehouse calculation in Python.

I **would** eventually provide something like:

```python
from mlb_research.stats import batting, pitching

batting.woba(...)
pitching.fip(...)
batting.babip(...)
pitching.xfip(...)
```

because researchers using the PyPI package will love that.

The important rule is:

> **There must never be two independently maintained definitions of the same formula.**

For example, SQL remains canonical for warehouse relations, while the Python implementation is:

- very small;
- pure;
- uses the same constants dataset;
- thoroughly parity-tested against SQL;
- intended for interactive calculations/notebooks.

Your own `mlb_baseball/model/AGENTS.md` is already pointing toward a neutral `stats/` namespace.

I think that's the right instinct.

---

# So instead of a "sabermetric function library," build a sabermetric subsystem

I would structure the work around six concepts:

1. **Atomic components** — store additive quantities such as AB, PA, H, 1B, 2B, 3B, HR, BB, HBP, SF, SO, outs, BF, fly balls, ground balls, pitches, swings, whiffs. Your existing `batting_game` and `pitching_game` are already an excellent start.

2. **Constants/reference data** — season-aware wOBA coefficients, wOBA scale, league HR/FB, FIP constant, run environment and whatever else the formula requires. Every value gets provenance.

3. **Canonical versioned SQL formulas** — one formula owner for AVG, OBP, wOBA, FIP, xFIP, RE24, etc. No PostgreSQL stored procedures and no magic formula strings buried inside Python.

4. **Metric registry** — you already have `mlb_baseball/metrics/*.yaml`. Make that the catalog describing `grain`, `formula_owner`, `inputs`, `constant_source`, `null_policy`, `PIT policy`, `citation`, `validation_status`, and public/internal status.

5. **Point-in-time feature derivation** — DuckDB `feat.*` builds trailing/rolling/pre-game versions from the canonical components. We do not mix final-season descriptive statistics with model-safe historical features.

6. **Optional Python facade** — `mlb_research.stats`, designed for researchers and notebooks, with SQL/Python parity fixtures rather than becoming another warehouse implementation.

That would be much stronger than simply collecting hundreds of formulas.

---

# We should also stop trying to calculate "all sabermetrics"

I think this contributed to some of the complexity you are feeling now.

There are metrics like:

```text
AVG
OBP
SLG
BABIP
K%
BB%
FIP
wOBA
RE24
```

which are transparent functions of well-defined inputs.

Then there are things like:

```text
WAR
OAA
framing
xwOBA
SIERA
proprietary expected metrics
```

that range from complicated to provider/model dependent.

They shouldn't all be treated identically.

I'd use a progression:

```text
atomic facts
    ↓
exact arithmetic statistics
    ↓
league-calibrated statistics
    ↓
contextual/run-value statistics
    ↓
estimated/model-based statistics
    ↓
our novel predictive metrics
```

And a metric doesn't move upward until we can answer:

```text
What exactly is it?
What grain?
What inputs?
What constants?
What period?
What was knowable when?
What happens when data is missing?
Where does the definition come from?
What did we validate it against?
```

That discipline will make this repository much more credible than one containing 500 loosely sourced metrics.

---

# Where I think the project is right now

The core architecture is actually **better than I expected from the question**.

You already have:

- source-faithful Raw;
- canonical Game/Play/Pitch concepts;
- a grain-complete game → season → team → career statistic backbone;
- additive counting-stat foundations;
- correctly recomputed rates rather than averaged rates;
- PostgreSQL as source of truth;
- DuckDB `feat.*` as the disposable PIT/model feature layer;
- a metric registry;
- citations;
- tie-outs;
- SQL ownership rules;
- SQLMesh experimentation;
- separate Python modeling code.

That's a very defensible design.

The problem isn't that we chose SQL when Python would have been better.

**The problem is that the project grew faster than formula governance.**

That's why we now see:

```text
fixed constants
duplicate coefficients
similar formulas in multiple places
SQL + Python ownership overlap
some advanced metrics that are not fully validated
health checks exposing dubious implementations
```

The current pipeline-recovery work is actually surfacing exactly the right problems.

I would **not tear down the project**.

I'd consolidate it.

---

# The next move I recommend

I would finish the current pipeline-recovery/health work first rather than introducing another architectural rewrite while known calculations are failing.

Immediately after that, I would create one OpenSpec change along the lines of:

**`sabermetric-foundation`** or **`metric-formula-consolidation`**.

Its first job should **not** be writing formulas.

Its first job should be producing an inventory like:

```text
metric
grain
current implementation(s)
canonical input components
formula source
constants
constant source
descriptive/PIT
SQL owner
Python duplicate?
validation evidence
status
```

Then we attack the highest-value inconsistencies first.

**My first three targets would be wOBA/wRC+, FIP/xFIP, and RE24/WPA.**

Those give us offense, pitching and contextual run value, and force us to solve the constants/PIT architecture correctly.

Only after those are rock-solid would I move outward into SIERA, BsR, framing, pitch metrics and more exotic calculations.

---

## The architecture I would target

```text
                         ┌─────────────────────┐
                         │ metric registry     │
                         │ definition/citation │
                         │ grain/null/PIT      │
                         └──────────┬──────────┘
                                    │
                                    │ governs
                                    ▼
┌────────────┐     ┌─────────────────────────────┐
│ raw source │ ──▶ │ core canonical facts        │
└────────────┘     │                             │
                   │ game                        │
                   │ play / plate appearance     │
                   │ pitch                       │
                   │ stat constants/reference    │
                   └──────────────┬──────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────┐
                   │ gold descriptive metrics    │
                   │ canonical versioned SQL     │
                   │                             │
                   │ AVG / OBP / SLG / wOBA      │
                   │ FIP / xFIP / RE24 / WPA     │
                   │ season/career/team/etc.     │
                   └──────────────┬──────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────┐
                   │ DuckDB feat.*               │
                   │ point-in-time transformations│
                   └──────────────┬──────────────┘
                                  │
                  ┌───────────────┴────────────────┐
                  ▼                                ▼
          Python ML / sims                mlb_research.stats
          predictions                     researcher API
```

And later:

```text
versioned SQL
     +
SQLMesh
     =
incremental / audited / lineage-aware Gold builds
```

rather than:

```text
SQLMesh = formula library
```

That distinction is important.

**So my answer is: stay with SQL for the canonical sabermetric warehouse, keep SQLMesh as the eventual transformation manager, retain Play/Pitch separation, keep Core atomic, put reusable calculated stats in Gold, put pregame rolling versions in `feat.*`, and use Python only where Python genuinely wins.**

The most valuable work now is **consolidating the formulas and replacing fixed magic constants with governed, season-aware data**, not adding another framework or another hundred metrics. That will make the project simpler *and* more statistically trustworthy.Yes. After reviewing the current repository architecture, the metric code, the SQL ownership rules, the SQLMesh state, the statistic backbone, and the available external libraries, I think there is a fairly clear path forward.

## The decision I would make

**Do not build a giant Python sabermetrics engine and do not build a collection of PostgreSQL functions/UDFs.**

Instead, make **versioned SQL the canonical implementation of deterministic sabermetrics**, with SQLMesh eventually managing those SQL transformations where it provides real value. Keep Python for modeling, simulation, orchestration, and an optional lightweight researcher-facing calculation API.

In other words:

```text
SOURCE DATA
    ↓
raw
    source-faithful data
    ↓
core
    canonical baseball facts / identities / events
    ├── game
    ├── play / plate appearance
    └── pitch
    ↓
gold
    reusable descriptive baseball statistics
    ├── batting_game
    ├── pitching_game
    ├── batting_season
    ├── pitching_season
    ├── wOBA
    ├── FIP
    ├── xFIP
    ├── RE24
    ├── WPA
    ├── park factors
    └── etc.
    ↓
DuckDB feat.*
    point-in-time / rolling / pregame versions
    ↓
Python
    ML / simulation / backtesting / pricing / betting models
```

That architecture is actually very close to what your project has evolved toward. **I would refine what you have rather than tear it down.**

---

# The most important distinction: facts vs. statistics vs. features

I think this distinction resolves most of the confusion.

| Layer | What belongs there | Example |
|---|---|---|
| `raw` | What the source literally gave us | Retrosheet event, MLB pitch JSON |
| `core` | Canonical baseball facts | game, player, pitch, PA/play, outs, outcome |
| `gold` | Reusable baseball/sabermetric statistics | AVG, OBP, wOBA, FIP, RE24 |
| `feat.*` | Point-in-time model features | starter FIP entering game, trailing-30d K%, team rolling wOBA |
| Python models | Predictions / fitted behavior | win probability, run distribution, Monte Carlo |
| Market layer | Value/pricing | fair odds, EV, edge, Kelly |

So to your question:

> do we just need raw values? the core layer?

**No. We absolutely want Gold.**

Raw/core alone would force every researcher, notebook, model, and analysis to recreate sabermetrics repeatedly. That would undermine one of the things that can make `mlb-baseball` genuinely useful.

But **Core should not become a giant collection of sabermetric columns.**

Core should answer:

> What actually happened?

Gold should answer:

> What statistics can we derive from what happened?

Feat should answer:

> What did we know before this game that a model could legitimately use?

That is a very clean separation.

---

# I would definitely preserve the play/pitch separation

I agree with you that the decoupling you've created between plays and pitches is valuable.

A pitch is not a play, and a plate appearance/play is not just a collection of pitch statistics.

For example:

```text
game
 └── plate appearance / play
      ├── batter
      ├── pitcher
      ├── outcome
      ├── base/out state
      ├── runs
      │
      └── pitches
           ├── pitch type
           ├── velocity
           ├── spin
           ├── location
           ├── called strike
           ├── whiff
           └── movement
```

That lets us derive things like:

**Play/PA-derived**

```text
AVG
OBP
SLG
OPS
ISO
BABIP
wOBA
wRC+
FIP
K%
BB%
RE24
WPA
BaseRuns
```

while the pitch relation supports:

```text
CSW%
Whiff%
Chase%
Zone%
F-Strike%
pitch mix
velocity
spin
movement
platoon pitch behavior
pitch tunneling
```

We should **not flatten all of this together**.

One thing I would seriously consider eventually is a first-class canonical **plate-appearance/event fact grain** between `core.play` and Gold.

That is because I found a recurring architectural smell in the current project: some of the statistic backbone still has to reach directly back into `raw.retrosheet_event` because `core.play` does not preserve enough of Retrosheet's event classification.

Your own `statistic-backbone` spec explicitly documents this.

That isn't necessarily wrong, but it tells us something.

Instead of having ten Gold formulas independently reinterpret Retrosheet event codes, we could eventually establish:

```text
raw.retrosheet_event ─┐
                      ├── core.plate_appearance
raw.mlb_playbyplay ───┘
```

with normalized facts such as:

```text
is_ab
is_pa
is_hit
hit_bases
is_bb
is_ibb
is_hbp
is_sf
is_sh
is_so
is_hr
outs_on_play
runs_on_play
batter_id
pitcher_id
batting_team_id
pitching_team_id
```

Then sabermetric SQL becomes dramatically simpler and source-independent.

I would **not rush into that change**, because your current backbone is working and being tied out. But it's a very good architectural direction.

---

# There is already evidence in the repo that we need formula consolidation

This was probably the most important thing I found.

You already have excellent sabermetric work. The bigger problem isn't lack of formulas.

The problem is that **formula ownership and constants are starting to drift.**

For example, `model/offense.py` currently has fixed values such as:

```python
W_UBB = 0.690
W_HBP = 0.722
W_1B = 0.878
W_2B = 1.242
W_3B = 1.569
W_HR = 2.015

WOBA_SCALE = 1.20
```

Yet the comments correctly acknowledge that actual wOBA weights vary by season.

FanGraphs likewise documents that the linear weights vary from year to year and publishes yearly values through its Guts data. [Sabermetrics Library](https://library.fangraphs.com/offense/woba/?utm_source=chatgpt.com)

I found something similar in:

`team_pitcher_estimators_retrosheet_update.sql`

where xFIP currently contains:

```sql
13.0 * (0.105 * prior_fb)
...
+ 3.10
```

So:

```text
league HR/FB = .105
FIP constant = 3.10
```

are effectively hard-coded.

But the FIP constant is specifically designed to align league FIP with league ERA and therefore varies with the run environment. [Sabermetrics Library](https://library.fangraphs.com/pitching/fip/?utm_source=chatgpt.com)

The same SQL also has another set of hard-coded wOBA weights for platoon calculations.

**That is what I would fix before creating another hundred metrics.**

---

# We need a constants/reference-data layer

Instead of formulas carrying magic numbers, I'd make the parameters data.

Something conceptually like:

```text
raw.fangraphs_guts
        ↓
core.stat_constant
```

with records resembling:

| season | metric | parameter | value | source |
|---:|---|---|---:|---|
| 2024 | woba | bb_weight | … | published |
| 2024 | woba | hbp_weight | … | published |
| 2024 | woba | single_weight | … | published |
| 2024 | woba | scale | … | published |
| 2024 | fip | constant | … | derived/published |
| 2024 | xfip | league_hr_fb | … | derived |
| 2024 | run_env | runs_per_pa | … | derived |

Then SQL says conceptually:

```sql
SELECT ...
FROM batting_components b
JOIN core.stat_constant c
  ON c.season = b.season
```

instead of:

```sql
0.690 * bb
+ 0.722 * hbp
...
```

That becomes **much more reproducible and much easier to audit**.

Even better, some constants can be generated from our own database rather than fetched.

FIP's constant, league HR/FB, run environments, RE matrices and similar quantities can be calculated from the underlying league data.

That is particularly attractive because it makes `mlb-baseball` self-contained.

---

# One complication: descriptive metrics versus pregame metrics

This is an extremely important distinction for your ML project.

Suppose we're calculating:

```text
Aaron Judge 2024 final-season wOBA
```

Using the official 2024 wOBA coefficients is completely appropriate.

But suppose we're calculating:

```text
Aaron Judge wOBA entering May 10, 2024
```

for a historical model.

We cannot casually inject information that became known after May 10.

So we need two contracts:

```text
DESCRIPTIVE GOLD
final/historical metric
→ season-calibrated constants are fine

POINT-IN-TIME FEATURE
information available entering game
→ constants/baselines need explicit availability semantics
```

That means the Gold and `feat.*` versions of something named "wOBA" may legitimately have subtly different contracts.

That's not duplication if we explicitly define them.

It's:

```text
gold.player_season.woba
     descriptive historical statistic

feat.game.home_woba_30d
     point-in-time predictive feature
```

Different purpose.

---

# What should SQLMesh do?

Here's where I'd change the way we're thinking about SQLMesh.

**SQLMesh isn't the sabermetric library.**

SQL is the formula.

SQLMesh is the machinery around the SQL:

```text
lineage
incrementality
environments
planning
audits
restatements
dependency graph
materialization
```

SQLMesh's own model system is designed around exactly these kinds of deterministic transformations and incremental time-based processing. [SQLMesh](https://sqlmesh.readthedocs.io/en/latest/concepts/audits/?utm_source=chatgpt.com)

But your current repository has a very important constraint:

**SQLMesh is still spike-only.**

`docs/SQLMESH_OPERATIONS.md` says the current gateway targets disposable `mlb_spike`, with `team_woba`, `park_factor`, etc. still candidate models. Production cutover requires parity first.

Therefore I would **not stop the project and rewrite Gold in SQLMesh right now.**

Instead:

```text
TODAY
versioned .sql = canonical formula

LATER
SQLMesh takes ownership of stable deterministic Gold relations
after parity testing
```

That gives us the best of both worlds.

And definitely **do not add dbt alongside it**. Your current architecture already made the SQLMesh-vs-dbt decision, and I don't see a compelling technical reason to reopen it.

---

# What about a Python sabermetrics library?

I specifically looked around for this.

There are three relevant cases.

### pybaseball

`pybaseball` is excellent, but it is primarily a **data acquisition library**. Its season-stat functions retrieve FanGraphs/Baseball-Reference metrics rather than serving as a canonical local formula implementation over your own event database. [GitHub](https://github.com/jldbc/pybaseball?utm_source=chatgpt.com)

So I would absolutely use pybaseball as:

```text
independent comparison source
research convenience
possibly supplemental ingestion
```

but **not** as our metric engine.

### baseballr

`baseballr` is much closer conceptually to what you're describing. It contains functions for things like FIP/wOBA, run expectancy and linear weights in addition to data acquisition. It is also actively documented. [Bill Petti](https://billpetti.github.io/baseballr/?utm_source=chatgpt.com)

I'd use it heavily as a **reference implementation and validation source**.

But making an R package a runtime dependency of this Python/Postgres/DuckDB platform would add more complexity than it removes.

### pyhomerun

This was the interesting find.

`pyhomerun` now provides pure Python functions for:

```text
AVG
OBP
SLG
OPS
ISO
BABIP
wOBA
wRAA
wRC+
ERA
WHIP
FIP
xFIP
Pythagorean expectation
log5
RE24
...
```

and allows custom wOBA weights and FIP constants. [PyPI](https://pypi.org/project/pyhomerun/0.8.0/?utm_source=chatgpt.com)

That is almost exactly the API you were imagining.

However, I **would not make it the canonical dependency yet**.

It is a relatively young package, and one design choice already conflicts with your project: it generally converts zero-denominator rate situations to `0.0`, whereas your project deliberately treats unavailable/undefined measurement as `NULL`.

Your current policy is statistically safer for a research database.

So `pyhomerun` is valuable as:

> an API-design inspiration and another independent formula implementation for tests.

Not something I would hand ownership of your database to.

---

# I think we should build our own *small* Python stats facade too

This may sound contradictory, but it's not.

I wouldn't put the warehouse calculation in Python.

I **would** eventually provide something like:

```python
from mlb_research.stats import batting, pitching

batting.woba(...)
pitching.fip(...)
batting.babip(...)
pitching.xfip(...)
```

because researchers using the PyPI package will love that.

The important rule is:

> **There must never be two independently maintained definitions of the same formula.**

For example, SQL remains canonical for warehouse relations, while the Python implementation is:

- very small;
- pure;
- uses the same constants dataset;
- thoroughly parity-tested against SQL;
- intended for interactive calculations/notebooks.

Your own `mlb_baseball/model/AGENTS.md` is already pointing toward a neutral `stats/` namespace.

I think that's the right instinct.

---

# So instead of a "sabermetric function library," build a sabermetric subsystem

I would structure the work around six concepts:

1. **Atomic components** — store additive quantities such as AB, PA, H, 1B, 2B, 3B, HR, BB, HBP, SF, SO, outs, BF, fly balls, ground balls, pitches, swings, whiffs. Your existing `batting_game` and `pitching_game` are already an excellent start.

2. **Constants/reference data** — season-aware wOBA coefficients, wOBA scale, league HR/FB, FIP constant, run environment and whatever else the formula requires. Every value gets provenance.

3. **Canonical versioned SQL formulas** — one formula owner for AVG, OBP, wOBA, FIP, xFIP, RE24, etc. No PostgreSQL stored procedures and no magic formula strings buried inside Python.

4. **Metric registry** — you already have `mlb_baseball/metrics/*.yaml`. Make that the catalog describing `grain`, `formula_owner`, `inputs`, `constant_source`, `null_policy`, `PIT policy`, `citation`, `validation_status`, and public/internal status.

5. **Point-in-time feature derivation** — DuckDB `feat.*` builds trailing/rolling/pre-game versions from the canonical components. We do not mix final-season descriptive statistics with model-safe historical features.

6. **Optional Python facade** — `mlb_research.stats`, designed for researchers and notebooks, with SQL/Python parity fixtures rather than becoming another warehouse implementation.

That would be much stronger than simply collecting hundreds of formulas.

---

# We should also stop trying to calculate "all sabermetrics"

I think this contributed to some of the complexity you are feeling now.

There are metrics like:

```text
AVG
OBP
SLG
BABIP
K%
BB%
FIP
wOBA
RE24
```

which are transparent functions of well-defined inputs.

Then there are things like:

```text
WAR
OAA
framing
xwOBA
SIERA
proprietary expected metrics
```

that range from complicated to provider/model dependent.

They shouldn't all be treated identically.

I'd use a progression:

```text
atomic facts
    ↓
exact arithmetic statistics
    ↓
league-calibrated statistics
    ↓
contextual/run-value statistics
    ↓
estimated/model-based statistics
    ↓
our novel predictive metrics
```

And a metric doesn't move upward until we can answer:

```text
What exactly is it?
What grain?
What inputs?
What constants?
What period?
What was knowable when?
What happens when data is missing?
Where does the definition come from?
What did we validate it against?
```

That discipline will make this repository much more credible than one containing 500 loosely sourced metrics.

---

# Where I think the project is right now

The core architecture is actually **better than I expected from the question**.

You already have:

- source-faithful Raw;
- canonical Game/Play/Pitch concepts;
- a grain-complete game → season → team → career statistic backbone;
- additive counting-stat foundations;
- correctly recomputed rates rather than averaged rates;
- PostgreSQL as source of truth;
- DuckDB `feat.*` as the disposable PIT/model feature layer;
- a metric registry;
- citations;
- tie-outs;
- SQL ownership rules;
- SQLMesh experimentation;
- separate Python modeling code.

That's a very defensible design.

The problem isn't that we chose SQL when Python would have been better.

**The problem is that the project grew faster than formula governance.**

That's why we now see:

```text
fixed constants
duplicate coefficients
similar formulas in multiple places
SQL + Python ownership overlap
some advanced metrics that are not fully validated
health checks exposing dubious implementations
```

The current pipeline-recovery work is actually surfacing exactly the right problems.

I would **not tear down the project**.

I'd consolidate it.

---

# The next move I recommend

I would finish the current pipeline-recovery/health work first rather than introducing another architectural rewrite while known calculations are failing.

Immediately after that, I would create one OpenSpec change along the lines of:

**`sabermetric-foundation`** or **`metric-formula-consolidation`**.

Its first job should **not** be writing formulas.

Its first job should be producing an inventory like:

```text
metric
grain
current implementation(s)
canonical input components
formula source
constants
constant source
descriptive/PIT
SQL owner
Python duplicate?
validation evidence
status
```

Then we attack the highest-value inconsistencies first.

**My first three targets would be wOBA/wRC+, FIP/xFIP, and RE24/WPA.**

Those give us offense, pitching and contextual run value, and force us to solve the constants/PIT architecture correctly.

Only after those are rock-solid would I move outward into SIERA, BsR, framing, pitch metrics and more exotic calculations.

---

## The architecture I would target

```text
                         ┌─────────────────────┐
                         │ metric registry     │
                         │ definition/citation │
                         │ grain/null/PIT      │
                         └──────────┬──────────┘
                                    │
                                    │ governs
                                    ▼
┌────────────┐     ┌─────────────────────────────┐
│ raw source │ ──▶ │ core canonical facts        │
└────────────┘     │                             │
                   │ game                        │
                   │ play / plate appearance     │
                   │ pitch                       │
                   │ stat constants/reference    │
                   └──────────────┬──────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────┐
                   │ gold descriptive metrics    │
                   │ canonical versioned SQL     │
                   │                             │
                   │ AVG / OBP / SLG / wOBA      │
                   │ FIP / xFIP / RE24 / WPA     │
                   │ season/career/team/etc.     │
                   └──────────────┬──────────────┘
                                  │
                                  ▼
                   ┌─────────────────────────────┐
                   │ DuckDB feat.*               │
                   │ point-in-time transformations│
                   └──────────────┬──────────────┘
                                  │
                  ┌───────────────┴────────────────┐
                  ▼                                ▼
          Python ML / sims                mlb_research.stats
          predictions                     researcher API
```

And later:

```text
versioned SQL
     +
SQLMesh
     =
incremental / audited / lineage-aware Gold builds
```

rather than:

```text
SQLMesh = formula library
```

That distinction is important.

**So my answer is: stay with SQL for the canonical sabermetric warehouse, keep SQLMesh as the eventual transformation manager, retain Play/Pitch separation, keep Core atomic, put reusable calculated stats in Gold, put pregame rolling versions in `feat.*`, and use Python only where Python genuinely wins.**

The most valuable work now is **consolidating the formulas and replacing fixed magic constants with governed, season-aware data**, not adding another framework or another hundred metrics. That will make the project simpler *and* more statistically trustworthy.
