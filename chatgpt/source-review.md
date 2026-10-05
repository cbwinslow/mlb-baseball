Yes. I did a fairly deep pass: I reviewed the current `cbwinslow/mlb-baseball` codebase, then searched roughly 50 candidates across sabermetric engines, MLB data providers, market-data clients, and recent baseball-ML projects, and then re-checked the strongest candidates against current PyPI/GitHub state.

The conclusion is actually encouraging: **we should not tear apart the architecture you already have.** The `raw → core → gold → DuckDB feat.*` structure is fundamentally the right architecture for this project. What we should do now is make it much more systematic about how third-party libraries are used.

The key distinction I would introduce is:

> **Libraries acquire/reference/validate data. Our SQL owns reproducible metrics. DuckDB owns point-in-time ML features. Python owns statistical models and simulations.**

That gives us the best of all worlds.

## The most useful libraries I found

| Library | Best use for us | Current state | Recommendation |
|---|---|---:|---|
| **Fungo** | FanGraphs, Guts!, park factors, Statcast, BRef, Retrosheet, MLB API | 2.0.0, July 2026 | **KEEP + EXPAND** |
| **SportsDataverse** | MLB/Savant datasets, RE24/WPA/xStats/advanced reference data | 0.1.4, Sept. 2026 | **ADD AS OPTIONAL REFERENCE SOURCE** |
| **pyhomerun** | wOBA, wRC+, FIP, xFIP, RE24, log5, Pythagorean etc. | 0.8.0, July 2026 | **ADD AS TEST ORACLE** |
| **saberkit** | wOBA/wRC+, FIP/xFIP, plus/minus stats, season contexts | 0.1.0, Aug. 2026 | **ADD AS SECOND TEST ORACLE / WATCH** |
| **python-mlb-statsapi** | Modern typed MLB StatsAPI client | 1.1.2, Sept. 29 2026 | **SPIKE / EVALUATE** |
| **polars-baseball** | Async, typed, Polars-native multi-provider ingestion | 0.21.1, Aug. 2026 | **BENCHMARK / WATCH** |
| **pybaseballstats** | Savant plus especially Umpire Scorecards | 0.6.4, Sept. 2026 | **TARGETED CONNECTOR ONLY** |
| **pybaseball** | Existing Statcast/BRef paths | latest PyPI release is old | **KEEP, DON'T EXPAND** |
| **Open-Meteo client** | Historical + forecast weather | actively maintained | **STRONG NEW DATA SOURCE** |
| **Polymarket official SDK** | Streaming/orderbook/data API if needed later | 0.12.0 | **DON'T REPLACE DIRECT REST YET** |

There are several very interesting developments here that did not really exist when some of the project's earlier dependency decisions were made.

### Fungo remains one of our best choices

You already made a good decision adopting **Fungo**. Version 2.0.0 was released in July 2026 and is explicitly designed as a lightweight baseball research data-access layer. It covers Statcast, MLB Stats API, FanGraphs, Baseball-Reference, Retrosheet, and Lahman while deliberately returning fairly raw structures rather than imposing its own DataFrame architecture. [PyPI](https://pypi.org/project/fungo/?utm_source=chatgpt.com)

That fits our `raw` philosophy almost perfectly.

In particular, I would continue expanding Fungo for:

- FanGraphs Guts constants
- FanGraphs park factors
- FanGraphs leaderboards
- depth charts / RosterResource information
- FanGraphs identifiers ↔ MLBAM identifiers
- advanced pitcher metrics that we want as **external references**
- Retrosheet/Lahman convenience access where useful

It is better to let Fungo maintain those HTTP interfaces than to create more project-specific scrapers.

---

## `pyhomerun` is probably the most interesting sabermetric library I found

This is exactly the kind of library you were asking about.

**pyhomerun 0.8.0** was released July 29, 2026. It is MIT licensed, typed, zero-dependency, and provides pure functions for:

AVG, OBP, SLG, OPS, ISO, BABIP, wOBA, wRAA, wRC, wRC+, ERA, FIP, xFIP, ERA+/-, OPS+, BB%, K%, Pythagorean expectation, log5, RE24/run values, and more. [PyPI](https://pypi.org/project/pyhomerun/0.8.0/?utm_source=chatgpt.com)

That sounds like an argument for replacing our SQL.

I **would not do that**.

Instead, pyhomerun is nearly perfect as an **independent calculation oracle**.

For example:

```text
our SQL wOBA
       ↓
compare
       ↓
pyhomerun.woba(...)
       ↓
compare
       ↓
FanGraphs published result
```

That is much stronger evidence than:

```text
our SQL implementation
       ↓
our Python implementation
```

because two implementations we wrote ourselves can reproduce the same misunderstanding.

There is one important limitation: pyhomerun explicitly ships representative modern constants for league-dependent calculations and tells users to inject the appropriate season-specific wOBA/FIP constants for exact historical work. [PyPI](https://pypi.org/project/pyhomerun/0.8.0/?utm_source=chatgpt.com)

That is actually useful to us because **we already ingest FanGraphs Guts by season**.

So we can do:

```python
pyhomerun.woba(..., weights=weights_from_gold_fangraphs_guts_1927)
```

and compare it with our own 1927 SQL result.

That is excellent validation architecture.

---

## `saberkit` is another very promising validation engine

`saberkit` is brand new—0.1.0 from August 27, 2026—so I would not make production depend on it yet.

But its design is fascinating.

It implements the normal rate stats plus:

- OPS+
- sOPS+
- tOPS+
- ERA+
- wRAA
- wRC / wRC+
- ERA-
- FIP-
- xFIP-
- league percentile rankings

and its core calculation engine is implemented in Rust, exposed to Python with PyO3/Arrow. [PyPI](https://pypi.org/project/saberkit/?utm_source=chatgpt.com)

Even more interesting: its league contexts are derived from Retrosheet rather than simply copying FanGraphs's constants.

That creates an extremely useful three-way validation structure:

```text
                 FanGraphs Guts
                      │
                      │
project SQL ──────────┼──────── pyhomerun
     │                │
     │                │
     └──────── saberkit / Retrosheet-derived context
```

If all three agree within expected tolerance, we have very strong confidence.

Because `saberkit` is only 0.1.0, however, it belongs in `dev`/validation—not our runtime ingestion stack.

---

# SportsDataverse may be the biggest new data-source opportunity

This one deserves investigation.

**SportsDataverse 0.1.4** was released September 1, 2026, is MIT licensed, and is actively maintained. Its Python package now has substantial MLB support. [PyPI](https://pypi.org/project/sportsdataverse/?utm_source=chatgpt.com)

The MLB side includes datasets/interfaces around things like:

- play-by-play
- pitches
- RE24 matrices
- win-expectancy tables
- WPA
- expected hitting statistics
- OAA
- catcher framing
- xERA
- Stuff+
- Command+
- Baseball Savant
- MLB Stats API

This is **not necessarily data we blindly import into gold**.

It is more valuable as:

```text
SportsDataverse
     ↓
external/reference
     ↓
compare against our result
```

For example:

```text
core.play
   ↓
our SQL
   ↓
gold.run_expectancy_24

         VS

SportsDataverse RE24
```

That could immediately strengthen our validation story.

And where SportsDataverse provides something genuinely difficult to recreate—Stuff+, Command+, expected-stat models, OAA—we could retain those as externally sourced metrics instead of pretending they are our calculations.

I'd make it an optional source extra rather than a foundational dependency because its wheel is relatively large and it covers many sports we do not need.

Something like:

```toml
[project.optional-dependencies]
reference = [
    "sportsdataverse>=0.1",
    "pyhomerun>=0.8",
    "saberkit>=0.1",
]
```

That would be clean.

---

# There is now a much more modern MLB Stats API client

I found **`python-mlb-statsapi` 1.1.2**, released September 29, 2026.

It is significantly more modern than the `MLB-StatsAPI` library currently in the repo:

- Pydantic models
- typed snake_case fields
- synchronous client
- asynchronous client
- explicit HTTP timeouts
- retries
- session ownership
- documented public API compatibility
- deterministic offline test suite
- separate live integration tests [PyPI](https://pypi.org/project/python-mlb-statsapi/1.1.2/?utm_source=chatgpt.com)


That deserves a formal spike.

I would **not replace our existing MLB connector immediately**, though.

Our ingestion system has an important property that a convenient typed SDK can accidentally destroy:

> raw data should remain source-faithful and replayable.

Pydantic models are fantastic for application code but can normalize away undocumented source fields that later become valuable.

There is also a source-rights consideration: although the library code is MIT licensed, its own documentation explicitly frames MLB data usage as educational/non-commercial. [PyPI](https://pypi.org/project/python-mlb-statsapi/1.1.2/?utm_source=chatgpt.com) Given that your project specifically wants a commercially usable research platform, that warrants a rights review before we switch.

So my verdict is:

**benchmark it against the existing connector, but do not migrate yet.**

---

# `polars-baseball` is another project worth watching closely

This surprised me.

`polars-baseball` has already reached **0.21.1** and is a typed, async-first, Polars-native baseball data SDK covering:

Statcast, Baseball Savant, FanGraphs, Baseball-Reference, Lahman, Retrosheet, MLB Stats API, and player ID workflows. [PyPI](https://pypi.org/project/polars-baseball/?utm_source=chatgpt.com)

It includes caching, explicit HTTP resource management, retries, concurrency controls, and native Polars output.

Architecturally, it looks attractive:

```text
async HTTP
   ↓
Polars
   ↓
Parquet / Arrow
   ↓
DuckDB
```

But I still would **not adopt it into the main pipeline right now**.

It overlaps enormously with:

```text
pybaseball
fungo
MLB-StatsAPI
our own connectors
```

and it is still beta with one maintainer.

Instead, I'd create a benchmark issue:

```text
fungo vs pybaseball vs polars-baseball
```

for the same 1-day / 1-week / full-season Statcast and FanGraphs requests.

If Polars-baseball turns out dramatically faster or more reliable, we have evidence for changing.

---

# `pybaseballstats` gives us one particularly interesting source: umpires

`pybaseballstats` has seen a lot of work in 2026; version 0.6.4 was released September 21. [PyPI](https://pypi.org/project/pybaseballstats/?utm_source=chatgpt.com)

It is explicitly trying to modernize parts of the `pybaseball` ecosystem.

I would **not** use it for BRef/FanGraphs because those endpoints have already been disrupted by anti-scraping changes.

But its **Umpire Scorecards** support is intriguing.

Umpire tendencies could become legitimate pregame features:

```text
called-strike tendency
zone expansion
run impact
home/away tendency
pitcher/batter handedness interactions
```

That is much more interesting to our ML project than duplicating another Statcast downloader.

So:

> `pybaseballstats` → evaluate specifically for an `umpire_scorecard` connector.

---

# Keep pybaseball, but stop building new architecture around it

`pybaseball` remains extremely useful, and we already depend on it.

But its latest PyPI release remains from 2023 and its own project warns that releases can lag. [PyPI](https://pypi.org/project/pybaseball/?utm_source=chatgpt.com)

Our current strategy is therefore right:

```text
pybaseball
├── Statcast where proven
├── BRef where proven
└── validation/reference data
```

but:

```text
DO NOT
└── make every new source depend on pybaseball
```

Fungo and modern source-specific clients give us better alternatives.

---

# I would add weather

The official Open-Meteo Python client is a surprisingly strong fit.

It provides historical weather going back to **1940** and can move data efficiently into NumPy, pandas, or Polars. [GitHub](https://github.com/open-meteo/python-requests?utm_source=chatgpt.com)

For baseball, that gives us:

```text
temperature
humidity
wind speed
wind direction
pressure
precipitation
cloud cover
```

Weather can interact with:

```text
park × temperature
park × wind direction
pitcher × temperature
HR rate × air density
run scoring × weather
```

Your existing park/environment work already heads in this direction.

But for ML we need **two distinct datasets**:

```text
observed_weather
forecast_weather
```

Observed weather is useful for historical explanation.

Forecast weather is what a pregame model would actually know.

Do not train on final observed weather and pretend that feature existed six hours before first pitch.

---

# I would NOT replace your direct Polymarket/Kalshi reads yet

The official Polymarket SDK has changed dramatically this year. `polymarket-client` is now the official unified Python SDK, currently around 0.12, with sync/async clients and typed models. [GitHub](https://github.com/Polymarket/py-sdk/blob/main/README.md?utm_source=chatgpt.com)

But version 0.10 introduced breaking changes, which is exactly the risk of a young 0.x API. [GitHub](https://github.com/Polymarket/py-sdk/releases?utm_source=chatgpt.com)

Your project only needs public market observations right now.

Therefore this is simpler:

```text
HTTP endpoint
    ↓
verbatim response
    ↓
raw.polymarket_*
```

than:

```text
HTTP
 ↓
SDK
 ↓
SDK normalization
 ↓
our normalization
```

The official SDK becomes attractive when we need:

- websocket market streams
- orderbook updates
- deeper liquidity information
- authenticated trading
- live execution

That's Phase C-type work.

---

# The bigger architectural decision: do not move sabermetrics into Python

After this search, I'm even more convinced of this.

For **database statistics**, SQL is the correct canonical implementation.

Example:

```sql
SUM(hr)
SUM(bb)
SUM(hbp)
SUM(so)
SUM(outs)
```

then:

```text
FIP
```

is an aggregation over relational data.

SQL is excellent at that.

Likewise:

```text
AVG
OBP
SLG
OPS
BABIP
ISO
K%
BB%
CSW%
wOBA
wRAA
wRC+
FIP
xFIP
RE24
WPA
park factors
rolling form
platoon rates
pitch mix
```

The Python packages should **validate those calculations rather than own them**.

That gives you:

```text
                       ┌──────── pyhomerun
                       │
raw → core → SQL metric├──────── saberkit
                       │
                       ├──────── baseballr
                       │
                       └──────── FanGraphs/BRef/SportsDataverse
```

That is substantially stronger than merely importing:

```python
from some_package import woba
```

and hoping the implementation remains stable.

---

# One immediate metric problem I would fix

Your repository inspection exposed a concrete example of why this matters.

You already have:

```text
gold.fangraphs_guts
```

containing season-specific FanGraphs constants.

But some existing calculations still use fixed approximations—for example the existing starter FIP implementation documents a fixed modern FIP constant, and analogous historical wOBA calculations have had fixed-weight limitations.

We can now fix that properly.

Instead of:

```text
FIP constant = 3.10 forever
```

use:

```text
season
 │
 ├── wBB
 ├── wHBP
 ├── w1B
 ├── w2B
 ├── w3B
 ├── wHR
 ├── wOBA scale
 ├── league wOBA
 ├── league R/PA
 ├── FIP constant
 └── league HR/FB
```

I would make this a first-class relation:

```text
gold.league_context
```

or perhaps:

```text
ref.league_context
```

with grain:

```text
season × league
```

Then every context-dependent sabermetric joins it.

That solves an entire class of problems at once.

---

# Preserve components, not merely calculated rates

This is one of the most important design principles for the database.

Do **not** store only:

```text
player
wOBA = .371
K%   = 19.2%
BB%  = 11.5%
```

Store the components:

```text
PA
AB
H
1B
2B
3B
HR
BB
IBB
HBP
SF
SO
```

plus the derived metric.

Why?

Suppose we want 30-day wOBA.

This is wrong:

```text
AVG(game_wOBA)
```

The correct approach is:

```text
SUM(weighted event numerators)
──────────────────────────────
SUM(wOBA denominator)
```

That applies to almost every rate statistic.

It also lets us construct arbitrary:

```text
7d
14d
30d
60d
season-to-date
career
home
away
vs LHP
vs RHP
night
day
park
pitch type
count
```

without re-ingesting anything.

---

# I would organize the metric database around a grain ladder

Your current play/pitch decoupling is absolutely worth keeping.

In fact, I would lean harder into it:

```text
core.pitch
   ↓
pitch metrics
   ↓
plate appearance

core.play
   ↓
PA metrics
   ↓
player-game
   ↓
team-game
   ↓
player-season
   ↓
team-season
```

Then separately:

```text
historical metric
       ↓
point-in-time transformation
       ↓
ML feature
```

That last distinction matters tremendously.

Aaron Judge's:

```text
2026 season wOBA
```

is a research statistic.

His:

```text
wOBA over games strictly before
2026-07-14 19:05 ET
```

is an ML feature.

They should not be conflated.

---

# The feature database should contain more than simple rolling averages

The baseball-ML projects I reviewed reinforce that good feature engineering generally includes multiple temporal representations rather than one aggregate.

For the same underlying statistic:

```text
wOBA_7d
wOBA_14d
wOBA_30d
wOBA_60d
wOBA_season
wOBA_prior_season
wOBA_ewma
wOBA_slope_30d
wOBA_std_30d
wOBA_zscore_vs_player
```

The model can determine which time horizon matters.

For a pitcher:

```text
velo_7d
velo_30d
velo_season
velo_delta_30d
spin_delta_30d
release_height_delta
extension_delta
pitch_mix_delta
CSW_30d
xwOBA_allowed_30d
```

A velocity drop by itself may be useful.

But:

```text
current velo - pitcher baseline
```

is usually much more informative.

---

# Small-sample metrics need shrinkage

This is an area where baseball projects often go wrong.

Suppose a batter is:

```text
4-for-7 vs LHP
```

A raw .571 average should not be treated like a true-talent .571 hitter.

Instead of arbitrary filtering like:

```sql
WHERE pa >= 25
```

we should eventually support empirical-Bayes / hierarchical shrinkage:

```text
observed platoon rate
        +
league/player prior
        ↓
posterior estimate
```

A classical baseline worth implementing is **Marcel**:

- recent seasons weighted more heavily
- regression toward league average
- age adjustment
- playing-time/sample-size adjustment

Modern baseball projection projects still use Marcel as the baseline that more sophisticated approaches have to beat. [GitHub](https://github.com/nielsjsc/LSTMLB?utm_source=chatgpt.com)

That's perfect for us.

Before calling a neural network clever, make it beat:

```text
Marcel
Elo
log5
Pythagorean
logistic regression
```

out of sample.

---

# For pitch quality, we can build our own Stuff+/Command+ later

This is an especially fertile area for your project.

Recent public Stuff+ projects use features such as:

```text
velocity
spin
induced vertical break
horizontal break
extension
release height
release side
spin axis
arm angle
vertical approach angle
horizontal approach angle
pitch-to-primary-pitch differentials
```

and deliberately separate physical pitch quality from location/context. One recent implementation uses separate pitch-type models and combines modeled whiff/contact outcomes into run value. [GitHub](https://github.com/TDFelton/stuff_plus?utm_source=chatgpt.com)

That suggests a clean future decomposition:

```text
Stuff+
  = physical pitch characteristics

Command+
  = intended/effective location quality

Pitching+
  = Stuff + Command + count/context
```

We should ingest publisher Stuff+/Command+ values where legally usable for **validation**, while eventually building our own named version:

```text
project_stuff_plus_v1
```

That distinction matters.

Never label our homemade model simply `Stuff+` if it is not the publisher's formula.

---

# Same warning for WAR

I would **not** make "calculate WAR" a single generic utility.

WAR is a methodology family, not one universally agreed formula.

Baseball-Reference and FanGraphs make different methodological choices.

We should preserve:

```text
bref_war
fangraphs_war
```

as external values where permitted.

If we eventually build ours:

```text
mlb_research_war_v1
```

with explicit:

```text
batting runs
baserunning runs
fielding runs
position adjustment
league adjustment
replacement runs
runs-per-win
```

That is scientifically much cleaner.

---

# The metrics I would prioritize for ML

I wouldn't try to implement another 150 metrics just because we can.

For winning games / finding market disagreement, I would build the metric inventory around a few strong feature families:

| Family | Examples |
|---|---|
| Offense | wOBA, wRC+, ISO, BABIP, K%, BB%, xwOBA, barrels, HardHit%, launch angle |
| Starter | FIP, xFIP, K-BB%, CSW%, velo, pitch mix, Stuff+, xwOBA allowed |
| Bullpen | FIP, K-BB%, workload 1/3/7d, leverage usage, availability, fatigue |
| Defense | OAA, catcher framing, throwing/baserunning prevention |
| Baserunning | BsR components, sprint speed, SB/CS, extra-base advancement |
| Context | park factor, temperature, wind, humidity, roof/surface, umpire |
| Team strength | Elo, log5, Pythagenpat, BaseRuns, run differential |
| Matchup | handedness, pitch-type hitter performance, pitcher arsenal × lineup weaknesses |
| Trend | rolling windows, EWMA, slope, variance, deviation from personal baseline |
| Market | implied probability, vig/fees, consensus, dispersion, spread, liquidity, price movement |
| Reliability | PA/BF/pitch counts, posterior uncertainty, missingness/coverage indicators |

The last family is easy to overlook.

Give the model both:

```text
woba_30d = .410
```

and:

```text
pa_30d = 28
```

because `.410 over 28 PA` means something quite different from `.410 over 140 PA`.

---

# The market side needs to become a feature source too

You are already doing something particularly valuable: preserving **time-stamped Kalshi/Polymarket snapshots rather than only the final market price**.

Keep expanding that.

Eventually I would derive:

```text
market_prob_open
market_prob_24h
market_prob_6h
market_prob_1h
market_prob_close

market_move_open_to_1h
market_move_6h_to_1h

market_spread
market_depth
market_volume
market_liquidity

book_consensus_prob
market_dispersion
```

The point is not only:

```text
Can our model predict who wins?
```

It is:

```text
P(model) - P(market)
```

and ultimately:

```text
Does disagreement contain information
after calibration, vig, fees, liquidity
and execution are considered?
```

A recent open MLB probabilistic modeling project follows exactly this philosophy: temporal validation, Brier/ECE calibration, probability calibration, SHAP/importance, and explicit evaluation against logged Kalshi/Odds API market prices rather than accuracy alone. [GitHub](https://github.com/NATEBAGS/mlb-probabilistic-models/blob/main/README.md?utm_source=chatgpt.com)

That's the right benchmark for our Engine.

---

# I would expand the ML library set—but only after the feature database is solid

You already have XGBoost and scikit-learn.

The strongest additions are:

**CatBoost** is production/stable and current; 1.2.10 was released in February 2026. It is particularly useful when we have categorical baseball variables and nonlinear interactions. [PyPI](https://pypi.org/project/catboost/?utm_source=chatgpt.com)

**LightGBM 4.7.0** was released in July 2026 and now has Polars/Arrow integrations. It gives us another high-performance tabular challenger. [PyPI](https://pypi.org/project/lightgbm/?utm_source=chatgpt.com)

**PyMC 6.3.2** was released in September 2026. This is the library I would use for true-talent estimation, shrinkage, aging curves, platoon effects and other hierarchical baseball problems. [PyPI](https://pypi.org/project/pymc/?utm_source=chatgpt.com)

**Optuna 5.0** is current as of September 2026 and is a very good fit for your eventual feature/hyperparameter search harness. [PyPI](https://pypi.org/project/optuna/?utm_source=chatgpt.com)

**SHAP 0.52** remains production/stable and is valuable for explaining why a model disagrees with the market. [PyPI](https://pypi.org/project/shap/?utm_source=chatgpt.com)

But those should be optional/modeling dependencies—not dumped into the core ingestion package.

---

# I also think Polars now deserves reconsideration

You previously had Polars in the "not yet justified" category.

The ecosystem has changed.

Polars 1.44.2 was released September 9, 2026, and 2.0 release candidates are already available. [PyPI](https://pypi.org/project/polars/?utm_source=chatgpt.com)

And now:

```text
sportsdataverse → Polars
polars-baseball → Polars
Open-Meteo → Polars-compatible
LightGBM → Polars-compatible
DuckDB ↔ Arrow ↔ Polars
```

That makes it increasingly attractive as the **Python analytical frame**, while SQL remains canonical.

I would still not rewrite pandas code simply because Polars exists.

But new high-volume research code could reasonably prefer:

```text
DuckDB ↔ Arrow ↔ Polars
```

with pandas at compatibility boundaries.

---

# Pandera has also reached the point where it could be useful

Pandera 0.33.1 was released September 1 and supports pandas, Polars, PyArrow, Ibis and other frame systems. [PyPI](https://pypi.org/project/pandera/?utm_source=chatgpt.com)

It would be useful at the boundary:

```text
external Python library
        ↓
DataFrame
        ↓
Pandera schema
        ↓
raw loader
```

For example:

```text
Statcast must contain:
game_pk
game_date
pitcher
batter
events
description
```

before ingestion proceeds.

We don't need Pandera to validate Postgres—that's what SQL constraints/tests are for.

It validates **Python dataframe contracts**.

---

# SQLMesh still has a role—but not as a sabermetric library

SQLMesh/dbt solve a different problem.

They are useful for:

```text
dependency graphs
incremental models
backfills
audits
lineage
environment promotion
```

They do **not** make:

```sql
13*HR + 3*(BB+HBP) - 2*K
```

more correct.

So I would keep the decision split:

```text
Formula
    ↓
SQL

Orchestration/versioning/incrementality
    ↓
SQLMesh
```

And because Phase A is already close to working, I would **not stop everything and migrate all SQL into SQLMesh right now**.

When the metric layer stabilizes, moving well-defined gold/feature models under SQLMesh becomes much easier.

---

# The architecture I recommend

This is where I think the project should end up:

```text
                       DATA PROVIDERS
                              │
          ┌───────────────────┼────────────────────┐
          │                   │                    │
       Fungo            MLB StatsAPI       SportsDataverse
    pybaseball           Retrosheet          Open-Meteo
          │                   │                    │
          └───────────────────┴────────────────────┘
                              │
                              ▼
                         raw.*
                  source-faithful/replayable
                              │
                              ▼
                         core.*
                 players / teams / games
                    plays / pitches
                              │
                              ▼
                  deterministic SQL
                              │
               ┌──────────────┴──────────────┐
               ▼                             ▼
            gold.*                     reference.*
       research metrics            external/tie-outs
               │
               │                      pyhomerun
               │                      saberkit
               │                      SportsDataverse
               │                      FanGraphs/BRef
               │
               ▼
       point-in-time builder
               │
               ▼
        DuckDB feat.*
               │
      ┌────────┼────────┐
      ▼        ▼        ▼
   sklearn   XGBoost  CatBoost
   LightGBM   PyMC    simulations
      │
      ▼
walk-forward predictions
      │
      ▼
market comparison
      │
      ▼
calibration / CLV / edge
```

**That is the structure I would build around.**

And it is gratifyingly close to what the repo already has.

---

# What I think we should do next

I would not launch a broad rewrite. I'd make the next development batch very focused:

1. **Create a `library-evaluation` OpenSpec/change** covering `pyhomerun`, `saberkit`, SportsDataverse, `python-mlb-statsapi`, `polars-baseball`, `pybaseballstats`, Open-Meteo, Pandera and Polars. Each gets `adopt / optional / oracle / watch / reject`, with license, maintenance, overlap, unique capability and source-rights notes.

2. **Build `league_context` and eliminate fixed historical constants.** Wire year-specific wOBA/FIP/xFIP context into the metrics that currently use modern defaults. Validate the results independently with pyhomerun + saberkit + FanGraphs.

3. **Turn the existing metric catalog into a real validation contract.** I would add metadata along the lines of `formula_version`, `constant_source`, `validation_oracle`, `validation_tolerance`, `availability`, `point_in_time_safe`, and `minimum_sample/reliability_method`.

4. **Add new data only where it creates real signal:** Open-Meteo weather, Umpire Scorecards, SportsDataverse reference metrics, and eventually lineup/depth-chart information. Do not add another source that merely duplicates Statcast for the sake of table count.

5. **Build a metric/feature matrix from components.** For each important statistic, preserve numerator/denominator and generate point-in-time `7d/14d/30d/60d/EWMA/prior-season` versions in DuckDB. Add sample-size and uncertainty fields beside every important rate.

6. **After that**, add CatBoost + LightGBM + Optuna as model challengers and PyMC for shrinkage/true-talent estimation. Every challenger goes through the walk-forward harness and must beat simple baselines on **log loss/Brier/calibration**, then be compared against market probability/closing-line performance—not merely classification accuracy.

Of all of these, **#2 is the one I would actually start coding first**. You already possess the raw ingredients: your `core.play`, metric catalog, FanGraphs Guts ingestion, existing FIP/wOBA implementations, and tie-out infrastructure. Fixing the season-context layer improves the scientific correctness of the entire database without creating another subsystem.

And after doing this search, I think the original question from our previous discussion is much easier to answer:

> **Yes, keep the sabermetrics in SQL. Do not replace them with a Python library. But absolutely use modern Python/R sabermetric libraries as independent calculation engines to test, verify, and improve that SQL.**

That combination is stronger—and considerably more reusable—than either SQL-only or Python-only.
