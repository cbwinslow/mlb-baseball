# Modeling, backtesting, feature store & real-time betting — planning session

**Status:** research / planning input, not an approved design. Captured
2026-09-04. Kept for reference; nothing here is a contract on its own.

This is a transcript of a planning conversation covering: an objective project
review and product sequencing, the model ladder (Elo → logistic → run
distributions → Monte Carlo → boosted trees → hierarchical player models →
plate-appearance simulator → props → market residual → neural nets),
time-ordered backtesting, the point-in-time feature store, real-time in-game
feature updates, and historical event-log replay. Formulas and code are as they
were written.

**What already made it into the project.** The strategic conclusions were
adopted into `openspec/project.md` through the `two-product-model` change
(archived 2026-09-07), which names this session as one of its three inputs:

- the phased ladder — Phase A public platform → Phase B internal Engine →
  Phase C consumer site;
- the **v1.1** definition — a point-in-time feature store (append-only `feat.*`
  snapshot tables + as-of retrieval + registry + leakage tests), the
  walk-forward backtest harness, and one reference baseline (Elo v2) + model
  card;
- **Phase B** item 1 — the `meta.metric` registry table.

**What is still just input here.** The concrete designs below — the `feat.*` and
`live.*` schema sketches, the walk-forward fold code, the leakage battery, the
fill simulator — are meant to seed the v1.1 OpenSpec changes when they are
written (the NEXT roadmap item), not to be built as-is. Sections 5–6 (real-time
/ live betting) map to Phase C and are parked.

---

## 1. Fresh take on the project

### User

> ok can we pick up where we left off? we were going through the plan that we made with one of our skills... also can you weigh in on our progress.... putting aside all of the guardrails and plans that we made... i want you to be objective on this... please review what we have so far and tell me if you would make any changes... in general i just want to make a detailed research database for researching mlb data and building ml models using it.... i want other people to be able to download it and bootstrap it and then use it on thier systems to conduct their own research... think of baseballr and pybaseball and how useful those tools are... i want this to be a fully stocked database that has tons of views to dispaly the data for various slices of the data and to have researchers and analyst be able to export taht data or access it using an api maybe... (that part i need your guidance on)... and i want the baseball to come with sabremetrics views/tables and the python code to calculate all of these already proven metrics for various players (and i want to add my own metrics too that are based on logic and research and that we have all of the math for and we prove that the code works and that the metrics are rooted in logic... there are a ton of different metrics out there that have already been researched as shown in tom tangos book as well as sabremetrics material as well as fangraphs, retrosheet, etc.... have published thier research that shows us how to calculate various metrics for different layers of mlb baseball.... things that can be used to build ml models that predict various outcomes... in addition i want to build some ml models using all of the different techniques and have a platform to conduct ml model analysis and to analyze the results and i want to produce valueble insight that would be valuable to people that participate in sports gambling and i want to produce a website that publishes our findings and charge subscriptino fees for the research that we publish... this is a big undertaking and i want this project to be comprehensive and high quality as well... i want to also use the betting sites polymarket and kalshi (prediction markets) as well and find insight all around those sites.... i want to try nd construct parlays as well if possible and research those and try and publish research on what to bet on and show our guidance thats backed by ai insight/research and our database and in general just try to find out ways for others to make money on betting on the mlb... i want to use all avilable data and build models as well as a website that can be a one stop shop for mlb researchers and sports betting enthusiasts... i want to have players/team/season stats made available as well somehow (we have decided to use hugging face for one method but i am open to others)..... so that being said.... pretend that you know nothing about this work we have done and thta you have no other context about the work we have done so far because i want to get a fresh take on how you would build osmething like this and what stack you would use and how we would go about it... im curious if you would even use a database... what are some of the proven ways to be able to predict game winners for example? like what are techniques and ml model types that you would use? what are some of the ways that have been successful and seen real results? we need to do a lot of research on this topic and we also need to be innovative and we also need to be smart about the stack that we use and we should be mindful of existing tools and combine everything that we can to make our lives easier..... another valuable thing would be to try and discover new meaningful metrics... ones that measure various aspects of baseball... there is a ton of data that we can use and we can get creative with the data as well and create new combinations of variables, we can use ratios to center the data too as to not be bound at 0, we can factor our averages of various things like WAR and stuff...., i want to look into various interaction variables that combine multiple metrics that can model non linear effects and interaction effects... just think about all of the different factors that can effect how good a team is...... we can think about what makes a team good and try and quantify that as then test it out using our data.... i want to try and explore goal seeking functions/algorithms that can automatically find new variables/features to use as well, or some that can use brute force and try different things and we see what sticks and then investigate the meaning behind them and we can also try and set up a deep neural network that can capture high dimensoinal interactions that are not apparent or are hidden somewhere in all of that data... also i want to explore individual player analysis and it would be valuable to be able to produce insight on specific players and thier situational performance and to be able to do what the book moneyball is about.... again i want youto give me  a fresh take

### Assistant

Yes—your current direction is fundamentally sound. The project already looks much closer to a serious, reproducible research platform than a typical “sports-picks model”: you have a tested PostgreSQL foundation, documented data contracts and source rights, a grain-based gold layer, proven-metric work, and an explicit decision to freeze the site/model expansion until the research database is usable by outsiders. That is the correct sequencing.

#### Objective progress review

Your strongest accomplishment is that you have stopped treating this as merely a prediction script and started treating it as a **research data product**.

Recent work shows meaningful maturity:

- You have built the beginning of the reusable statistic backbone: batting and pitching relations at game, season, team, and career grains, with rates recomputed from underlying numerators and denominators rather than incorrectly averaged.
- You have a documented provenance, source-rights, export, health-check, migration, and testing culture—not just tables.
- You implemented a conservative export policy: the public-safe bundle is Retrosheet-only, while sources with redistribution constraints remain local-research-only. That separation is essential if this becomes public.
- You have a real testing and CI posture, including isolated databases, migrations, integration coverage, linting, and data-quality checks.
- You correctly paused the public site and prediction ladder so that the research database can become one coherent, bootstrapable product first.
- Your current active delivery plan—Parquet exports, Hugging Face publication, a DuckDB-in-browser experience, a Python loader, and a Marimo notebook—is exactly the missing researcher-facing layer. It is planned, not yet shipped.

My blunt assessment: **the engineering quality is ahead of the product delivery surface.** You have a sophisticated internal platform, but an outside researcher still cannot yet do the simple thing you want them to do:

```bash
pip install mlb-research
mlb-research download --dataset batting-season
duckdb
SELECT * FROM batting_season WHERE season = 2025;
```

That is now the highest-value gap—not more metrics, more ingestion sources, a neural net, or a web application.

#### What I would change

I would not replace your database-first approach. I would sharpen the architecture and narrow the sequence.

##### Keep PostgreSQL—but do not distribute PostgreSQL

Use PostgreSQL as the canonical operational and integration database:

| Layer | Recommended technology | Purpose |
|---|---|---|
| Canonical database | PostgreSQL | Identity resolution, normalized entities, ingestion state, provenance, access control, relational joins, operational refreshes |
| Transformation layer | Your existing SQL files now; evolve toward SQLMesh/dbt only when its production-writing path is proven | Repeatable, tested gold marts and semantic metrics |
| Research distribution | Partitioned Parquet | Low-cost public artifacts, reproducibility, downloads |
| Local analyst engine | DuckDB | Fast queries over downloaded Parquet with zero server setup |
| Python interface | `mlb-research` package | Dataset installer, query helpers, schema catalog, version pinning |
| Public query interface | DuckDB-WASM first; API second | Let users explore data without operating your infrastructure |
| Website | Astro/Cloudflare later | Publish research, model reports, methodology, and dashboards—not the data warehouse itself |

PostgreSQL is the right canonical store because it gives you correctness, constraints, repeatable transformations, and a strong internal API boundary. But Parquet plus DuckDB is the right **distribution format** because a researcher can download only the tables they need, query locally, and avoid bootstrapping a multi-gigabyte Postgres instance. PostgreSQL is primarily optimized for transactional workloads, whereas DuckDB/Parquet is a very strong low-friction analytical delivery combination.

##### Make the product a “research kit”

Your external product should not initially be “a giant database dump.” It should be a versioned, documented set of **research-ready marts**:

1. **Core public backbone**
   - Games, teams, players, parks, seasons, schedules, player identifiers
   - Retrosheet-derived play, batting, pitching, and baserunning tables
   - Game, player-game, team-game, player-season, team-season, and career grains

2. **Metric packages**
   - Standard batting/pitching/fielding tables
   - Run expectancy, WPA, RE24, leverage, park factors, platoon splits
   - Statcast-derived tables only when source terms permit their redistribution
   - Each metric needs definition, formula, source lineage, grain, assumptions, and tests.

3. **Feature packages**
   - Strictly point-in-time feature tables for game predictions
   - Examples: `features_game_pregame_v1`, `features_team_form_30d_v1`, `features_starter_context_v1`
   - Never let a feature table quietly blend postgame data with pregame information.

4. **Research artifacts**
   - Marimo notebooks that reproduce a published analysis.
   - Data dictionaries generated from table contracts.
   - A small set of canonical SQL recipes.
   - A changelog with dataset version, rows, date coverage, source revisions, and breaking changes.

The distinction matters: researchers should be able to reproduce *your* published result, modify an input, and prove whether their result changed for a legitimate reason.

##### Do not make a public API the first priority

Build in this order:

1. Parquet exports and manifests.
2. DuckDB loader and Python package.
3. DuckDB-WASM browser querying for small curated tables.
4. A narrow, cached, read-only API for website use cases.
5. Authenticated subscription APIs only after you know which requests people actually need.

An early general API becomes expensive: quotas, abuse prevention, caching, authentication, schema versioning, reliability, and source-rights enforcement. Your downloadable Parquet catalog will serve analysts better and more cheaply at this stage.

#### Modeling and betting reality

The right target is not “predict winners.” It is to estimate a **well-calibrated probability distribution** before the market closes:

\[
P(\text{home win}), \quad P(\text{home runs}), \quad P(\text{away runs}), \quad P(\text{player outcome})
\]

From that distribution, you can derive moneyline, run-line, totals, player props, and parlay probabilities.

##### Start with proven baselines

A baseline is not disposable—it is the standard every later model must beat out of sample.

| Model | Why use it | Role |
|---|---|---|
| Home-field baseline | Tests whether anything adds value | Minimum benchmark |
| Elo with regression to mean | Stable, interpretable team-strength signal | Daily baseline |
| Elo + probable-starter adjustment | Captures a major game-specific driver | Better practical baseline |
| Log5/team strength model | Transparent matchup probability | Useful sanity-check model |
| Logistic regression | Strong, calibrated tabular benchmark | First production challenger |
| Run-distribution model | Produces probabilities for wins, totals, and spreads | Better betting substrate |
| Gradient boosting | Captures nonlinear tabular relationships | Challenger model |
| Hierarchical Bayesian model | Shrinks sparse player/team samples properly | Player, pitcher, and matchup research |
| Monte Carlo simulator | Converts plate-appearance or run distributions to markets | Product layer |

A recent public MLB Elo methodology illustrates the sensible core: team Elo, starting-pitcher adjustment using FIP, home-field adjustment, preseason projection blending, injury adjustments, and probability calibration.

For serious betting research, I would prioritize this model ladder:

1. **Elo + starter + home field** — A transparent and stable daily benchmark.
2. **Projected runs model** — Model expected runs for each team using a Poisson, negative binomial, or hierarchical count framework. Simulate the game to derive moneyline, totals, run-line, and score distributions.
3. **Hierarchical plate-appearance model** — Estimate plate-appearance outcome probabilities conditioned on batter, pitcher, handedness, park, count/state, and time-decayed performance; shrink sparse matchups toward population priors; then simulate innings and games.
4. **Gradient-boosted pregame classifier/regressor** — CatBoost, LightGBM, or XGBoost on point-in-time feature marts. This often deserves priority over deep learning for structured sports tables.
5. **Stacked ensemble only after genuine diversity exists** — Combine models only when their errors differ. A stack of five highly correlated models gives the illusion of sophistication without much information gain.

##### What “successful” really means

Do not evaluate models mainly by winner accuracy. MLB is noisy, and favorites win frequently; a model can show decent accuracy while being badly calibrated and unprofitable.

Use:

- Log loss as the primary probability score.
- Brier score for probability accuracy.
- Calibration curves and calibration slope/intercept.
- Reliability by decile.
- Paired, chronological holdout comparisons against Elo, closing market probabilities, and a home-field baseline.
- Closing-line value, where applicable.
- ROI only after realistic vig, limits, stale lines, unavailable bets, voids, and bankroll rules.
- Maximum drawdown, volatility, sample size, and confidence intervals.

Your existing instinct around historical cutoff discipline, holdouts, and promotion gates is excellent. A model that “wins” in a backtest but sees the confirmed lineup, final starter, postgame rating, or future season aggregate is not merely imperfect—it is invalid.

Also: markets are formidable baselines. The most commercially valuable research might not be “we beat the market every day,” but rather:

- Identifying where your model and market disagree for explainable baseball reasons.
- Detecting stale or internally inconsistent market prices.
- Quantifying lineup, starter, bullpen, rest, and weather moves.
- Producing calibrated probabilities and transparent uncertainty.
- Publishing research that helps users understand why a bet does or does not clear a threshold.

Never frame a public product as a way for others to reliably make money. Frame it as analytical research, probabilistic estimates, documented methodology, and historical performance with risk disclosures.

#### Metrics and discovery

Your goal of finding new metrics is worthwhile, but the process needs to be scientific enough that it does not become feature-mining.

##### Build a formal metric registry

Every metric—existing or novel—should have a record with:

- Metric name and stable version.
- Baseball question it attempts to answer.
- Grain: pitch, plate appearance, game, player-game, team-game, season, etc.
- Formula in math and SQL/Python.
- Required fields and source lineage.
- Population and eligibility thresholds.
- Point-in-time availability.
- Known limitations.
- Unit and integration tests with hand-calculated fixtures.
- Validation benchmark against a published source where feasible.
- Incremental predictive value test.
- Correlation and redundancy checks against existing metrics.

For example, a novel metric should not be admitted because it correlates with wins in one historical sample. It should survive:

1. A baseball mechanism hypothesis.
2. Leakage review.
3. Replication across time periods.
4. Incremental value over known features.
5. Stability across teams, parks, and eras.
6. Interpretability review.
7. A frozen out-of-sample test.

##### Better feature-discovery methods

Use constrained discovery before brute force:

- Domain-designed interactions: batter handedness × pitcher arsenal; park × batted-ball profile; bullpen fatigue × opponent contact profile.
- Nonlinear transforms: splines, percentiles, z-scores within season, empirical-Bayes shrinkage.
- Rolling windows at several horizons: 7, 14, 30, 60 days and season-to-date.
- Recency-weighted statistics rather than arbitrary “last 10 games” splits.
- Hierarchical partial pooling for sparse player splits.
- Regularized interaction selection: elastic net, group lasso, GAMs.
- Gradient boosting plus SHAP/partial-dependence analysis to generate hypotheses.
- Symbolic regression only as a hypothesis generator—not as a production metric factory.
- Feature synthesis libraries only inside strict time-aware folds.

I would avoid unrestricted brute-force ratio generation. It creates denominator pathologies, duplicate features, accidental leakage, and thousands of false discoveries. A metric that emerges from automated search should enter a **candidate registry**, not the gold semantic layer, until it clears your validation protocol.

#### Recommended next milestone

I would make the next deliverable a narrow but complete **Research Database v1 release**, not a broader platform expansion.

##### Definition of done

- One-command bootstrap for a local researcher.
- Versioned Parquet bundles partitioned by season and table.
- Manifest with schema, row counts, sources, licenses/rights, checksum, and build timestamp.
- A `mlb-research` Python package that downloads and opens datasets with DuckDB.
- Five to ten polished gold tables—not hundreds of partially documented ones.
- A public data dictionary and metric registry.
- One Marimo notebook that reproduces a credible analysis end to end.
- One DuckDB-WASM page that queries a small, public-safe subset.
- A benchmark notebook comparing baseline Elo, logistic regression, and one run-distribution model using strictly chronological splits.
- A published model card that reports calibration, log loss, Brier score, limitations, and non-results.

The specific first user-facing bundle should be:

```text
core_player
core_team
core_game
gold_batting_game
gold_pitching_game
gold_batting_season
gold_pitching_season
gold_team_season
gold_run_expectancy
gold_win_probability
gold_leverage_index
```

Then build the pregame feature store and modeling ladder on top of that stable interface.

The project is ambitious, but it is no longer vague. You have the hard and less glamorous pieces—contracts, tests, provenance, data rights, grain discipline, and reproducibility—moving in the right direction. The key change I would make now is ruthless product sequencing: **ship the researcher experience before expanding the metric catalog, prediction models, website, subscriptions, or betting automation.**

---

## 2. Models and techniques

### User

> what models can we use and what techniques should we use?

### Assistant

For your MLB project, use a **model ladder**, not one giant “AI model.” Start with transparent probability baselines, add run-distribution and hierarchical player models, then use gradient boosting and neural networks only where they demonstrably add point-in-time predictive value.

The highest-value objective is not “pick winners”; it is to estimate calibrated probabilities and distributions for games, runs, and player outcomes, then compare those estimates honestly with available market prices. Log loss, Brier score, calibration curves, and time-ordered backtests should determine whether any model survives.

#### Model map

| Goal | Best initial model families | Output |
|---|---|---|
| Game winner | Elo, logistic regression, Bayesian team-strength model, gradient boosting | \(P(\text{home win})\) |
| Team runs / totals | Poisson, negative binomial, bivariate count models, Bayesian run model | Full run distribution |
| Moneyline, total, spread | Monte Carlo from team-run or plate-appearance distributions | Win %, total %, spread %, score probabilities |
| Batter hits, HRs, Ks | Hierarchical Bayesian count/Bernoulli models, negative binomial, zero-inflated models | \(P(\text{over line})\), distribution of outcomes |
| Pitcher Ks, outs, ER | Hierarchical count models plus pitch-count / hook-risk model | Distribution, not just a mean |
| Plate appearance outcomes | Multinomial logistic / hierarchical Bayesian multinomial model | \(P(\text{K, BB, 1B, 2B, 3B, HR, out})\) |
| In-game win probability | Markov chain, state-space model, live gradient boosting | \(P(\text{win} \mid \text{current state})\) |
| Market comparison | Calibrated model ensemble + market-probability benchmark | Model edge, uncertainty, line movement |
| Research and new metrics | GAMs, elastic net, boosted trees, symbolic regression as hypothesis generation | Candidate features, not automatic production metrics |

#### Foundation models first

These models should be in the database and benchmark suite before any deep learning work.

##### 1. Elo with baseball adjustments

Use Elo as your durable game-winner baseline. Basic Elo is simple:

\[
P(\text{home win}) =
\frac{1}{1 + 10^{-(R_{\text{home}} - R_{\text{away}} + H)/400}}
\]

Where:

- \(R_{\text{home}}\) and \(R_{\text{away}}\) are pregame team ratings.
- \(H\) is a learned home-field adjustment.
- Ratings update after each completed game.
- The update weight can vary by margin, recency, postseason, and preseason prior.

For baseball, improve it with:

- Starting-pitcher value relative to replacement or league average.
- Projected lineup strength, not last night’s actual lineup.
- Bullpen availability and recent workload.
- Travel/rest and doubleheader context.
- Park factors.
- Injury or active-roster changes.
- A preseason projection prior that fades as current-season evidence accumulates.

This model should run every day because it is interpretable, fast, and hard to break. Public MLB Elo approaches commonly use team Elo with starting-pitcher, home-field, preseason-projection, and injury adjustments.

**Why it matters:** a complicated model has no value if it cannot beat a well-calibrated Elo baseline on a strictly chronological holdout.

##### 2. Regularized logistic regression

Build a pregame logistic model:

\[
P(\text{home win}) =
\sigma(\beta_0 + \beta_1 x_1 + \cdots + \beta_p x_p)
\]

Use elastic net regularization:

\[
\min_{\beta}
-\log L(\beta)
+ \lambda
\left[
\alpha \lVert\beta\rVert_1
+
\frac{1-\alpha}{2}\lVert\beta\rVert_2^2
\right]
\]

This is underrated. It gives you:

- Coefficients you can inspect.
- Stable performance under correlated baseball features.
- A strong calibration starting point.
- A test of whether a new metric has value beyond established variables.

Start with **feature differences**, such as:

```text
home_offense_projection - away_offense_projection
home_starter_projection - away_starter_projection
home_bullpen_availability - away_bullpen_availability
home_team_elo - away_team_elo
home_park_adjustment
```

Use rolling, point-in-time measures—not season-end numbers or full-season aggregates that leak future information.

#### Run-distribution models

For betting-oriented research, run distributions are more useful than winner-only classifiers. If you model the full distribution of runs, you can derive moneyline, totals, spreads, alternate lines, and correct-score probabilities from the same engine.

##### 3. Poisson and negative-binomial models

A simple team-run model starts with:

\[
R_{\text{home}} \sim \text{Poisson}(\lambda_{\text{home}})
\]

\[
R_{\text{away}} \sim \text{Poisson}(\lambda_{\text{away}})
\]

\[
\log(\lambda_{\text{home}})
=
\alpha
+ \text{home offense}
- \text{away starter}
- \text{away bullpen}
+ \text{park}
+ \text{weather}
+ \text{lineup}
\]

Baseball scores often show more variance than a pure Poisson model allows, so use a negative binomial when overdispersion is material:

\[
R \sim \text{NegBin}(\mu, \phi)
\]

Where:

- \(\mu\) is expected runs.
- \(\phi\) controls extra variance.

This is a good early production model because it is transparent and creates a complete score distribution.

##### 4. Correlated run models

The two teams’ run totals are not fully independent. Weather, park conditions, umpire zone tendencies, game pace, extra innings, and the quality of both offenses can affect both sides.

Eventually explore:

- Bivariate Poisson.
- Shared latent game-environment effect.
- Bayesian hierarchical correlated-count model.
- Copula-based dependence model.
- Simulation using plate-appearance outcomes rather than independent team scores.

But do not start there. Begin with independent or conditionally independent negative-binomial team runs, evaluate residual correlation, and add dependence only if it materially improves held-out log loss or market-specific calibration.

##### 5. Monte Carlo simulation layer

Once you have team-run distributions:

```python
for simulation in range(100_000):
    home_runs = sample_home_runs()
    away_runs = sample_away_runs()

    if home_runs > away_runs:
        home_wins += 1

    total_runs.append(home_runs + away_runs)
    margin.append(home_runs - away_runs)
```

Then estimate:

\[
P(\text{home win}) =
\frac{\text{home-win simulations}}{N}
\]

\[
P(\text{over } 8.5) =
\frac{\text{simulations with total runs} > 8.5}{N}
\]

\[
P(\text{home } -1.5) =
\frac{\text{simulations with home margin} \ge 2}{N}
\]

This lets one model power multiple markets, instead of maintaining separate winner, total, and run-line models.

#### Player and matchup models

This is where your Retrosheet, Statcast, player-ID crosswalk, lineup, and pitch-level data can become a genuine advantage.

##### 6. Hierarchical Bayesian player projections

For player metrics, hierarchical Bayesian models are one of the most appropriate tools you can use.

A batter’s observed outcome rate is noisy:

\[
\hat{p}_{\text{player}} =
\frac{\text{successes}}{\text{opportunities}}
\]

Instead of trusting the raw rate, partially pool it:

\[
\text{logit}(p_i)
\sim
\mathcal{N}(\mu_{\text{league}} + u_{\text{player}}, \sigma_{\text{player}})
\]

This naturally shrinks small samples toward appropriate priors:

- A rookie with 18 plate appearances should regress heavily toward league/role/age prior.
- A hitter with 3,000 plate appearances should be influenced largely by his own record.
- A batter’s split against left-handers should shrink more strongly than his overall rate.
- A pitcher’s current season can be combined with prior seasons using recency weights.

Use these models for:

- Batter OBP, strikeout rate, walk rate, HR rate, hit rate.
- Pitcher strikeout, walk, HR-allowed, ground-ball, and whiff rates.
- Batter-vs-pitcher matchup effects—but shrink these aggressively.
- Platoon effects.
- Park effects.
- Catcher/framing or umpire effects where you have enough data.
- Aging curves and skill-change detection.

Hierarchical models are especially valuable because player-level baseball data is sparse and noisy at the exact split level where analysts are most tempted to overfit. Public examples of MLB projection systems increasingly use hierarchical Bayesian player models and matchup layers to estimate full outcome distributions rather than a single player projection.

##### 7. Plate-appearance multinomial model

This is likely your most promising advanced modeling direction.

Predict each plate appearance as one mutually exclusive outcome:

\[
Y \in
\{
\text{out}, \text{BB/HBP}, \text{1B}, \text{2B}, \text{3B}, \text{HR}, \text{K}
\}
\]

Use multinomial logistic regression:

\[
P(Y=k \mid X)
=
\frac{\exp(\eta_k)}
{\sum_j \exp(\eta_j)}
\]

Where each class score can include:

\[
\eta_k =
\alpha_k
+
\beta_{k,\text{batter}}
+
\gamma_{k,\text{pitcher}}
+
\delta_{k,\text{handedness}}
+
\pi_{k,\text{park}}
+
\omega_{k,\text{weather}}
+
\zeta_{k,\text{count}}
\]

Then make it hierarchical:

- Batter random effects.
- Pitcher random effects.
- Batter handedness and pitcher handedness interactions.
- Park-level effects.
- Pitch-type and arsenal effects.
- Count and base/out state.
- Recent but shrunk skill changes.
- Injury/velocity-decline indicators.
- Statcast quality-of-contact effects for balls in play.

This gives you a coherent distribution that can feed a Markov chain or inning/game simulator.

For example:

```text
Batter: left-handed hitter
Pitcher: right-handed starter
Park: Yankee Stadium
Situation: 1 out, runner on first, 1-1 count
```

Your model produces a probability vector:

```text
Out:     0.615
Walk:    0.082
Single:  0.158
Double:  0.046
Triple:  0.004
HR:      0.034
HBP:     0.011
K:       included within an out taxonomy or modeled separately
```

The simulator transitions the base/out state according to that sampled outcome. Over tens of thousands of simulations, it yields runs, win probability, player hits, total bases, RBI chances, strikeouts, and other distributions.

##### 8. Markov-chain simulation

Your current Markov work is worth retaining, but I would treat the Markov chain as a **simulation framework**, not as the ultimate predictive model.

The state can be:

\[
S = (\text{inning}, \text{half inning}, \text{outs}, \text{base state}, \text{score}, \text{pitcher/bullpen context})
\]

The transition probabilities should come from your plate-appearance model, not merely static historical transition matrices.

Use a progression:

1. League-average transition matrix.
2. Team offense versus team pitching transition matrix.
3. Batter/pitcher/handedness/park-adjusted transition matrix.
4. Lineup-aware model.
5. Starter-to-bullpen simulation.
6. Pitch-count, fatigue, and reliever-availability adjustments.
7. Live, in-game state updates.

That architecture lets you improve the inputs while preserving the same game-simulation engine.

#### Machine-learning models

##### 9. Gradient-boosted trees

For structured pregame feature tables, use CatBoost, LightGBM, or XGBoost before deep neural networks.

They handle:

- Nonlinear effects.
- Thresholds.
- Interactions.
- Missingness.
- Mixed feature scales.
- Complex relationships such as bullpen fatigue only mattering when the starter has low expected innings.

Good targets:

- Home-win probability.
- Team runs.
- Starting-pitcher strikeouts.
- Batter hits.
- Batter home runs.
- Whether a starting pitcher lasts \(5+\) innings.
- First-five-inning winner or total.
- Bullpen runs allowed.
- Individual plate-appearance events.

Use:

- CatBoost when categorical identities like player, team, park, umpire, or opponent need careful treatment.
- LightGBM/XGBoost when your feature table is mostly numeric and you want fast experimentation.
- Monotonic constraints sparingly when baseball logic is clear, such as stronger offense not decreasing expected runs all else equal.

Important: player identifiers can cause memorization. If you include raw batter/pitcher IDs, evaluate on **future seasons and unseen dates**, not random row splits. Better yet, use learned player projections or target encodings that are generated strictly from data available before each game.

##### 10. Generalized additive models

GAMs are ideal for interpretable nonlinear baseball effects:

\[
\log(\mu)
=
\beta_0 +
f_1(\text{pitcher velocity}) +
f_2(\text{rest days}) +
f_3(\text{temperature}) +
f_4(\text{rolling wOBA}) +
\beta_{\text{park}}
\]

Use them when you want to understand shapes such as:

- At what point does bullpen workload become harmful?
- How does velocity change affect strikeout probability?
- Is exit velocity’s relationship with HR probability nonlinear?
- How does a hitter’s advantage change across pitcher handedness and pitch movement?

GAMs are excellent for creating and testing defensible metrics before you hide relationships inside a boosted-tree model.

##### 11. Deep neural networks

Use neural nets later and only for data structures that justify them.

| Neural architecture | Best baseball use |
|---|---|
| Feed-forward tabular net | Large feature-table experiments after CatBoost baseline |
| Embedding model | Batter/pitcher/team/park identities and latent similarities |
| Temporal convolution / transformer | Sequence of pitches or player game logs |
| Graph neural network | Lineup interactions, batter-pitcher matchup networks, roster networks |
| Survival model / neural survival model | Starter removal, injury return, pitcher availability |
| Mixture density network | Full conditional outcome distributions |
| Deep ensemble | Better uncertainty estimates than one deterministic net |

I would **not** start with a deep neural net for game winners. Public baseball data has enough rows for useful tabular ML, but the number of independent MLB games per season is still limited. A neural net can memorize player/team identities, detect leakage, and look spectacular in random cross-validation while failing live.

The first deep-learning target I would choose is pitch-level or plate-appearance-level modeling, because you have many more observations and a clearer generative process.

#### Feature engineering techniques

The feature layer will matter more than whether you pick XGBoost or a neural net.

##### Time-aware features

Every feature needs an explicit “available as of” timestamp.

Use:

- Prior-season baseline.
- Current-season-to-date value.
- Exponentially weighted moving average.
- Rolling 7/14/30/60-day windows.
- Rolling 50/100/250 plate-appearance or batters-faced windows.
- Separate recent form from long-term talent.
- Sample size and uncertainty columns for every rate.
- Days since last appearance.
- Batters faced/pitches thrown over 1, 3, 7, and 14 days.
- Starter rest, bullpen fatigue, and travel context.

Do not use raw “last 10 games” splits without comparing them to recency-weighted alternatives and sample-size-aware shrinkage.

##### Interaction features

High-value interactions include:

- Batter handedness × pitcher handedness.
- Batter swing decisions × pitcher chase-inducing arsenal.
- Batter contact quality × pitcher batted-ball profile.
- Park dimensions × hitter spray profile.
- Park × weather × batted-ball quality.
- Pitch velocity/movement × batter pitch-type weakness.
- Starter expected innings × bullpen fatigue.
- Team defense × pitcher ground-ball rate.
- Umpire zone tendency × pitcher command × batter discipline.
- Catcher receiving × pitcher location profile.
- Lineup quality × opposing bullpen depth.
- Game total environment × player plate-appearance expectation.

Do not manually create every possible interaction. Use baseball logic to prioritize candidates, then use regularization or boosted trees to test them.

##### Normalization and transformations

Your instinct about ratios and centering is right, but apply it carefully:

- Use rates with exposure columns: HR/PA plus PA; K/BF plus BF.
- Use empirical-Bayes-smoothed rates, not raw ratios.
- Use league- and season-adjusted z-scores.
- Use park-adjusted and era-adjusted metrics.
- Use log transforms for skewed positive data such as salary, pitcher workload, or implied odds.
- Use splines/GAMs rather than arbitrary polynomial terms.
- Keep raw components so researchers can recompute rates.
- Store denominator, numerator, estimate, uncertainty, and sample-size flag together.

For example, do not store only a hitter’s “recent HR rate.” Store:

```text
recent_hr
recent_pa
league_prior_hr_rate
shrunk_hr_rate
posterior_standard_error
window_start
window_end
as_of_timestamp
```

#### Betting and market models

Use markets as a benchmark and as data—not as ground truth.

##### Market-implied probability

For decimal odds:

\[
p_{\text{implied}} = \frac{1}{\text{decimal odds}}
\]

For a two-sided market, remove vig before comparing the model with market consensus:

\[
p_{\text{fair, home}}
=
\frac{p_{\text{home}}}
{p_{\text{home}} + p_{\text{away}}}
\]

Then calculate model edge:

\[
\text{edge} =
p_{\text{model}} - p_{\text{market,fair}}
\]

But never treat a positive edge as sufficient. Require:

- Model calibration.
- Sufficient line liquidity.
- Timestamp-valid price.
- Minimum edge threshold.
- Market disagreement that survives uncertainty.
- No stale lineup, starter, or weather assumptions.
- Historical performance by market type and confidence bucket.

##### Market models to build

- Closing-line probability model.
- Opening-to-close line-movement model.
- Polymarket/Kalshi probability tracker.
- Cross-market disagreement detector.
- Market liquidity and spread-quality score.
- Market-versus-model residual model.
- Event-contract resolution and timing-quality monitor.
- Price-change alert model around lineup, starter, injury, and weather news.

Prediction markets can be especially useful for collecting a transparent time series of public belief. But liquidity, contract wording, timing, and settlement rules must become first-class fields in your schema; “the price” is not a single universal truth.

#### Evaluation discipline

Your model registry should reject models that do not beat simple baselines on forward-looking data.

##### Required evaluation design

1. Split data chronologically—never random train/test splitting for game predictions.
2. Freeze a final holdout period that is never used for feature selection or hyperparameter tuning.
3. Use rolling-origin validation inside the earlier training period.
4. Build features only from records available before the scheduled first pitch.
5. Compare on the same games against Elo, market consensus, and simple baseline probabilities.
6. Save every prediction with feature snapshot version, model version, cutoff timestamp, inputs, and output distribution.
7. Report confidence intervals for differences in log loss and Brier score.
8. Evaluate calibration overall and within probability bands.
9. Check results by season, month, favorite/underdog, park, market, and lineup-status subgroup.
10. Promote a model only if it improves a predeclared metric with meaningful, repeatable magnitude.

Use both:

\[
\text{Log Loss}
=
-\frac{1}{n}
\sum_{i=1}^{n}
\left[
y_i \log(p_i)
+
(1-y_i)\log(1-p_i)
\right]
\]

and:

\[
\text{Brier Score}
=
\frac{1}{n}
\sum_{i=1}^{n}
(p_i-y_i)^2
\]

Log loss strongly punishes false confidence; Brier score is intuitive and especially helpful for calibration review. Closing-line value can be useful as a secondary market benchmark, but it is not a substitute for properly scored probability forecasts.

#### Recommended build order

For your project, I would build these in order:

1. **Elo v2** — Team Elo, home field, preseason prior, starter adjustment, point-in-time storage.
2. **Pregame feature mart** — One row per game instance; all features timestamped and leakage-audited.
3. **Elastic-net logistic regression** — Home-win probability baseline with calibration layer.
4. **Negative-binomial team-runs model** — Expected runs and full score distribution.
5. **Monte Carlo market calculator** — Derive moneyline, total, run-line, first-five, and score outcomes.
6. **CatBoost challenger** — Test against the prior models using the exact same point-in-time feature mart.
7. **Hierarchical batter/pitcher projection layer** — Build stable estimates for K%, BB%, HR/PA, hit/PA, and batted-ball quality.
8. **Plate-appearance multinomial model** — Feed it into your Markov/simulation engine.
9. **Lineup-aware and bullpen-aware simulator** — Add realistic starter exit, reliever selection, and availability logic.
10. **Player-prop models** — Start with pitcher strikeouts and batter hits, then HRs, total bases, and other volatile props.
11. **Market residual research** — Compare model probabilities with vig-adjusted prices, line movement, Polymarket/Kalshi snapshots, and closing prices.
12. **Neural network experiments** — Only after you have a rigorous benchmark suite and a reason to believe the tabular models have left usable signal on the table.

The immediate practical move is to define three canonical training tables: `game_pregame_features`, `player_prop_features`, and `plate_appearance_features`, each with explicit as-of timestamps, source provenance, and frozen training snapshots. That gives every future model a stable, comparable input contract.

---

## 3. Time-ordered backtesting

### User

> How do we implement time-ordered backtesting for sports data

### Assistant

Implement time-ordered backtesting as a **replay** of history: for every game, freeze a decision clock, build features only from records available at that clock, train only on earlier games, then score the later ones. Random k-fold, shuffled rows, season-end stats, and “nearest available” joins all leak the future and make the backtest lie.

#### Core design

Treat each prediction as happening at a single timestamp \(t^*\). For MLB, \(t^*\) is usually scheduled first pitch minus a small buffer, or the last market snapshot you would actually have used. Every input must satisfy \(\text{observed\_at} \le t^*\). Missing data stays missing; never fill from a later row.

Use three nested periods, not one train/test split:

| Period | Purpose | Touched how often |
|---|---|---|
| Development | Fit coefficients, Elo, shrinkage constants | Repeatedly |
| Validation | Tune windows, features, hyperparameters | Repeatedly, but never after seeing holdout |
| Frozen holdout | Final honest score | Once, after all choices are locked |

Inside development, use walk-forward validation, not shuffled CV. Sports outcomes are temporally dependent and non-stationary, so standard k-fold is optimistically biased.

| Scheme | How it works | Use when |
|---|---|---|
| Expanding window | Train on all history through \(t\), test the next block | You want more data and older seasons still matter |
| Sliding window | Train on the last \(w\) days/games only | The process has changed (rule, ball, expansion, dead-ball era) |
| Purged / embargoed | Leave a gap between train and test | Rolling features overlap the test window |
| Nested walk-forward | Inner loop tunes; outer loop scores | You are selecting models or features |

Do not use sklearn `TimeSeriesSplit` as the only splitter. It cuts by **row position**, not by game date, so doubleheaders, postponed games, and uneven daily slates get mixed incorrectly. Split on `game_datetime`, then `game_number`.

A practical MLB calendar:

- Train: 2018–2023, walk-forward by week or month.
- Validate: 2024, still walk-forward, used only for model selection.
- Holdout: 2025 plus 2026 completed games, frozen.

Retrain on a cadence you can actually run in production. Daily retrains are honest for Elo and logistic models. Weekly or monthly retrains are enough for gradient boosting. Do not backtest a model that retrains every game if you will only retrain once a week live.

#### Point-in-time features

The backtest is only as honest as the feature join. The correct pattern is an as-of join: for each game, take the latest feature snapshot whose timestamp is still before \(t^*\). Feature stores exist specifically to generate those point-in-time training sets so future values cannot leak into historical labels.

Store features as event-time tables, not as “current season stats”:

```sql
CREATE TABLE gold.player_rate_snapshot (
    player_id     bigint NOT NULL,
    as_of_ts      timestamptz NOT NULL,
    window_pa     int NOT NULL,
    k_rate        double precision,
    bb_rate       double precision,
    hr_pa         double precision,
    source        text NOT NULL,
    PRIMARY KEY (player_id, as_of_ts)
);
```

Then join with an as-of predicate, not `player_id` alone:

```sql
SELECT
    g.game_id,
    g.game_start,
    p.player_id,
    s.k_rate,
    s.as_of_ts
FROM core.game AS g
JOIN core.lineup_probable AS p
  ON p.game_id = g.game_id
 AND p.observed_at <= g.game_start - interval '15 minutes'
CROSS JOIN LATERAL (
    SELECT s.*
    FROM gold.player_rate_snapshot AS s
    WHERE s.player_id = p.player_id
      AND s.as_of_ts <= g.game_start - interval '15 minutes'
    ORDER BY s.as_of_ts DESC
    LIMIT 1
) AS s;
```

Rebuild rolling stats from completed games only:

```sql
-- rate through yesterday, never including today's game
SELECT
    player_id,
    game_date,
    SUM(k)  FILTER (WHERE game_date < :as_of_date)
        OVER (PARTITION BY player_id ORDER BY game_date)
        AS k_to_date,
    SUM(pa) FILTER (WHERE game_date < :as_of_date)
        OVER (PARTITION BY player_id ORDER BY game_date)
        AS pa_to_date
FROM gold.batting_game;
```

If a feature uses a 30-game or 250-PA lookback, embargo at least that much time between train labels and test games. Otherwise the test game’s rolling window still contains training-game outcomes, and the split is not clean.

Same-day MLB traps to encode in the join:

- Game 2 of a doubleheader cannot see Game 1 box-score stats if you would have bet before Game 2.
- A probable starter is not the same as the confirmed starter. Backtest the probable available at \(t^*\); score a second “oracle starter” series only as an upper bound.
- Season stats, WAR, FIP, and team Elo must be the version as of that morning, not the final season line.
- Market odds must be the snapshot you would have bet, usually open or last pregame print, not close if you claim a closing-line strategy.
- Do not impute a missing snapshot from the next day’s value.

#### Walk-forward loop

Implement the evaluator as a clock, not as `train_test_split()`.

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class Fold:
    train_end: datetime
    test_start: datetime
    test_end: datetime
    embargo: timedelta

def expanding_folds(
    dates: pd.DatetimeIndex,
    min_train: datetime,
    test_span: timedelta,
    step: timedelta,
    embargo: timedelta,
) -> list[Fold]:
    folds = []
    test_start = min_train
    last = dates.max().to_pydatetime()
    while test_start + test_span <= last:
        train_end = test_start - embargo
        folds.append(Fold(train_end, test_start, test_start + test_span, embargo))
        test_start += step
    return folds

def as_of_frame(events: pd.DataFrame, t_star: datetime) -> pd.DataFrame:
    return events.loc[events["observed_at"] <= t_star].copy()

def walk_forward(games, events, folds, fit_fn, predict_fn, score_fn):
    rows = []
    for fold in folds:
        history = games.loc[games["game_start"] <= fold.train_end]
        slate = games.loc[
            (games["game_start"] >= fold.test_start)
            & (games["game_start"] < fold.test_end)
        ]
        if history.empty or slate.empty:
            continue
        model = fit_fn(history, as_of_frame(events, fold.train_end))
        for game in slate.itertuples():
            t_star = game.game_start - timedelta(minutes=15)
            x = as_of_frame(events, t_star)
            p = predict_fn(model, game, x)
            rows.append({
                "game_id": game.game_id,
                "t_star": t_star,
                "fold_test_start": fold.test_start,
                "p_home": p,
                "y_home": game.home_win,
            })
    pred = pd.DataFrame(rows)
    pred["log_loss"] = -(
        pred.y_home * np.log(pred.p_home.clip(1e-15, 1 - 1e-15))
        + (1 - pred.y_home) * np.log((1 - pred.p_home).clip(1e-15, 1 - 1e-15))
    )
    return pred
```

That loop has three non-negotiable properties:

1. Training labels stop at `train_end`.
2. Features for a test game are rebuilt at that game’s own \(t^*\), not at fold start.
3. Predictions are written before the outcome is used for anything except scoring.

For nested selection, run an inner expanding window on 2018–2023 to choose hyperparameters. Refit the chosen spec on all data through 2024. Score 2025–2026 once. If you retune after seeing the holdout, the holdout is gone.

Persist every prediction as a first-class table:

```text
game_id
model_version
feature_set_version
t_star
generated_at
p_home
p_over_8_5
market_p_home
market_observed_at
y_home          -- nullable until the game ends
```

If you cannot reconstruct the exact feature vector from `(model_version, feature_set_version, t_star)`, the backtest is not reproducible.

#### Sports-specific leakage

Most bad sports backtests fail here, not in the splitter.

**Completed-game stats used as pregame features.** Anything built from `gold.batting_game` must exclude the target `game_id` and any later game.

**Target leakage through IDs.** A booster that sees `pitcher_id` can memorize 2023 results and look brilliant on a random split. Chronological splits reduce this; hashed target encoding with only prior games is safer.

**Market close used as a feature for a bet you would have placed at open.** If the strategy is “bet at 10 a.m.,” the feature is the 10 a.m. price. Closing line is a benchmark, not an input, unless the strategy truly waits for close.

**Same-slate contamination.** Training on the 7:10 ET game and testing the 7:15 ET game on the same day is usually acceptable for pregame models, because neither result exists yet. It is not acceptable if either feature used in-progress scores, Twitter “confirmed lineup” scraped after first pitch, or a daily table that already includes that night’s games.

**Label leakage in evaluation.** Your holdout scorer must use the stored pregame probability. Recomputing features after the season with final WAR is a different study.

**Prediction-market special case.** Settlement, final status, later headlines, and current web search are future facts. Bound every market row with `observed_at <= t_star`, and do not let a “nearest quote” walk forward to the next print.

A cheap leakage test: shuffle only the labels in the holdout. If log loss barely changes, the model is not using real pregame signal. A second test: add a feature equal to the actual winner. If the pipeline does not explode to near-zero log loss, the label never reached training, which is what you want on the test side.

#### What to score

Score probabilities first, betting P&L second. Accuracy is not enough because two 58% models can have very different betting value. Use log loss and Brier score, then calibration, then a market comparison, then a costed betting simulation.

| Question | Metric |
|---|---|
| Are probabilities honest? | Log loss, Brier, reliability diagram |
| Does the model beat a dumb prior? | Brier skill vs home-field or Elo |
| Does it beat the market? | Brier skill vs vig-removed market probability |
| Would it have been bettable? | ROI after juice, CLV, drawdown |
| Is the gain real? | Paired bootstrap CI on log-loss difference |

Compare models on the exact same games. If Elo is missing 12 games and CatBoost is missing 3, you are not comparing models; you are comparing coverage. Your existing paired-sample idea is the right one.

A fold is a pass only if all of these hold:

- Features were built with `observed_at <= t_star`.
- Training games all start before the embargo.
- Holdout was not used for feature or hyperparameter decisions.
- Metrics are reported with sample size and a confidence interval.
- A simple Elo/log5 baseline is scored on the same slate.

If you implement only one artifact next, make it `gold.prediction` rows that already satisfy the as-of rule, plus a fold table that can rebuild train/validate/holdout from dates. The models can change; the clock cannot.

---

## 4. Feature store for sports analytics

### User

> How to build a feature store for sports analytics

### Assistant

A sports feature store is a **time-travel** catalog: named, versioned features keyed by entity and timestamp, retrieved as they existed before a game, not as they look after the season. The store’s job is point-in-time joins for training and the same values at serving time so backtests and live predictions use one definition.

Do not start with Feast or Tecton. For an MLB research database, PostgreSQL snapshot tables plus a retrieval API are enough. A commercial feature store is justified later if you have many teams, low-latency serving, and feature-definition drift you cannot police in SQL.

#### What to store

Store feature **views**, not one giant `game_features_wide` table. The wide game row is an assembled training dataset. The store underneath it is a set of slowly changing snapshots at natural grains.

| Entity | Grain | Example features | Typical as-of |
|---|---|---|---|
| `player` | player × timestamp | rolling K%, BB%, wOBA, PA count, uncertainty | end of previous day |
| `pitcher` | pitcher × timestamp | FIP, velo, pitch mix, rest, BF last 7 days | end of previous day / last outing |
| `team` | team × timestamp | Elo, Pythagorean, bullpen fatigue, lineup strength | morning of game |
| `game` | game instance | park, weather, umpire, rest, travel, doubleheader flag | pregame \(t^*\) |
| `matchup` | batter × pitcher × timestamp | shrunk platoon rates, limited PA | before first pitch |
| `park` | park × season-to-date | HR factor, weather-adjusted run factor | before game |
| `market` | game × book × timestamp | vig-removed moneyline, total, movement | last snapshot \(\le t^*\) |

Every stored row needs four clocks:

- `entity_id` — player, team, game, park
- `event_ts` — when the baseball fact happened (last pitch of yesterday’s game)
- `created_ts` — when your pipeline actually wrote the feature
- `available_ts` — when a model would have been allowed to see it

Point-in-time retrieval scans backward from the entity row’s timestamp and takes the latest feature whose event time is at or before that timestamp. If you also require `created_ts <= t^*`, you block late-arriving Retrosheet or Statcast files from leaking into a historical training row.

Keep numerators and denominators, not only rates:

```text
k, pa, k_rate, k_rate_shrunk, pa_window, window_start, window_end
```

A rate without exposure is not a sports feature. Eighteen plate appearances and 600 plate appearances are different objects.

#### Table layout

Use append-only snapshot tables. Do not overwrite “current season stats.”

```sql
CREATE TABLE feat.player_offense_1d (
    player_id        bigint NOT NULL,
    event_ts         timestamptz NOT NULL,  -- end of last included game
    created_ts       timestamptz NOT NULL DEFAULT now(),
    available_ts     timestamptz NOT NULL,  -- typically event_ts + ingest lag
    feature_version  text NOT NULL,
    pa               int NOT NULL,
    k                int NOT NULL,
    bb               int NOT NULL,
    h                int NOT NULL,
    hr               int NOT NULL,
    k_rate           double precision,
    k_rate_shrunk    double precision,
    woba             double precision,
    PRIMARY KEY (player_id, event_ts, feature_version)
);

CREATE INDEX ON feat.player_offense_1d (player_id, available_ts DESC);
```

Assemble a game-level training row only at retrieval time:

```text
entity_df:
  game_id, home_team_id, away_team_id, home_starter_id, away_starter_id, event_timestamp

joined:
  home starter rolling FIP as of t*
  away starter rolling FIP as of t*
  home team Elo as of t*
  away offense vs RHP as of t*
  park factor as of t*
  weather as of t*
  market moneyline as of t*
```

That entity dataframe is Feast’s historical-retrieval contract: keys plus `event_timestamp`, then a last-known-value join from each feature view. You can implement the same contract in Postgres without Feast.

Wide `gold.game_feature` can remain a **materialized** retrieval cache for the daily slate. It should be built from these views, not used as the only source of truth. If a researcher asks “what was Judge’s shrunk K% on 2024-07-12 at 6:40 p.m. ET?”, the answer must come from `feat.player_offense_1d`, not from a game row that may have been rebuilt later.

#### Point-in-time retrieval

The only legal join is “latest snapshot not after the decision clock.”

```sql
CREATE FUNCTION feat.asof_player_offense(
    p_player_id bigint,
    p_tstar     timestamptz,
    p_version   text DEFAULT 'v1'
) RETURNS feat.player_offense_1d
LANGUAGE sql STABLE AS $$
    SELECT s.*
    FROM feat.player_offense_1d AS s
    WHERE s.player_id = p_player_id
      AND s.feature_version = p_version
      AND s.available_ts <= p_tstar
    ORDER BY s.available_ts DESC
    LIMIT 1
$$;
```

Batch version for a slate:

```sql
SELECT
    g.game_id,
    g.game_start AS event_timestamp,
    off.*
FROM core.game AS g
JOIN core.probable_starter AS st
  ON st.game_id = g.game_id
 AND st.observed_at <= g.game_start - interval '15 minutes'
CROSS JOIN LATERAL feat.asof_player_offense(
    st.pitcher_id,
    g.game_start - interval '15 minutes',
    'v1'
) AS off;
```

Python API should look like a feature store even if it is just SQL:

```python
def get_historical_features(entity_df, features, t_col="event_timestamp"):
    frames = [entity_df]
    for spec in features:
        frames.append(asof_join(entity_df, spec, t_col))
    return reduce(lambda a, b: a.merge(b, on=list(entity_df.columns)), frames)

training = get_historical_features(
    games[["game_id", "home_starter_id", "event_timestamp"]],
    features=[
        "player_offense_1d:k_rate_shrunk",
        "pitcher_1d:fip_shrunk",
        "team_elo:rating",
        "park_season:hr_factor",
        "market_pregame:p_home_fair",
    ],
)
```

Two timestamp filters matter in sports:

1. `event_ts <= t*` — the game, PA, or pitch had already occurred.
2. `created_ts <= t*` — your warehouse had already ingested it.

If Statcast for April 3 lands on April 5, a model run on April 3 must not see those pitches. That is the `created_timestamp` filter Feast added for exactly this late-data case.

Sports-specific retrieval rules:

- Default `t*` = scheduled first pitch minus 15 minutes, or last market snapshot you would have bet.
- Doubleheaders: game 2 cannot see game 1 box scores unless `available_ts` is before game 2’s `t*`.
- Probable starters and posted lineups are features with their own `observed_at`. Do not silently substitute the actual starter.
- Same-day games may share yesterday’s player snapshots. They must not share that night’s results.
- Market features join on `(game_id, observed_at <= t*)`, never on “closing line” unless the strategy is explicitly a close bet.

#### Compute jobs

Build features incrementally from completed facts. Do not recompute every player’s career every morning unless the definition changed.

A daily job:

1. Close yesterday’s games.
2. Update player, pitcher, and team snapshot rows with `event_ts = yesterday_end`.
3. Set `available_ts` to `now()` or to a documented ingest lag, whichever is later.
4. Materialize today’s slate into `gold.game_feature` using as-of retrieval at each game’s `t*`.
5. Freeze that slate as `gold.game_feature_snapshot` keyed by `feature_set_version`.

Rolling windows belong in SQL, with the target game excluded:

```sql
INSERT INTO feat.player_offense_1d (
    player_id, event_ts, available_ts, feature_version,
    pa, k, bb, h, hr, k_rate, k_rate_shrunk, woba
)
SELECT
    player_id,
    date_trunc('day', game_date) + interval '1 day' AS event_ts,
    date_trunc('day', game_date) + interval '1 day' AS available_ts,
    'v1',
    SUM(pa) OVER w AS pa,
    SUM(k)  OVER w AS k,
    ...
FROM gold.batting_game
WINDOW w AS (
    PARTITION BY player_id
    ORDER BY game_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
```

Then shrink:

\[
\hat{p} = \frac{k + m \cdot p_{\text{league}}}{PA + m}
\]

Store \(m\), \(p_{\text{league}}\), raw rate, and shrunk rate together. League priors must also be as-of: 2024 league K% cannot be used as the 2023-May prior.

Version features when the formula changes. `k_rate_shrunk@v1` and `@v2` are different columns. Never mutate historical snapshot rows in place to “fix” a definition; insert a new `feature_version`.

For live serving you do not need Redis yet. A current-state table is enough:

```sql
CREATE TABLE feat.player_offense_current AS
SELECT DISTINCT ON (player_id)
    *
FROM feat.player_offense_1d
WHERE feature_version = 'v1'
ORDER BY player_id, available_ts DESC;
```

Online/offline drift is the classic feature-store failure: training used as-of SQL, production reads a different current table, and live log loss collapses. The serving path must call the same retrieval function with `t* = now()`.

#### Registry and tests

A feature is not admitted until it has a registry row.

```yaml
name: pitcher_fip_shrunk
entity: pitcher
version: v1
owner: research
event_ts: end of last outing
available_ts: outing_end + 6h ingest lag
inputs: [er, ip, hr, bb, hbp, k]  # from completed games only
formula: |
  FIP = (13*HR + 3*(BB+HBP) - 2*K)/IP + cFIP_asof
  shrink m = 200 BF toward league FIP
not_available_when: IP = 0
leakage_notes: excludes target game; no season-end cFIP
tests:
  - hand_calc_verlander_2019_09_01
  - asof_excludes_same_day_start
  - serving_equals_historical_at_tstar
```

Minimum tests:

- Hand-calculated fixture for one known player-date.
- As-of test: retrieving at 16:00 does not include a 19:10 game that night.
- Late-arrival test: a row with `created_ts` after `t*` is invisible when `filter_by_created_timestamp` is on.
- Doubleheader test.
- Serving/historical equality: `get_online_features(t*) == get_historical_features(t*)` for the same keys.
- Denominator test: rates are null when PA or IP is zero.
- Version pin: a frozen snapshot’s checksum does not change after a later rebuild of current tables.

Recommended build order for your stack:

1. Snapshot tables at player, pitcher, team, park grains.
2. `feat.asof_*` functions and one `get_historical_features()` helper.
3. Daily materialize of the upcoming slate into `gold.game_feature`.
4. Content-addressed snapshots for experiments.
5. Registry YAML plus leakage tests in CI.
6. Only then consider Feast if you want a standard retrieval API on top of the same Postgres offline tables.

Skip Redis, Kafka, and an “online store” until a model actually has to score in under a second during games. Pregame MLB features change on a minutes-to-hours cadence. Correct as-of history is the scarce resource, not millisecond lookups.

The feature store is working when you can recreate last Tuesday’s 6:40 p.m. ET Yankees–Red Sox feature vector bit-for-bit, train on it, and then score tonight’s slate with the same code path.

---

## 5. Real-time in-game feature updates

### User

> How to handle real-time in-game feature updates for live betting

### Assistant

Treat live betting as **state updates**, not as rebuilding the research database. Freeze pregame features at first pitch, append every pitch/play to an event log, mutate a small in-memory game state, then rescore remaining-game probabilities. Do not run `mlb report` or recompute season rolling stats on each pitch.

Public MLB live feeds are usually 5–15 seconds behind the broadcast if you poll every 5–10 seconds, so your feature clock must be the feed’s event time, not wall-clock “now.” Commercial live APIs treat play-by-play as the sequencing source, initialize from a full REST snapshot, then apply incremental events, with REST as the recovery path if the stream drops.

#### Split two feature speeds

| Layer | Update cadence | Examples | Live rule |
|---|---|---|---|
| Pregame (frozen) | Once at first pitch | Elo, season FIP, lineup quality, park, weather at start, opening price | Copy into the live context; do not rewrite with this game’s box score |
| Game state (hot) | Every pitch/play | Inning, half, outs, bases, score, count, batter, pitcher, pitch number | Mutate from the event log |
| In-game derived | Every state change | Win expectancy, remaining runs, leverage, starter hook risk, next-batter matchup | Recompute from frozen priors + current state |
| Market (hot) | Every quote | Live moneyline, run line, total, Kalshi/Polymarket tick | Join on `quote_ts <= event_ts` |
| Postgame | After `status=closed` | Official scoring changes, Statcast reconciliation | Never used for live decisions |

The live model is almost always **real-time inference** with an offline-trained engine (Markov / run expectancy / remaining-game simulator). Do not online-learn Elo or GBM weights from the current game. That is unstable and leaks the outcome you are still pricing.

A 3–2 count with the bases loaded changes win probability a lot. Yesterday’s team wOBA does not. Spend latency budget on state, not on re-aggregating 16 million Retrosheet rows.

#### Event log, then state

Make play-by-play the source of truth. Box score is a projection for the scoreboard, not the feature driver. Process events by `sequence_number` or event id so polls do not double-apply the same pitch.

```text
live.event
  game_pk
  sequence_no
  event_ts          -- feed timestamp
  ingest_ts         -- when you received it
  event_type        -- pitch, play, sub, delay, scoring_change
  payload jsonb
  UNIQUE (game_pk, sequence_no)
```

Reduce the stream to a compact state object:

```python
@dataclass
class LiveState:
    game_pk: int
    seq: int
    event_ts: datetime
    status: str                 # scheduled, inprogress, delayed, closed
    inning: int
    half: str                   # T / B
    outs: int
    bases: tuple[int, int, int] # runner player ids or 0/1
    score_home: int
    score_away: int
    balls: int
    strikes: int
    batter_id: int | None
    pitcher_id: int | None
    pitcher_pitches: int
    pitcher_is_starter: bool
    lineup_idx: dict[str, int]
    win_exp_home: float | None
```

Apply events as a pure function:

```text
new_state = reduce(event, old_state)
```

That gives you replay, recovery, and live backtests from the same code. If the websocket dies, pull the full live feed, rebuild state from sequence 1, and resume. That initialize-then-push plus REST reconciliation pattern is the standard live-game integration.

Handle sports-specific mutations as first-class events:

- Pitch: update count, pitch number, velocity if present.
- Play: update bases, outs, score, batter.
- Substitution: pitcher, batter, runner, defense.
- Mound visit / delay: freeze scoring, keep `status=delayed`.
- Scoring change: apply only if `event_ts` is still before your decision; in live mode, a later official change does not rewrite a bet you already would have priced.
- Game over: close the state, stop inference, write a final snapshot.

Do not update `feat.player_offense_1d` mid-game. If you need “strikeouts so far tonight,” store it on `LiveState`, not in the season feature store. Mixing those clocks is how live systems contaminate tomorrow’s pregame backtest.

#### Online store

Postgres is the durable log. It is not the live read path.

```text
Redis HASH  live:game:{game_pk}
  seq, event_ts, state_json, features_json, p_home, p_over, model_version

Redis STREAM live:events:{game_pk}
  append-only pitches for consumers

Postgres    live.event          durable
Postgres    live.prediction     every scored state, for audit
```

On each new sequence number:

1. Persist the raw event.
2. Update `LiveState`.
3. Derive features from frozen pregame priors + state.
4. Score remaining-game probabilities.
5. Write Redis + `live.prediction`.
6. Compare to the latest market tick with `quote_ts <= event_ts`.

Online stores exist so serving can do a key-value lookup of the latest features while training still uses historical snapshots. Track freshness with `event_ts`, a TTL, and a watermark of the latest event time processed. If `now - event_ts` exceeds your SLA, skip the bet rather than score stale state.

A homelab-sized MLB slate does not need Kafka. One process per live game, Redis, and an append-only Postgres table is enough. Add a broker only when multiple consumers (site, alerts, research writer) need the same stream.

Feature TTL examples:

| Feature | TTL | Stale action |
|---|---|---|
| Count, outs, bases, score | until next event | block scoring |
| Win expectancy | until next event | block scoring |
| Starter pitch count | until next pitch | block hook-risk markets |
| Weather | 5–15 min | reuse last, flag degraded |
| Frozen pregame Elo | game duration | never refresh from this game |
| Live market quote | 2–5 sec | do not compare |

#### What to recompute live

Recompute only quantities that are a function of current state.

**Win expectancy / remaining runs.** Look up or simulate \(P(\text{home win} \mid \text{inning, half, outs, bases, score, pitcher})\). This is your Markov engine with the current 24 base-out states, plus score and inning. That is the core live moneyline model.

**Starter hook and bullpen.** Pitch count, in-game runs allowed, leverage, and available relievers. Books often price early innings heavily on the starter; your live edge, if any, is usually recognizing that the game has already left that assumption. Do not treat that as a betting instruction; treat it as a state feature.

**Next PA matchup.** Current batter vs current pitcher, handedness, count. Use pregame hierarchical rates, not a mid-game retrain.

**Player props remaining.** Tonight’s pitcher Ks so far plus remaining expected batters faced. The season K% stays frozen; only exposure left in this game changes.

Keep the live feature vector tiny:

```text
frozen: elo_diff, starter_fip_pre, lineup_woba_pre, park, weather_start
hot:    inning, half, outs, bases, score_diff, count,
        pitcher_pitches, is_starter, leverage, we_home
market: p_home_live, total_live, quote_ts
```

Inference should be milliseconds: a table lookup plus a short Monte Carlo, or a precomputed win-expectancy grid. A 50,000-game simulator on every pitch will lose to a 24-state Markov lookup. Use the heavy simulator only on pitching changes, half-inning starts, or when the market you care about is a total/prop rather than moneyline.

#### Live backtest and failure modes

A live system you cannot replay is not a model; it is a dashboard. To backtest, you need the ordered feed with timestamps, not the cleaned postgame Retrosheet file.

Store every decision as:

```text
game_pk, seq, event_ts, ingest_ts,
state_hash, feature_version, model_version,
p_home, p_over,
market_p_home, market_ts,
latency_ms = ingest_ts - event_ts
```

Then replay: sort by `event_ts`, apply `reduce`, score, and only count a hypothetical bet if `ingest_ts + decision_delay <= market_ts` of the quote you claim you could have hit. If you ignore latency, the backtest assumes you bet on information the book already had.

Common failure modes:

- **Polling duplicates.** Deduplicate on `(game_pk, sequence_no)`.
- **Out-of-order packets.** Buffer by sequence; do not apply seq 142 before 141.
- **Late Statcast.** Velocity and exit velo may arrive after the pitch that books already priced. Live moneyline should not wait on them.
- **Official scoring changes.** Live features follow the feed as it stood; postgame corrections belong in the research warehouse only.
- **Training-serving skew.** The WE function used live must be the same function used in replay. One codebase, two clocks.
- **Pregame table mutation.** If tonight’s hits flow into `gold.batting_game` before the final out, tomorrow’s as-of join will leak. Write live stats to `live.*` until `status=closed`, then promote.
- **Market timestamp mismatch.** Comparing a 7:12:01 model to a 7:12:08 book update is not an edge; it is stale-quote fiction.

Operational loop for one game:

```text
REST snapshot → subscribe/poll PBP
on new seq:
  append live.event
  update LiveState
  derive hot features
  score remaining-game model
  join latest market tick with quote_ts <= event_ts
  write live.prediction
on disconnect:
  REST snapshot, rebuild from seq 1, resume
on closed:
  freeze, promote box score to gold, stop
```

Build this after the pregame feature store works. Live betting multiplies operational load and does not fix a leaky pregame model. The research product is a replayable event log plus a state reducer plus a remaining-game probability function; the website and alerts are just consumers of `live.prediction`.

---

## 6. Backtesting real-time models with historical event logs

### User

> How to backtest real time sports betting models with historical event logs

### Assistant

A real-time backtest is a **replay** of the same reducer you would run live: apply events in order, score only on information available at that event, then try to “trade” only against a quote that still existed after your latency. If you score a cleaned postgame file against closing prices, you are not backtesting a live model.

You actually need two experiments. Sequence replay tests whether the model’s state machine is honest. Market replay tests whether a bet could have been placed. Mixing them is the usual way live-betting research lies.

#### Two backtests

| Test | Inputs | Question | Passes if |
|---|---|---|---|
| Model replay | Ordered PBP + frozen pregame features | Was \(P_t\) calibrated given state \(S_t\)? | Log loss / Brier vs final outcome, by state |
| Market replay | Same + timestamped live quotes | Could that probability have been bet? | Edge after delay, vig, suspensions, missed fills |
| Latency stress | Same + delay distribution | Does the edge survive realistic lag? | Edge goes to ~0 as delay approaches book update time |

Retrosheet-style logs are excellent for model replay: they give play sequence, bases, outs, score, and substitutions. They are usually **not** enough for market replay, because they lack wall-clock pitch times and contemporaneous live odds. For fills you need a feed with `event_ts` plus a historical odds tape with `quote_ts`.

Do not reconstruct “live” prices from the final line. In-play baseball lines jump on the pitch; the close is a different object.

#### Clocks

Give every row four times. Look-ahead bias is almost always a clock bug, not a model bug.

```text
event_ts     when the pitch/play happened (feed clock)
ingest_ts    when your pipeline would have received it
decision_ts  ingest_ts + compute + human/API delay
quote_ts     when the book/market published that price
```

A hypothetical bet at sequence \(k\) is valid only if:

\[
\text{decision\_ts}_k \le \text{quote\_ts}_{\text{used}}
\le \text{next material market update}
\]

If compute time exceeds how fast the price decays, the action is invalid no matter how good \(P_k\) was. Report a latency budget and refuse fills outside it.

Schema:

```sql
CREATE TABLE live.event_hist (
    game_pk       bigint NOT NULL,
    seq           int    NOT NULL,
    event_ts      timestamptz NOT NULL,
    ingest_ts     timestamptz,          -- null if unknown; do not fake it
    event_type    text NOT NULL,
    payload       jsonb NOT NULL,
    source        text NOT NULL,        -- statsapi, retrosheet, sportradar
    PRIMARY KEY (game_pk, seq, source)
);

CREATE TABLE live.quote_hist (
    game_pk       bigint NOT NULL,
    market        text NOT NULL,        -- ml_home, total, spread, kalshi
    quote_ts      timestamptz NOT NULL,
    p_or_line     double precision NOT NULL,
    suspended     boolean NOT NULL DEFAULT false,
    source        text NOT NULL,
    PRIMARY KEY (game_pk, market, quote_ts, source)
);

CREATE TABLE live.decision_hist (
    game_pk       bigint NOT NULL,
    seq           int NOT NULL,
    model_version text NOT NULL,
    state_hash    text NOT NULL,
    p_home        double precision NOT NULL,
    event_ts      timestamptz NOT NULL,
    ingest_ts     timestamptz NOT NULL,
    decision_ts   timestamptz NOT NULL,
    quote_ts      timestamptz,
    quote_p_home  double precision,
    fill_status   text NOT NULL,        -- filled, suspended, stale, no_quote
    PRIMARY KEY (game_pk, seq, model_version)
);
```

If `ingest_ts` is missing, do not pretend it equals `event_ts`. Public MLB polling is often 5–15 seconds behind the broadcast; books are usually faster. A conservative research default is `ingest_ts = event_ts + poll_interval + 2s` jitter, then show results under several delay assumptions rather than one heroic number.

#### Replay engine

Use the live reducer unchanged. Historical backtests that reimplement scoring in a batch SQL job will diverge from production.

```python
def replay_game(events, quotes, pregame, model, delay: timedelta):
    state = initial_state(pregame)
    rows = []
    for ev in events:  # already sorted by (game_pk, seq)
        state = reduce_event(state, ev)
        if not state.in_progress:
            continue
        ingest_ts = ev.ingest_ts or (ev.event_ts + delay)
        decision_ts = ingest_ts + model.compute_budget
        p = model.score(state, pregame)          # remaining-game P(home)
        quote = last_quote(
            quotes,
            market="ml_home",
            asof=decision_ts,
        )
        fill = classify_fill(quote, decision_ts, state)
        rows.append(Decision(ev, state, p, decision_ts, quote, fill))
    return rows

def last_quote(quotes, market, asof):
    q = quotes[(quotes.market == market) & (quotes.quote_ts <= asof)]
    if q.empty:
        return None
    return q.iloc[-1]

def classify_fill(quote, decision_ts, state):
    if quote is None:
        return "no_quote"
    if quote.suspended:
        return "suspended"
    if decision_ts - quote.quote_ts > STALE:     # e.g. 3–8s for ML
        return "stale"
    return "filled"
```

Critical details:

- Sort by `(game_pk, seq)`, not by wall clock alone. Out-of-order packets must wait for the missing sequence, just as live would.
- Freeze pregame features at first pitch. Tonight’s hits do not update season wOBA inside this replay.
- Score remaining-game probability from current state, not “who won after the fact.”
- Write `state_hash` so you can prove Tuesday’s 6–4, 2-out, runner-on-second vector is reconstructable.
- On disconnect/gap in the historical feed, rebuild from seq 1 or mark the hole; never interpolate a missing pitch from the final box score.

Walk forward across seasons the same way as pregame models: train WE/Markov parameters on earlier years, replay later years, freeze a holdout. Inner-loop tuning that peeks at 2025 live P&L invalidates 2025.

#### Market fills

Most fake live edges die in the fill simulator, not in log loss.

Join the last unsuspended quote at or before `decision_ts`. Then apply friction:

| Friction | Honest treatment |
|---|---|
| Vig | Convert to fair probability; edge vs fair, P&L vs actual juice |
| Suspension | No fill on HR, K looking, inning-ending DP, pitching change until quote resumes |
| Stale quote | Reject if quote is older than your SLA |
| Limit / liquidity | Cap stake; do not assume $10k got the $50 screen price |
| Partial fill | For Kalshi/Polymarket, use size at that tick if you have a tape |
| Next-tick bias | Never fill at the quote *after* the event |
| Line movement | Count closing-line value only if you actually filled the earlier price |

Historical odds APIs that return every in-play snapshot in chronological order are the right market tape. A daily close, or “Pinnacle close,” is a pregame benchmark, not an in-play fill.

P&L for a filled home moneyline:

\[
\text{EV}_i = p_i \cdot \text{net win} - (1-p_i) \cdot \text{stake}
\]

but reported ROI must use the **actual** decimal odds you filled, not your model probability. Keep three ledgers:

1. Model quality: log loss of \(p_i\) vs game winner, including unfilled rows.
2. Paper trading: P&L on `fill_status='filled'` only.
3. Stress: same bets with +2s, +5s, +10s extra delay.

If ledger 1 looks strong and ledger 3 is dead, you had a latency artifact, not a baseball model. Books explicitly widen acceptance delay and suspend on high-impact events; a backtest that fills through those windows is modeling an advantage you would not get.

Replay is also not a chart review. Execute the rule as events arrive, log skipped signals, and compare that journal to live paper trading later. Friction that is invisible in a batch join shows up immediately in event-by-event replay.

#### What leaks in historical logs

Retrosheet and cleaned Statcast are postgame products. Using them as if they were the live wire creates specific lies:

- **Official scoring.** A hit later changed to an error must stay a hit in the live replay until the feed itself changed it.
- **Final pitch tags.** Pitch type, exit velo, and launch angle often arrive late. A live moneyline at pitch time should not wait for Statcast.
- **Actual starter / pinch hitter.** Use only substitutions that had occurred by `seq`. The final lineup card is future information.
- **Win probability charts on box-score pages.** Those are computed from the finished account. They are a useful sanity check for your WE table, not a trading tape.
- **Publication time ≠ available time.** If a news or injury timestamp is “posted at 8:01” but your scrape would have seen it at 8:04, the embargo is 8:04.
- **Nearest-quote joins.** `ORDER BY abs(quote_ts - event_ts)` will pick a quote from *after* the pitch. Always `quote_ts <= decision_ts`.
- **Same-event Statcast merge.** Joining Savant on `(game_pk, at_bat_number, pitch_number)` after the game is fine for research metrics. It is illegal inside a live decision at that pitch.

A cheap leakage battery:

1. Shuffle remaining-game outcomes among similar states. Log loss should get worse.
2. Fill at `quote_ts = event_ts` vs `event_ts + 10s`. If P&L collapses, the original edge was speed, not state.
3. Replay with the live code path and a batch SQL rewrite. Any disagreement is a production bug.
4. Drop all events with missing `ingest_ts` and re-score. If results change a lot, you were imputing a fantasy feed.

Minimum honest report for one model version:

```text
n_states scored
log_loss / brier by inning and score_diff
calibration in 10 WE buckets
fill rate, stale rate, suspension rate
ROI at delay = 2s / 5s / 10s
max drawdown on filled bets
paired comparison vs a static WE table (no pitcher adjustment)
```

Start with model replay on Retrosheet/Stats API sequences until calibration is real. Only then attach a timestamped odds tape. A calibrated remaining-game engine plus a strict fill simulator is the backtest. Everything else is a highlight reel.

---

## Formula index

Quick reference for the math used in this conversation.

### Targets

\[
P(\text{home win}), \quad P(\text{home runs}), \quad P(\text{away runs}), \quad P(\text{player outcome})
\]

### Elo

\[
P(\text{home win}) =
\frac{1}{1 + 10^{-(R_{\text{home}} - R_{\text{away}} + H)/400}}
\]

### Logistic regression

\[
P(\text{home win}) =
\sigma(\beta_0 + \beta_1 x_1 + \cdots + \beta_p x_p)
\]

### Elastic net

\[
\min_{\beta}
-\log L(\beta)
+ \lambda
\left[
\alpha \lVert\beta\rVert_1
+
\frac{1-\alpha}{2}\lVert\beta\rVert_2^2
\right]
\]

### Team runs

\[
R_{\text{home}} \sim \text{Poisson}(\lambda_{\text{home}})
\]

\[
R_{\text{away}} \sim \text{Poisson}(\lambda_{\text{away}})
\]

\[
\log(\lambda_{\text{home}})
=
\alpha
+ \text{home offense}
- \text{away starter}
- \text{away bullpen}
+ \text{park}
+ \text{weather}
+ \text{lineup}
\]

\[
R \sim \text{NegBin}(\mu, \phi)
\]

### Monte Carlo market probabilities

\[
P(\text{home win}) =
\frac{\text{home-win simulations}}{N}
\]

\[
P(\text{over } 8.5) =
\frac{\text{simulations with total runs} > 8.5}{N}
\]

\[
P(\text{home } -1.5) =
\frac{\text{simulations with home margin} \ge 2}{N}
\]

### Hierarchical player rates

\[
\hat{p}_{\text{player}} =
\frac{\text{successes}}{\text{opportunities}}
\]

\[
\text{logit}(p_i)
\sim
\mathcal{N}(\mu_{\text{league}} + u_{\text{player}}, \sigma_{\text{player}})
\]

### Empirical-Bayes shrinkage

\[
\hat{p} = \frac{k + m \cdot p_{\text{league}}}{PA + m}
\]

### Plate-appearance multinomial

\[
Y \in
\{
\text{out}, \text{BB/HBP}, \text{1B}, \text{2B}, \text{3B}, \text{HR}, \text{K}
\}
\]

\[
P(Y=k \mid X)
=
\frac{\exp(\eta_k)}
{\sum_j \exp(\eta_j)}
\]

\[
\eta_k =
\alpha_k
+
\beta_{k,\text{batter}}
+
\gamma_{k,\text{pitcher}}
+
\delta_{k,\text{handedness}}
+
\pi_{k,\text{park}}
+
\omega_{k,\text{weather}}
+
\zeta_{k,\text{count}}
\]

### Markov state

\[
S = (\text{inning}, \text{half inning}, \text{outs}, \text{base state}, \text{score}, \text{pitcher/bullpen context})
\]

### GAM

\[
\log(\mu)
=
\beta_0 +
f_1(\text{pitcher velocity}) +
f_2(\text{rest days}) +
f_3(\text{temperature}) +
f_4(\text{rolling wOBA}) +
\beta_{\text{park}}
\]

### Market math

\[
p_{\text{implied}} = \frac{1}{\text{decimal odds}}
\]

\[
p_{\text{fair, home}}
=
\frac{p_{\text{home}}}
{p_{\text{home}} + p_{\text{away}}}
\]

\[
\text{edge} =
p_{\text{model}} - p_{\text{market,fair}}
\]

\[
\text{EV}_i = p_i \cdot \text{net win} - (1-p_i) \cdot \text{stake}
\]

### Scoring

\[
\text{Log Loss}
=
-\frac{1}{n}
\sum_{i=1}^{n}
\left[
y_i \log(p_i)
+
(1-y_i)\log(1-p_i)
\right]
\]

\[
\text{Brier Score}
=
\frac{1}{n}
\sum_{i=1}^{n}
(p_i-y_i)^2
\]

### Point-in-time constraint

\[
\text{observed\_at} \le t^*
\]

### Live remaining-game probability

\[
P(\text{home win} \mid \text{inning, half, outs, bases, score, pitcher})
\]

### Valid live fill

\[
\text{decision\_ts}_k \le \text{quote\_ts}_{\text{used}}
\le \text{next material market update}
\]
