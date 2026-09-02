# MLB research, prediction, and website project review

> **Status: historical snapshot (2026-08-10), not maintained.** A point-in-time review kept for the record. Current direction: [`openspec/project.md`](../openspec/project.md).


Date: 2026-08-04

This is a technical and product review, not legal advice. The legal/data-rights findings below are serious enough that a qualified attorney or written permission from the relevant data owner should be obtained before a public or commercial launch.

## Executive assessment

This is already a substantial baseball data platform, not a starter project. The production database contains roughly 227,000 conformed games, 16.5 million Retrosheet events, 13.4 million raw Statcast pitches, 32,000 conformed market rows, 217,000 game-feature rows, and 28,000 historical prediction snapshots. The connector system, raw/core/gold layering, ID reconciliation, ingestion tracking, health checks, point-in-time feature discipline, and test coverage are all thoughtful foundations.

The project is not ready for a public betting-style website yet. The immediate work is not “add more features” or “start Astro.” It is to correct the evaluation and model-lifecycle layer, establish a lawful public-data boundary, and design a small serving contract. Four findings dominate everything else:

1. **Data rights are a launch blocker.** `docs/DATA_SOURCES.md` uses “Free” as if it meant reusable. It does not. Retrosheet expressly permits commercial products with prominent attribution, but MLB's current terms prohibit automated scripts that collect or interact with MLB digital properties. Sports Reference explicitly says scraped content cannot be used to build a competing database or to train predictive ML without permission. The current pipeline automates MLB/Statcast/Baseball-Reference collection and uses Baseball-Reference WAR in the model.
2. **The implemented `log5` formula is not the cited log5 formula.** The code and tests implement `pA² / (pA² + pB²)`. The cited SABR method is `pA(1-pB) / [pA(1-pB) + pB(1-pA)]`. This invalidates `log5-v1` as a named baseline and changes the baseline that gates whether the GBM is saved.
3. **The live 2026 evaluation counts repeated snapshots as independent games.** The database currently has hundreds of decided prediction *rows* but only 47 decided games common to GBM/Elo/log5 when one latest prediction per game is selected. The roadmap's `n=352/453/430` claims are snapshot counts, not independent game counts. The conclusion that GBM “genuinely wins live” is premature.
4. **There is no immutable model or prediction contract.** `gbm-v1` can be overwritten in place, its artifact is gitignored, and a prediction row stores no artifact hash, feature-set version, training cutoff, code commit, data cutoff, prediction horizon, starter/lineup status, or market timestamp. Historical predictions therefore cannot be reproduced or compared rigorously.
5. **The modern pitch-to-game linkage is badly incomplete.** In the live database, 12,598,817 of 13,421,741 `core.pitch` rows have no `game_id`. The defect is systematic in 2008–2025 (roughly 92.5%–98.9% unlinked by season), while 2026 is almost fully linked. Retrosheet encodes an ordinary game as number `0`, while MLB schedule data uses `1`; the conformance query assumed both used `0`. Historical franchise/display-name drift then prevents many remaining name-based matches. This must be repaired and the affected core/features/models rebuilt before any model result is trusted.

My recommendation is to reposition the product around **transparent baseball forecasts and research**, not an OddsTrader clone. The strongest differentiator is an open “why the probability moved” product that joins historical research, model uncertainty, feature provenance, model-versus-market tracking, and honest calibration. Odds grids are common; transparent model history and reproducible baseball research are not.

## Owner decisions recorded on 2026-08-04

The primary objective is a strong public portfolio/resume project and a useful research website. The commercial idea is display advertising plus affiliate links to regulated betting operators, but revenue is optional upside rather than the release criterion. That changes the recommended optimization target: prioritize technical credibility, reproducibility, public writing, and a polished user experience before advertising or affiliates.

The primary evaluator is now a hiring manager or data/ML practitioner, while the interface should still feel useful and exciting to a baseball fan. This is a productive two-layer design: the default surface is a polished forecast product; every result has a path into model cards, calibration, feature lineage, architecture, and reproducible research for technical reviewers.

The intended consumer positioning is “sports betting with AI,” aimed at mainstream sports fans, socially oriented bettors, and data-curious young adults. Do not define or target the audience as college students: that group includes people below the prevailing wagering age, and responsible-wagering standards specifically discourage college-focused promotion. Define the target as **legally eligible adults, 21+, who enjoy baseball and sports-betting analysis**. The tone can still be bold, entertaining, simple, and culturally current without using campus targeting or youth-coded creative.

The owner has no budget for data, hosting, odds, or weather beyond existing basic AI subscriptions. The initial product must therefore be valuable with a zero-dollar data plan and degrade honestly when a real-time input is unavailable. Free-tier limits must not silently become core production dependencies.

The owner wants forecasts published as often as possible. “As often as possible” should mean **whenever a material input changes**, plus named comparison cutoffs—not repeatedly publishing a new timestamp for an unchanged forecast. Store every material snapshot, but evaluate exactly one prediction per game at each named cutoff. A useful eventual sequence is overnight/opening, 24 hours, 6 hours, 1 hour, lineup-confirmed, and 15 minutes before first pitch, with event-driven reruns for starter, lineup, weather, or market changes.

That full intraday cadence is not possible from Retrosheet alone. Retrosheet is an excellent historical foundation, but a current-day forecast can only change as often as its lawfully usable current inputs change. A Retrosheet-only first release should therefore publish a clearly labeled team-strength or starter-neutral forecast when the schedule is available, update after newly completed games are ingested, and never imply that lineups, probable starters, weather, or live odds are current. Frequent intraday updates require a permitted real-time source or an explicitly documented manual input workflow.

The owner is willing to forgo monetization if that would permit a stronger product using additional sources. This is useful flexibility, but noncommercial status is **not** a general exception to source terms. If a source prohibits automated collection, public redistribution, competing databases, or predictive ML, removing ads does not remove that restriction. Obtain written permission/license or omit that source from the affected workflow.

Implement three explicit rights profiles rather than relying on display-layer filtering:

- `public_safe`: only sources approved for public display, redistribution as applicable, and predictive ML; compatible with later ads or affiliates.
- `licensed_full`: richer current-day sources covered by written permission or a commercial license.
- `local_research`: only sources whose terms expressly permit the particular private research use; never assume that “not public” or “not monetized” is sufficient.

Public serving tables, training sets, model artifacts, generated content, and downloads should be built from the selected profile's allowlist. Separate configuration, schemas/buckets, artifact registries, and CI checks should prevent data from a more restrictive profile from accidentally reaching a public deployment.

For the zero-budget profile, use Retrosheet as the baseball foundation and consider the National Weather Service API for U.S. venue forecasts. NWS describes its API as open data, free for any purpose, with reasonable rate limits and a required identifying User-Agent. Cache venue grid mappings and forecasts; retain issuance/retrieval timestamps so backtests use only weather information actually available at the prediction cutoff.

- [National Weather Service API documentation](https://www.weather.gov/documentation/services-web-API)

## What exists today

### Data and ingestion

The current pipeline has unusually broad coverage:

- Retrosheet parsed CSV, raw event files, game logs, box scores, rosters, schedules, transactions, and reference data.
- Chadwick player IDs and Lahman season data.
- MLB schedule, roster, transaction, play-by-play, live-state, probable-pitcher, venue, standings, and reference endpoints.
- Statcast pitch data and 18 leaderboard-style feeds.
- Baseball-Reference season statistics and WAR.
- Polymarket and Kalshi markets, snapshots, and optional price-history backfills.
- News/RSS headlines and summaries.

The raw/core/gold split is appropriate:

- `raw` preserves source-shaped records and tolerates drift.
- `core` resolves stable players, teams, games, venues, plays, pitches, markets, and WAR.
- `gold` currently holds a wide game feature table and prediction history.

This is meaningfully different from baseball.computer. The latter describes itself as a historical Retrosheet/Lahman database with a browser query layer, and its current repository builds a DuckDB database with SQLMesh. This project uses Postgres, live data, Statcast, market data, prediction workflows, and an intended consumer product. Using the same general tools or public facts is not copying; copying its names, prose, schema, CSS, assets, or distinctive interface would be.

References:

- [baseball.computer site](https://baseball.computer/)
- [baseball.computer repository](https://github.com/droher/baseball.computer)

### Existing models and features

The model pipeline currently provides:

- Formula baselines: `log5-v1` and `elo-v1`.
- `gbm-v1`: an XGBoost classifier with 37 configured inputs.
- Market comparison rows: `polymarket-v1` and `kalshi-v1`.
- Season-to-date record, last-10 record, run differential, Pythagenpat, and Elo.
- Starting pitcher FIP-like value and K/BB/HR rates.
- Team wOBA and a wRC+-named feature.
- Park factor, prior-season WAR, OAA, speed, and catcher framing.
- Bullpen quality and recent fatigue.
- Probable-starter and live-season adaptations for 2026.

The work shows strong awareness of target leakage. Many feature builders use only prior games, lag season aggregates by a full year, and explicitly leave unresolved values null. That discipline should become a formal feature-availability contract rather than remain only in module comments.

### Verification performed for this review

- `ruff check mlb_baseball tests`: passed at the initial review point; the focused conformance changes described below also pass Ruff and Python compilation.
- `./.venv/bin/pytest -q tests/unit`: 160 passed in 6.50 seconds.
- Focused integration tests for features/GBM/market/Elo/starter/bullpen: 11 passed before the run was interrupted after 9m21s because the suite was still spending long periods in database resets.
- The new game-linkage regression was attempted first against the shared default database and then against isolated/existing test databases. Concurrent agent activity contaminated the shared run; the isolated runs never reached the assertion because `conform.run()` spent more than five minutes in unblocked `DataFileImmediateSync`/`DataFileExtend` work for the full partitioned-table `TRUNCATE`. Only Codex's test processes were canceled. Record this test as **not completed**, not passed or failed; repeat it after the other database-heavy agent jobs finish.
- `mlb inventory`: completed and confirmed the live row counts summarized above.
- `mlb doctor`: interrupted after more than 90 seconds without output. It was stuck in the MLB API partition-coverage query.
- The main working tree was clean before this report was added. It now contains this untracked report plus the explicitly documented conformance/test changes below.

The system-level `pytest` executable is incompatible with the installed `anyio` plugin, but the repository's `.venv/bin/pytest` works. The project already has a committed `uv.lock`; standardize `uv sync`/`uv run` as the only documented local and CI path so this distinction is not tribal knowledge.

### Live worktree and branch coordination

Claude was actively working while the takeover audit ran. At the last coordination check, main and all three active feature worktrees still shared base commit `8b0476f`; an older SQLMesh spike worktree was seven commits behind main. The active, uncommitted scopes were:

| Worktree | Current scope | Files likely to merge |
|---|---|---|
| `agent-a97014c683b9d2011` | total prediction model | `model/total.py`, total tests, docs, `0029_gold_total_prediction.sql` |
| `agent-aa087ae3ffef36fe2` | reporting layer | `report.py`, reporting tests/docs, `0029_gold_reporting.sql` |
| `agent-ab96a738b3bf68449` | stacked model | `model/stack.py`, stack tests/docs |
| main/Codex | audit and game linkage | this report, `conform.py`, `test_conform.py` |

There is an immediate merge hazard: two worktrees independently created migrations with the `0029_` prefix. The runner sorts and records complete filenames, so both files may technically execute, but their relative order becomes name-dependent and the shared sequence number becomes misleading. Renumber one after deciding merge order and before either branch lands. Do not edit the same migration after it has been applied to any durable database.

The test suite also assumes a shared default database named `mlb_test`. Concurrent agent runs can block each other on `TRUNCATE` and can produce misleading failures from cross-test state. Every concurrent worktree should use a unique `TEST_DATABASE_URL`; CI should create a database per job or worker. The three Claude worktrees were already using dedicated `mlb_test_total`, `mlb_test_playerstats`, and `mlb_test_stack` databases in their focused commands; Codex moved its verification to `mlb_test_codex` after detecting the default-database collision.

These worktree observations are a point-in-time coordination record, not a claim that Claude's unfinished implementations are reviewed or ready to merge. Re-run `git worktree list`, status, diffs, tests, and migration ordering immediately before integration.

## Critical findings

### P0 — Separate “free to access” from “permitted to reuse”

The source registry needs a rights audit before public launch.

Retrosheet is the clearest source. Its current notice says recipients may make any desired use, including a commercial product, as long as its specified attribution appears prominently. That is a strong foundation for public research and derived statistics.

- [Retrosheet event data notices](https://www.retrosheet.org/game.htm#Notice)

MLB is different. Its current terms state that automated scripts may not collect information from or otherwise interact with MLB digital properties. The repo's MLB Stats API and Baseball Savant collection should not be assumed public-commercial-safe merely because endpoints respond without authentication.

- [MLB.com Terms of Use](https://www.mlb.com/official-information/terms-of-use)

Sports Reference is even more explicit for this use case. Its current data-use page says users should not create sites or tools from scraped Sports Reference data and its quoted terms prohibit using site data to create a competing database or to support machine-learning methods that predict, classify, label, or score inputs without permission. `core.player_war`, `war.py`, and the Baseball-Reference connector are therefore high-risk inputs for a public prediction product.

- [Sports Reference data-use policy](https://www.sports-reference.com/data_use.html)

Recommended action:

1. Add these fields for every source: `access_cost`, `license_or_terms_url`, `automated_access`, `redistribution`, `commercial_display`, `ml_training`, `required_attribution`, `last_reviewed`, and `status` (`green`, `permission-needed`, `private-research-only`, `remove`).
2. Treat MLB, Baseball Savant, Baseball-Reference, RSS summaries, Polymarket, and Kalshi as permission-needed until their exact terms are reviewed for the intended public product.
3. Make a “public-safe” data profile. A first public release can be built on Retrosheet, properly licensed Lahman material, original derived features, and any market source whose terms explicitly permit the intended use.
4. Remove Baseball-Reference WAR from public-model training unless written permission is obtained. A replacement can be built from Retrosheet/Statcast components that the project calculates itself, subject to the rights status of those underlying inputs.
5. Do not use MLB/team logos, uniforms, or copied OddsTrader assets. Team and league names raise trademark considerations even when game facts themselves are usable. Use original branding and a clear “not affiliated with MLB” statement reviewed by counsel.
6. Keep a source-attribution page and attach source lineage to each displayed metric.

AGPL licensing of this repository's code does not grant rights to redistribute upstream data.

### P0 — Correct the log5 baseline

Current implementation in `mlb_baseball/model/log5.py`:

```text
p_current(A beats B) = pA² / (pA² + pB²)
```

The cited log5 relationship is:

```text
p_log5(A beats B)
  = pA(1 - pB) / [pA(1 - pB) + pB(1 - pA)]
  = (pA - pA*pB) / (pA + pB - 2*pA*pB)
```

The SABR article states the defining property `P(x, .500) = x`. The current implementation fails that property: with a .600 team against a .500 team, it returns approximately .5902 rather than .6000. Existing tests encode the wrong squared formula and therefore protect the bug.

- [SABR: Probabilities of Victory in Head-to-Head Team Matchups](https://sabr.org/journal/article/probabilities-of-victory-in-head-to-head-team-matchups/)

After correcting it:

- Add tests for `P(.600, .500) == .600`, complement symmetry, equal teams, and boundary handling.
- Do not output exact 0 or 1 from tiny samples. Apply an empirical-Bayes prior or preseason strength prior before log5. Clipping only at scoring time hides poor probability construction.
- Re-run validation and the GBM save gate because the comparison baseline changes.
- Version the corrected baseline as `log5-v2`; preserve old rows as known-invalid historical output rather than silently relabeling them.

### P0 — Recompute the forward test at game grain

The current `gold.prediction` table intentionally stores repeated predictions. That is useful for line movement and model movement, but each row is not an independent outcome.

Live database state during this review:

| Model | All rows | Distinct games | Rows with outcome |
|---|---:|---:|---:|
| Elo | 13,885 | 793 | 565 |
| GBM | 2,163 | 173 | 456 |
| log5 | 12,748 | 689 | 550 |
| Polymarket | 21 | 21 | 21 |
| Kalshi | 21 | 21 | 21 |

When selecting the latest prediction for each decided game, there were only 53 Elo games and 47 GBM/log5 games. On the common 47-game sample, the current values were:

| Model | Games | Log loss | Brier | Accuracy |
|---|---:|---:|---:|---:|
| GBM | 47 | 0.6764 | 0.2417 | 0.5745 |
| log5 (known wrong formula) | 47 | 0.6928 | 0.2500 | 0.4894 |
| Elo | 47 | 0.6974 | 0.2521 | 0.4894 |

This small sample is directionally encouraging for GBM, but it cannot support the roadmap's strong conclusion. The prior `n=352/453/430` counts repeatedly weight the same games, exaggerate effective sample size, and understate uncertainty.

Create explicit evaluation cutoffs:

- `open`: first prediction after a market/game is available.
- `24h`: last prediction at least 24 hours before first pitch.
- `6h`: last prediction at least 6 hours before first pitch.
- `lineup`: first prediction after confirmed lineups, if available.
- `close`: last prediction before first pitch.

For every leaderboard:

- Select exactly one prediction per game per cutoff.
- Compare models on the exact same games.
- Cluster confidence intervals/bootstrap samples by game.
- Report coverage and missingness alongside scores.
- Report log loss, Brier score/decomposition, calibration plot, calibration slope/intercept, sharpness, and accuracy only as a secondary metric.
- For betting claims, compare against de-vigged executable prices and report closing-line value before reporting ROI.

### P0 — Make model versions immutable and reproducible

`models/` is gitignored, so a fresh clone has no `gbm-v1.json`; `mlb predict` silently emits zero GBM predictions until training succeeds. `mlb train` is described as optional even though it is required to reproduce the shipped prediction path.

Worse, successful retraining overwrites `models/gbm-v1.json` while old and new predictions retain the same `model_version`. A model version therefore does not identify a model.

Add:

```text
meta.model
  model_id
  name
  target
  artifact_uri
  artifact_sha256
  git_sha
  feature_set_version
  train_start
  train_end
  parameters_json
  metrics_json
  created_at
  status

meta.model_run
  run_id
  model_id
  data_cutoff
  source_snapshot/version
  started_at
  finished_at
  status/error
```

Then store `model_id`, `run_id`, `data_cutoff`, `prediction_cutoff`, and `feature_snapshot_id` on every prediction. Never overwrite an artifact in place; promote a new immutable artifact to “champion.”

The current save rule—replace the model if its point-estimate log loss is microscopically below both baselines—is too weak. The original reported GBM/Elo difference was around 0.0004. Require a minimum practical improvement or uncertainty interval and compare against the current champion, not only the formula baselines.

## Important modeling and data issues

### The validation set has become a development set

The project repeatedly added features and checked whether they improved the same 2024–2025 validation period. That period is no longer an untouched validation set; repeated human choices can overfit it even if XGBoost never trains on it directly.

Use rolling-origin evaluation, for example:

- Train through 2018, validate 2019.
- Train through 2019, validate 2020.
- Continue through 2024/2025.
- Aggregate fold metrics, then keep the newest complete season as a final untouched test until the modeling cycle is frozen.
- Preserve 2026 as forward monitoring, one game per cutoff.

### Ancient data may hurt a modern forecast

The current training set reaches deep into baseball history while most rich optional features exist only in modern eras. XGBoost can handle null values, but it cannot make 1870s–1990s baseball structurally equivalent to today's rules, travel, bullpen usage, talent pool, schedule, ball, DH, and Statcast environment.

Benchmark at least three training regimes:

- Modern: 2015 onward, full Statcast era.
- Recent broad: 2008 onward, pitch-tracking era.
- Historical: all available years with era indicators and recency weights.

Choose based on rolling out-of-sample performance. The research database should preserve all history; the production predictor does not need to train on all of it.

### Feature availability needs an explicit contract

“No target leakage” is necessary but not sufficient. A feature must have been knowable at the promised prediction time.

- Historical starter features use the pitcher who actually started; live rows use the probable pitcher. That is valid only for a lineup/confirmed-starter model. For a prior-day model, it creates training-serving skew and ignores scratches.
- Historical weather values are observations at the park. A live pregame model needs archived forecast snapshots, not observed weather.
- Historical starting lineups can be used only for a “lineups confirmed” forecast unless historical announcement timestamps are available.
- Market prices need bid/ask, liquidity, timestamp, and a clear rule for last trade versus executable midpoint.

Define each feature with:

```text
name, grain, source, event_time, available_at, max_staleness,
backfill_method, null_meaning, transformation_version, rights_status
```

Build `gold.game_snapshot` at `(game_key, as_of, cutoff)` grain rather than treating the continually rebuilt wide row as the full historical record.

### Configured, computed, and documented features have drifted

- `home_rest` and `away_rest` are computed and almost fully populated but are not in `gbm.FEATURE_COLUMNS`.
- `home_starter_rest` and `away_starter_rest` are populated but not used by GBM.
- Catcher framing is populated but deliberately excluded after a failed retrain.
- `day_night`, temperature, and wind columns exist in `gold.game_feature` but had **zero populated rows** during this review.
- The roadmap says the 37-column GBM uses every feature described above, which is false for rest and framing.
- The top-level README/North Star/Architecture still describe Phase 2 as not started, while the roadmap describes a live model.

Generate model cards and feature lists from code/registry metadata so documentation does not manually drift.

### Some metric names overstate what is computed

- `home_starter_era` stores FIP, not ERA. Rename it to `home_starter_fip` in the next schema version.
- FIP uses a fixed 3.10 constant across all eras. That may be acceptable for within-season rank but is not era-accurate; use season constants or standardized components.
- wOBA uses one modern fixed set of weights across all seasons. Call it a fixed-weight wOBA proxy or derive season-specific linear weights from the project's run-expectancy data.
- The `wRC+` formula is a simplified custom adjustment, not a faithful public wRC+ calculation. In particular, it applies a raw home/road park ratio directly to full team offense. Either document it as a custom `offense_plus` feature or implement a fully specified run/PA and park adjustment.
- Park factor is a raw home/road run-scoring ratio. That is useful, but distinguish raw venue run factor from a player/team park adjustment. MLB's own example puts 2018 Coors at 1.271 using the raw ratio; Baseball-Reference describes additional adjustment and multi-year calculation steps.

References:

- [MLB Ballpark Factor definition](https://www.mlb.com/glossary/advanced-stats/park-factor)
- [Baseball-Reference park-adjustment methodology](https://www.baseball-reference.com/about/parkadjust.shtml)

### Model design is too narrow for the stated product

The current GBM has fixed hand-chosen hyperparameters, no probability calibrator, no early stopping, no recorded random seed/model parameters, no feature-importance history, and no drift monitoring. XGBoost is a reasonable model, but it should be one contestant in a disciplined experiment framework.

Add a simple regularized logistic regression immediately. If XGBoost cannot materially and consistently beat a calibrated linear model and Elo across rolling folds, complexity is not earning its keep.

### Prediction identity needs improvement

This review's earlier conclusion about `mlb_game_pk` is superseded by a
2026-08-10 source and production-data audit. Repeated schedule rows represent
postponement or suspended/resumed history under one MLB game key, not two MLB
games. Canonicalize one MLB game per `game_pk`, preserve schedule observations
in `raw`, and retain `retro_game_id` for a record without a safe MLB crosswalk.
See `GAME_INSTANCE_IDENTITY.md` and `KNOWLEDGE_BASE.md`.

### Market data is not yet an odds product

Current market rows are mainly retrospective because `core.market` only matches completed `core.game` rows. A live site needs upcoming-game matching and quote snapshots before first pitch.

Also retain and display:

- bid, ask, last, midpoint, spread, volume, open interest/liquidity;
- market type and period (full game, first five, run line, total);
- captured time, scheduled start, and time-to-start;
- both outcomes and normalized/de-vigged probability where applicable;
- stale/closed/suspended flags.

A last trade from an illiquid market is not necessarily an executable probability. Do not present model-market “edge” without accounting for the price a user could actually obtain.

## Recommended model portfolio

Build diverse models that answer different questions. Diversity is what makes later ensembling useful.

### Tier 1 — trustworthy baselines

1. Corrected log5 with preseason shrinkage and home-field adjustment.
2. Tuned Elo with rolling validation of K, reversion, home advantage, margin multiplier, travel, and starting-pitcher adjustment.
3. Regularized logistic regression on feature differences rather than separate home/away columns.
4. Market-only baseline using timestamped, executable, de-vigged prices.

### Tier 2 — production game models

1. Calibrated XGBoost/LightGBM/CatBoost with modern-era training and rolling folds.
2. Explainable Boosting Machine or generalized additive model for nonlinear but readable effects.
3. Dynamic Bradley–Terry or hierarchical Bayesian team-strength model with partial pooling, offseason reversion, and pitcher effects.
4. Stacked ensemble trained only on out-of-fold, chronological base-model predictions. Never train the meta-model on in-sample base predictions.

### Tier 3 — runs and derivative markets

A binary winner model cannot naturally produce totals, run lines, or team totals. Build a paired run model:

- Negative binomial or Poisson-style home/away run distributions with correlated/overdispersed residuals.
- Derive win, run-line, total, and team-total probabilities from the joint score distribution.
- Calibrate each target separately.

This becomes far more reusable than training an unrelated classifier for every market.

### Tier 4 — matchup and player models

1. Plate-appearance outcome model: K, BB/HBP, HR, ball in play, hit/out conditional on batter, pitcher, handedness, park, count-neutral pitch traits, and defense.
2. Pitcher strikeout model: projected batters faced × per-batter K probability, with pitch count and bullpen hook distribution.
3. Batter hits/total-bases/HR models using playing-time probability and lineup slot.
4. Bullpen availability/usage model predicting which relievers are actually available and likely to pitch.
5. Monte Carlo game simulator built from plate-appearance or half-inning transition probabilities.

### Tier 5 — research models

- Base/out Markov run expectancy and RE24.
- In-game win probability with score, inning, base/out state, batter/pitcher, and bullpen state.
- Player aging/projection system inspired by Marcel but implemented from the project's own permitted data.
- Pitch-quality models: Stuff-like, Location-like, and Pitching-like components based on velocity, movement, release, command, and pitch outcome.
- Change detection for pitcher velocity, spin, release point, arsenal mix, and hitter bat speed/contact quality.

## Feature backlog, prioritized by likely value

### Highest value

1. **Confirmed lineup strength.** Project each batter's point-in-time offensive value, handedness split, lineup slot, and replacement penalty. Provide separate probable and confirmed-lineup forecasts.
2. **Probable/confirmed starter status.** Track announcement/scratch history and expose uncertainty when no starter is confirmed.
3. **Pitcher quality with recency and opponent adjustment.** Rolling xFIP/SIERA-like components, velocity/movement trends, pitch count, times-through-order behavior, platoon splits, and pitch-mix matchup.
4. **Bullpen availability.** Reliever-level pitches/outs over 1/2/3/5 days, back-to-back usage, role, handedness, travel, and closer/setup availability, aggregated using only likely available pitchers.
5. **Injuries and roster state.** IL moves, transactions, call-ups/options, days since return, and projected missing WAR/run value. Prefer structured permitted sources over article text.
6. **Weather forecast snapshots.** Temperature, humidity, wind speed and direction relative to home plate, precipitation, roof state, forecast provider, and forecast issuance time.
7. **Travel and circadian effects.** Distance, time-zone changes, road-trip length, getaway day, night-to-day turnaround, and altitude change.
8. **Park factors by event and handedness.** Runs, HR, 2B/3B, singles/BABIP, strikeouts/walks, and left/right batter factors with shrinkage.

### Strong second wave

- Opponent-adjusted rolling team offense/pitching rather than raw season totals.
- Quality-of-contact: xwOBA, barrel%, hard-hit%, launch-angle distribution, bat speed, and rolling stabilization/shrinkage.
- Defense by position and projected lineup, not only prior-year team OAA.
- Catcher framing and throwing tied to the expected catcher, not prior-year team total.
- Umpire called-strike tendencies, handedness interaction, and consistency, if available under acceptable terms and known before the game.
- Baserunning value rather than average sprint speed alone.
- Schedule strength and recent opponent quality.
- Manager tendencies: bullpen hook, intentional walks, steals, platoons, and rest patterns.
- Interleague/DH/rule/ball-era indicators for historical models.
- Market movement, disagreement between markets, liquidity, and stale-quote age as comparison signals first; only later as model inputs.

### Features to avoid or constrain

- Same-game box-score, winning/losing pitcher, settled price, or post-start information.
- Final/current season aggregates used for earlier games in that season.
- Actual weather in a forecast model without archived forecast timestamps.
- Actual starter/lineup in a forecast claimed to exist before those facts were announced.
- Raw news sentiment without timestamp, team/entity resolution, deduplication, and a demonstrated incremental benefit.
- Hundreds of correlated rolling windows added without feature ablations and stability checks.

## Conformance and database audit

### Keep `conform.py`, but stop growing it as a monolith

`mlb_baseball/conform.py` is roughly 1,600 lines and currently combines five different responsibilities: orchestration, source prerequisites, identity resolution, core fact/dimension construction, and market-name parsing. It contains valuable source-specific logic that should not be thrown away, especially multi-pass player/team/game reconciliation that is awkward or unsafe to express as a single SQL model.

Do not rewrite the whole file in SQLMesh, dbt, or dlt. Refactor it behind the current `run()` entry point into bounded modules:

```text
conform/
  orchestrator.py
  dimensions.py
  identity.py
  games.py
  events.py
  markets.py
  sql/                 # versioned set-based statements where useful
```

Preserve one transaction boundary or a deliberate staged-publish protocol per logical build. Add a Postgres advisory lock so two schedulers cannot conform simultaneously. For large rebuilds, populate staging tables, validate row counts/keys/linkage, and swap or merge into the published core instead of truncating the serving tables at the start. A failed transform should leave the last known-good core available.

Keep Python for parsing, fuzzy/heuristic identity resolution, multi-pass reconciliation, exception policy, and ML training. Move deterministic set-based gold features and serving marts into SQLMesh. Keep schema DDL in numbered migrations.

### P0 linkage defect found during takeover

The live database proves that a row-count-only health check is insufficient:

- `core.game`: 227,054 rows; 7,977 have a missing home or away team; 200,770 have no MLB `game_pk` (many older historical rows are expected not to have one).
- `core.pitch`: 13,421,741 rows; 12,598,817 have no conformed `game_id`.
- `core.play`: 16,485,138 rows; 44,227 have a missing batter or pitcher link.
- In 2024, exact current name/number matching linked only 48 core games. Normalizing the single-game number and matching through numeric team IDs identifies roughly 2,471 candidates.

The primary defect is a source semantic mismatch: Retrosheet uses game number `0` for a normal game while MLB schedule rows normally use `1`. The current comment and equality in `_backfill_game_pk` said both use `0`. A second mismatch comes from MLB applying current display names to historical schedule rows (for example Guardians, Rays, Angels/Athletics) while Retrosheet preserves era-specific team names.

The takeover patch changes the first pass to normalize `0`/null to `1` and adds a second pass through the learned numeric MLB team-ID crosswalk, while preserving the existing policy of leaving ambiguous duplicate source IDs null. A production rebuild has deliberately **not** been run during this review because `conform.run()` is a large mutating operation and Claude is working concurrently. Before publishing model metrics:

1. Land and verify the focused integration test in an isolated database.
2. Back up or snapshot the current core/gold state.
3. Rebuild conformance once no other ingest/model job is active.
4. Require modern-season `core.pitch.game_id` coverage near the source-appropriate expectation, not merely equal raw/core row counts.
5. Rebuild every feature and model artifact whose inputs depended on the bad linkage.
6. Re-run chronological evaluation; do not compare pre-fix and post-fix scores as if they used the same dataset.

### Table design assessment

The raw/core/gold layering is sound, and core entities generally have primary/foreign keys. The gaps are contracts, grain, and safe publication:

- Raw has about 138 relations and roughly 46 GB of data, but only one raw table has a primary key. Source-faithful text landing is reasonable; it still needs per-table natural-key/dedup policy, source snapshot/run identity, and explicit append-versus-replace semantics.
- Core has hundreds of relations including season partitions and roughly 7 GB. Stable surrogate IDs are appropriate, but cross-source IDs should live in versioned mapping tables with valid-time/source/confidence rather than accumulating nullable IDs and abbreviation maps on dimensions.
- Gold currently has only two large, wide tables (roughly 945 MB). Independent feature builders repeatedly updating one shared `gold.game_feature` row creates ownership conflicts, expensive rewrites, and poor lineage. Use one narrow model/table per feature family at an explicit grain, then assemble a versioned final feature snapshot.
- Core and gold currently have no `CHECK` constraints. Add carefully chosen checks for probability `[0,1]`, nonnegative counts, allowed status/cutoff enums, home/away inequality, and required timestamps. Keep uncertain source values nullable rather than coercing bad data.
- Prediction uniqueness needs `(game_key, target, model_id, cutoff, generated_at)` or a prediction ID, not `mlb_game_pk` alone.
- Add a dedicated `serve` schema containing only narrow, rights-filtered, documented website marts. Astro should never connect directly to `raw`, broad `core`, or training tables.

For every important relation, document: grain, primary key, natural key, event time, availability time, ingestion time, source/run, update strategy, rights profile, retention, and downstream owners. Enforce those contracts with SQLMesh audits or equivalent tests plus database constraints where the invariant is absolute.

## Ingestion and deployment security audit

The pipeline has good foundations: parameterized Psycopg usage is common, dynamic identifiers usually use `sql.Identifier`, subprocesses use argument arrays rather than `shell=True`, `literal_eval` is used instead of `eval`, HTTPS certificate verification is left enabled, and the Chadwick source is pinned to a commit in CI. It is not safe to expose as a public website database in its current operating configuration.

### Immediate host/database issues

- The current application role is a Postgres superuser with `CREATEDB` and `CREATE` on data schemas. Split it into owner/migration, ingest writer, transform writer, and website read-only roles. The website credential should only have `SELECT` on approved `serve` views/tables.
- Postgres has SSL enabled but listens on all IPv4/IPv6 interfaces, accepts several LAN/container/Tailscale ranges, and the inspected connection was not using SSL. Restrict `listen_addresses`/firewall exposure to actual clients, prefer Unix sockets locally, require TLS for remote routes, and use SCRAM rules explicitly rather than legacy `md5` HBA labels.
- The local `.env` is gitignored but mode `0664`, allowing unrelated local users to read it. Change secret files to `0600`; keep production secrets outside the repository and rotate any credential that may have been exposed.
- `PUBLIC` can connect to the database but did not have usage on raw/core/gold and could not create in `public`, which is a useful existing control. Retain that deny-by-default posture.

### Ingestion hardening

- Remote ZIPs are extracted with `extractall` and no explicit member-path, decompressed-size, entry-count, or compression-ratio validation. Validate every archive member remains under a new temporary directory, cap compressed and decompressed sizes, reject links/special files, then atomically promote validated output.
- HTTP downloads are buffered in memory and destination/manifest writes are non-atomic. Stream to a temporary file with byte limits, calculate a checksum, `fsync` as appropriate, then rename atomically. Write manifests the same way.
- Raw schema evolution silently adds all-text columns. Reject sanitized-name collisions and empty names; record schema fingerprints; alert on additions/removals/renames; require explicit review when a source change affects a conformed field.
- Append-style loads need declared conflict keys or immutable snapshot IDs. “Loaded successfully twice” must not mean “duplicated twice.”
- Separate daily and five-minute filesystem lock files allow the two schedules to overlap while touching some of the same source tables. Use one database advisory lock per connector/resource plus a conformance lock; filesystem PID reaping is not sufficient across containers or hosts.
- The custom migration runner lacks a global advisory lock and applied-file checksums. Add both before concurrent deployments are possible.
- CI actions use moving version tags. Pin third-party actions to reviewed commit SHAs and enable dependency/security update automation.

Security priority order: isolate the database and create the read-only serving role first; fix secrets/network rules second; harden remote archives/downloads third; then add migration/schema-drift controls. Do not put Postgres directly behind the public Astro site or a tunnel using the current superuser credential.

## SQLMesh, dbt, and dlt decision

Use **SQLMesh selectively**, keep the custom ingestion connectors, and do not add dbt or dlt now.

| Tool | What it is best at here | Decision |
|---|---|---|
| SQLMesh | versioned SQL models, plans/environments, incremental gold builds, audits, lineage, table diffs | Adopt for new deterministic gold and `serve` models after P0 correctness fixes |
| dbt | widely recognized SQL transformation workflow and ecosystem | Do not add alongside SQLMesh; it would duplicate responsibilities and discard a spike that already tied out real models |
| dlt | API/file extraction and loading with state/schema evolution | Do not rewrite existing domain-specific connectors; reconsider only for a future generic permitted JSON source |

The repository's SQLMesh spike already did the work a framework evaluation should do: it tied out venue, park-factor, and team-wOBA outputs, exercised plans/environments/incremental models/audits, and documented why multi-pass identity and market matching do not port cleanly. SQLMesh's official concepts directly cover blocking/nonblocking audits, change plans, isolated environments, and incremental restatement. dlt's official scope is loading pipelines, state, and schema evolution; it is not a conformance or ML orchestration replacement.

- [SQLMesh audits](https://sqlmesh.readthedocs.io/en/stable/concepts/audits/)
- [SQLMesh plans](https://sqlmesh.readthedocs.io/en/stable/concepts/plans/)
- [SQLMesh environments](https://sqlmesh.readthedocs.io/en/stable/concepts/environments/)
- [dlt introduction](https://dlthub.com/docs/intro)
- [dlt schema evolution](https://dlthub.com/docs/general-usage/schema-evolution)
- [dlt pipeline state](https://dlthub.com/docs/general-usage/state)

The adoption boundary should be explicit:

- SQLMesh owns narrow, deterministic, set-based feature modules, final feature snapshots, evaluations, and website marts.
- Python owns source adapters, archive parsing, entity resolution, feature logic that truly requires Python, model training/calibration, artifact registration, and prediction orchestration.
- Numbered migrations own schemas, constraints, roles/grants where appropriate, and non-model operational tables.
- Astro reads only `serve` outputs or pre-generated JSON; it does not become a transformation engine.

Before adding more SQLMesh models, replace the shared-wide-table update pattern. Each feature model should declare one grain and one owner; a final model joins them at a named as-of/cutoff and has blocking key/range/temporal audits. This makes lineage meaningful and prevents two feature jobs from racing to update the same row.

## Recommended data/ML architecture

Keep Postgres. The data volume does not justify replacing it. Split responsibilities more clearly:

```text
sources
  -> raw immutable/source snapshots
  -> core conformed facts and dimensions
  -> point-in-time feature snapshots
  -> immutable model runs and predictions
  -> narrow serving marts/API
  -> Astro pages and interactive islands
```

Recommended tables/views:

- `gold.game_snapshot`: one row per game/cutoff/as-of with source availability flags.
- `gold.feature_value` or versioned wide snapshot tables: immutable feature materialization.
- `meta.feature`: definitions, ownership, event/availability time, version, rights status.
- `meta.model` and `meta.model_run`: immutable artifacts and experiment records.
- `gold.prediction`: target, side, model ID, cutoff, probability, uncertainty, generated time, outcome.
- `gold.evaluation`: reproducible metrics by model, cutoff, season/fold, and common sample.
- `gold.market_quote`: upcoming/finished game identity, market type, bid/ask/last, volume, capture time.
- `gold.daily_game`: narrow denormalized serving mart for the website.
- `gold.game_detail`: feature explanations, latest forecasts, market comparison, freshness.
- `gold.model_scorecard`: calibration and performance summaries.

The SQLMesh spike demonstrates real value for incremental gold transformations, audits, lineage, and table diffs. Adopting it for `model/` transformations is reasonable even though baseball.computer also uses SQLMesh; SQLMesh is a general tool, not their proprietary design. Keep the implementation, schemas, model definitions, prose, and UI independently designed. Do not migrate the complex conformance layer until the gold-layer adoption proves operationally stable.

## Operational and code-quality findings

### Health checks are too expensive and silent

`mlb doctor` buffers all output until every health check finishes. During this review it appeared hung for more than 90 seconds in `mlb_api.health_check()`.

The partition-coverage SQL runs a correlated distinct-count subquery against large unindexed raw tables once per season. Rewrite it as pre-aggregated CTEs joined by season, add a statement timeout, time each check, and stream results as they complete. Provide `mlb doctor --quick` and `--deep`; expensive historical reconciliations belong in the deep mode or scheduled audits.

### Inventory is noisy and slow

`mlb inventory` emits every empty yearly `core.pitch_*` and `core.play_*` partition, producing hundreds of zero-row lines. Aggregate partitioned parents by default and add `--partitions` for detail. Use catalog estimates for a fast default and `--exact` for full counts.

### Full rebuilds are becoming the bottleneck

Many model operations truncate and rebuild broad tables. The focused integration selection advanced only 11 tests in 9m21s. Continue the SQLMesh/incremental work for gold features, and redesign test cleanup so model tests do not repeatedly synchronize hundreds of partitions.

### Dependency reproducibility is incomplete

`pyproject.toml` has broad lower bounds and the repository now has a committed `uv.lock`, but local commands do not consistently use it. A system `pytest`/`anyio` mismatch demonstrates how easily environments still drift. Document `uv sync --frozen` and `uv run` as the canonical setup/execution path, verify the lock in CI, pin the runtime Python versions tested, and run unit/lint/type/integration jobs separately.

### A few implementation details should be corrected

- Add `game_number`/scheduled timestamp to the Elo ordering; accepting arbitrary doubleheader order is unnecessary.
- Add a prediction horizon so the system does not publish forecasts for every scheduled game through September as if all have equal information. During review, 740 undecided feature rows extended from August 4 through September 27.
- Avoid returning zero silently when the GBM artifact is missing; fail the model check prominently while allowing the other models to run.
- Replace hard-coded current-team abbreviation maps with versioned identity mappings where a permitted numeric ID is unavailable.
- Generate schema and feature documentation from registered definitions.
- Revisit stale comments: several module docstrings still describe features as unbuilt after they were implemented.

## Astro website recommendation

### Positioning

Do not build “OddsTrader, but ours.” Build an original product with this promise:

> Transparent MLB forecasts, the evidence behind them, and an open research database.

OddsTrader's current MLB page centers on a dense sportsbook odds grid, best-line shopping, line movement, injuries, weather, rankings, and matchup pages. Those are useful category conventions, but duplicating its layout, copy, visual hierarchy, brand treatment, or interaction details is unnecessary and increases trade-dress/copyright risk.

- [OddsTrader MLB page](https://www.oddstrader.com/mlb/)

Original differentiators:

- A probability range and confidence/uncertainty, not a fake precise “pick.”
- “Why it moved” since open/yesterday/lineup confirmation.
- Model consensus and disagreement.
- Model versus market with price freshness and liquidity.
- Starter/lineup/weather confirmation status.
- Public calibration and model scorecards.
- Every feature linked to methodology, timestamp, and source.
- A research mode with downloadable query recipes and reproducible examples.
- Historical “what did the model know then?” pages from immutable snapshots.

### MVP pages

1. `/mlb` — today's slate: time, teams, starter status, model probability/range, market comparison, change, freshness.
2. `/mlb/game/[gameKey]` — matchup explanation, feature deltas, forecast timeline, market timeline, scenario changes, source freshness.
3. `/models` and `/models/[id]` — model card, training period, features, calibration, common-sample comparison, change log.
4. `/research` — database overview, data dictionary, example analyses, source/license notes.
5. `/teams/[slug]`, `/players/[slug]`, `/parks/[slug]` — research-oriented historical pages, introduced after the daily product works.
6. `/methodology`, `/data-sources`, `/responsible-use`, `/terms`, `/privacy`.

### Astro shape

Use Astro's default static output for methodology, research, model cards, and evergreen pages. Render the daily slate and matchup routes on demand with a Node adapter and short cache headers. Use small interactive islands only for charts, filters, and live refresh.

Astro's official docs recommend starting with static output and opting individual routes into on-demand rendering. Its server endpoints can securely execute backend code, and islands allow interactive components without turning the entire site into a client-side app.

- [Astro on-demand rendering](https://docs.astro.build/en/guides/on-demand-rendering/)
- [Astro islands architecture](https://docs.astro.build/en/concepts/islands/)

Suggested repository layout:

```text
mlb_baseball/       Python ingestion/modeling
transforms/         versioned SQL transformations
site/               Astro application
  src/pages/
  src/components/
  src/lib/server/
  src/content/
```

The Astro server should query only narrow serving marts through a read-only database role. Never expose `raw` or permit arbitrary public SQL in the first product version. Cache the daily slate for 30–60 seconds, but keep HTTP refresh frequency separate from model generation frequency. Every forecast should display `generated_at`, `data_cutoff`, prediction horizon, and the state of important inputs. Polling the page every minute must not create a false sense of freshness when the underlying lawful source has not changed.

### Portfolio-first visual experience

The site should be visually memorable because it communicates information well, not because it imitates OddsTrader. Build an original “baseball forecasting terminal” with a restrained stadium-scoreboard influence and modern analytical graphics. The strongest showcase routes are:

- **Daily forecast board:** matchup cards with win probability, uncertainty, model disagreement, data freshness, and the largest change since the previous cutoff.
- **Game forecast story:** a probability timeline with annotations for every material input change and a feature-contribution waterfall explaining the current result.
- **Scenario lab:** clearly hypothetical controls for starter, lineup-strength, park, and weather assumptions, backed by a versioned model rather than arbitrary UI arithmetic.
- **Model scorecard:** calibration curve, Brier/log-loss history, matched-sample comparisons, confidence buckets, and honest recent misses.
- **Season replay:** move a date slider through the season and see exactly what the model knew and predicted at that time.
- **Research explorer:** curated questions, saved reproducible queries, definitions, and downloadable results rather than unrestricted production SQL.
- **Data lineage view:** trace a displayed prediction through source, ingestion run, feature version, model artifact, and prediction snapshot.
- **Engineering page:** a concise architecture diagram, reliability indicators, test strategy, performance numbers, and design decisions aimed directly at technical reviewers.

The daily board earns attention; the replay, lineage, calibration, and architecture views earn credibility with hiring managers.

### Betting outputs without a paid odds feed

The owner wants all three presentation layers: model probabilities, analytical edges, and explicit picks. Keep them distinct so the product remains mathematically honest:

1. **Forecast:** the model's calibrated win probability and uncertainty.
2. **Fair price:** American/decimal odds implied by that probability before vig.
3. **Winner lean:** the team more likely to win; this is not automatically a profitable bet.
4. **Playable-price threshold:** “bet only at `X` or better,” calculated from the model probability plus a configurable safety margin.
5. **Market edge:** calculated only when a time-stamped permitted quote exists or the user enters the available sportsbook odds.
6. **Pick:** a conditional recommendation containing market, minimum acceptable price, model version, data cutoff, expiration, and rationale.

A zero-cost MVP should include a client-side odds input. The user enters the price currently offered by a sportsbook; the browser calculates implied probability, estimated edge, and expected value against the published model. The server need not store the user's quote. This is more defensible than scraping live odds and is a good interactive portfolio feature.

Never label the higher-probability team as a positive-value bet without accounting for price. For example, a 60% winner forecast has fair American odds near `-150`; taking that team at `-190` may still be negative expected value. Every explicit pick should therefore be conditional on a minimum price, not just a team name.

### AI marketing without AI theater

“AI-powered MLB forecasts” is a legitimate top-of-funnel description if the product uses trained statistical/ML models, but the technical pages should name the actual methods. A strong brand promise is:

> AI-powered MLB forecasts. Every pick explained. Every prediction tracked.

Support that promise by publishing every pregame prediction before the outcome, retaining losses, reporting calibration and proper scoring rules, and showing which model generated each forecast. Avoid “locks,” guaranteed-profit language, invented confidence, selective win screenshots, fake live updates, or implying that use of AI alone creates an edge. The marketing can simplify the mechanics without misrepresenting performance.

### Content strategy

Create factual templated content from structured records:

- daily slate summary;
- largest model/market disagreements;
- probability movers and their feature causes;
- starter changes and model impact;
- weather/park scenarios;
- weekly calibration and “what the model got wrong” review;
- research notes derived from reproducible queries.

If an LLM is later used for prose, give it a small fact packet, require every numerical claim to come from that packet, store the prompt/model/version, and label generated content. Do not feed article bodies or restricted data into a generative model without rights.

### Responsible presentation

- No guaranteed-win language.
- Separate probability quality from betting value.
- Show sample sizes and uncertainty.
- Explain that users can lose money and provide responsible-gambling resources if betting content is included.
- Do not infer jurisdictional legality; terms and geolocation requirements need separate review.
- Treat advertising and sportsbook affiliates as removable adapters around the product, never as inputs to editorial ranking or model output.
- Do not publish affiliate links until data rights, operator program terms, clear and conspicuous commission disclosures, age/jurisdiction rules, responsible-gambling presentation, and business structure are settled. The FTC says the financial relationship should be disclosed close to the recommendation or link; a buried disclosure page is insufficient.
- [FTC affiliate disclosure guidance](https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking)
- Do not target college campuses or audiences under 21. The American Gaming Association's current responsible-marketing code says sports-wagering marketing should be aimed at adults 21+ and prohibits promotional college partnerships apart from limited responsible-gambling/alumni contexts.
- [AGA Responsible Marketing Code](https://www.americangaming.org/marketing-code/)

## Prioritized roadmap

### Stage 0 — correctness and rights (now)

1. Coordinate and review Claude's three active worktrees; resolve the duplicate `0029` migration number before merging anything.
2. Repair game-number/team-name linkage, rebuild core/features, and add non-null linkage coverage gates by modern season.
3. Build the source-rights matrix and implement a Retrosheet-first public-safe allowlist that removes/segregates red sources from training, serving, downloads, and generated content.
4. Correct log5 as `v2` and re-run all baselines.
5. Rewrite forward evaluation to one game per cutoff on matched samples.
6. Create immutable model/model-run metadata and prediction provenance.
7. Freeze an untouched evaluation period and adopt rolling-origin folds.
8. Create least-privilege database roles, lock down remote Postgres access, fix secret permissions, and isolate a read-only `serve` schema.
9. Update README/North Star/Architecture to reflect actual status.
10. Add the newly available Retrosheet discrepancy files to the source backlog. The current Retrosheet site now publishes discrepancy files by decade through 1986, contradicting the repository's statement that this product does not exist.

### Stage 1 — trustworthy winner forecast

1. Define prediction cutoffs and feature availability contracts.
2. Add logistic/GAM baselines and calibrated modern-era GBM experiments.
3. Tune Elo rather than treating chosen constants as fixed.
4. Add confirmed/probable starter distinction, lineup state, and bullpen availability.
5. Produce calibration dashboards and champion/challenger promotion rules.
6. Adopt SQLMesh for new narrow gold/serving transforms; do not migrate `conform.py` wholesale.
7. Initially label forecasts as starter-neutral unless a permitted, time-stamped source supplies the probable or confirmed starter.

### Stage 2 — serving layer and Astro MVP

1. Build `daily_game`, `game_detail`, and `model_scorecard` serving marts.
2. Scaffold `site/` with an original visual system and no copied assets/layout.
3. Ship the daily forecast board, game forecast story, model scorecard, methodology, sources, engineering, and responsible-use pages.
4. Add cached server endpoints and a read-only DB role.
5. Add monitoring for data freshness, missing starters, failed prediction runs, and stale pages.
6. Add the client-side odds/edge calculator and conditional playable-price output without depending on a live odds vendor.

### Stage 3 — market and content product

1. Match upcoming markets to scheduled games.
2. Store executable quote fields and calculate normalized probability/edge.
3. Add forecast and market timelines.
4. Add generated-but-grounded previews and weekly model reviews.
5. Evaluate usage before adding accounts, alerts, personalization, display advertising, or affiliate monetization.
6. Keep the site fully functional when every advertisement and affiliate component is disabled.

### Stage 4 — totals, props, and simulation

1. Joint run distribution model.
2. First-five, total, run-line, and team-total outputs.
3. Batter/pitcher matchup and player prop models.
4. Plate-appearance simulator and in-game win probability.
5. Formal out-of-fold stacked ensemble.

## Remaining product and strategy questions

The portfolio audience, zero-dollar operating constraint, optional ad/affiliate monetization, desire for maximum meaningful forecast cadence, all three betting-output layers, and willingness to change the data profile are now decided. These questions still materially affect the design:

1. Should the public database offer downloads, a documented API, browser SQL, or only curated research pages at first?
2. Is self-hosting required, and what machine/network will serve Astro and Postgres?
3. Are user accounts/alerts part of the first release, or can it be fully public and anonymous?
4. How open should the model be: full source/artifacts, methodology only, or a split between open research and proprietary production models?

## Final recommendation

The database is the strongest part of the project. Preserve it, but stop treating source breadth as the main success metric. The next milestone should be:

> A legally scoped, reproducible, calibrated pregame winner forecast with immutable snapshots and an original Astro daily-slate page that explains why each probability changed.

That single vertical slice forces the right contracts across data rights, feature availability, model evaluation, artifact provenance, serving, design, and content. Once it is honest and reliable, totals, props, live models, research tools, and monetization can grow from it without rebuilding the foundation.
