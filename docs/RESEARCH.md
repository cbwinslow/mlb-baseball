# Phase 2 Research — Models and Techniques

A running, source-cited knowledge base of sabermetric and ML techniques evaluated for Phase 2 (see ADR-032). Organized by technique, not chronologically — update an existing section rather than appending a new dated entry. Each entry: what it is, the concrete formula/method where one exists, source(s), and a note on how (or whether) it applies to `gold.game_feature`/the win-probability model.

## Head-to-head win probability (log5)

**Formula:** `P(A beats B) = WPa(1-WPb) / [WPa(1-WPb) + WPb(1-WPa)]`, where `WPa`/`WPb` are the two teams' winning percentages. (An earlier version of this doc, and the code it justified, cited `WPa² / (WPa² + WPb²)` — that ratio-of-squares form was a misreading of the source; it fails the article's own required defining property below and was never actually validated. Corrected 2026-08-04 after an independent audit caught the mismatch — see `docs/PROJECT_REVIEW.md`.)

Independently derived twice: Bill James proposed it axiomatically in 1981 (the "log5" method); a SABR paper by Richards derives the same formula constructively (via a neutral-proxy-team thought experiment) and validates it directly against 204,858 decisive MLB games, 1871-2013 — **97.90% efficiency ratio**, Brier skill score 0.0556 above naive baseline, consistent (90-94%+ efficiency) across eras. A refined version adjusting for league composition (`P'`) reaches 98.32%. The article states one required defining property of the function: `P(x, .500) == x` — a team with winning percentage `x` must get win probability exactly `x` against a league-average opponent. The odds-ratio form above satisfies this identically; the squared form does not (e.g. `.6²/(.6²+.5²) = .5902`, not `.600`).

**Relevance:** this is the cheapest possible baseline — two numbers in, one probability out, no training step. Directly matches `gold.game_feature`'s `home_win_pct`/`away_win_pct` columns; log5 on those two values alone is worth standing up as the very first `gold.prediction` row, before Elo or anything ML-based.

Source: [SABR — Probabilities of Victory in Head-to-Head Team Matchups](https://sabr.org/journal/article/probabilities-of-victory-in-head-to-head-team-matchups/)

## Elo ratings

FiveThirtyEight's MLB Elo model (the standard public reference):
- Home-field advantage: **+24 Elo points** before computing win probability.
- Pre-game adjustments: travel distance, days of rest, and **starting pitcher** — a separately-tracked, continuously-updating per-pitcher rating (refreshed after every start from that start's game score) blended into the team's game-day rating.
- Post-game update: standard Elo margin-of-victory multiplier (bigger wins move ratings more, with a dampening term against runaway autocorrelation) — general MOV-Elo shape: `multiplier = (|score_diff| + 3)^0.8 / (7.5 + 0.006 × elo_diff)` (this exact constant set is the general 538 cross-sport formula; MLB-specific constants weren't found published and should be tuned against our own backtest).
- Ratings revert toward the mean between seasons rather than carrying forward untouched.
- K-factor: no MLB-specific published value found. Start low (≈4) given a 162-game season needs much slower-moving ratings than the NBA (82 games) or NFL (16 games) versions 538 publishes K-factors for; calibrate against our own backtest log-loss.

**Relevance:** `gold.game_feature.home_elo`/`away_elo`, computed incrementally game-by-game from `core.game` in date order. Second baseline to stand up, after log5.

**Implemented** (`mlb_baseball/model/elo.py`): starting-pitcher adjustment not built (would need per-pitcher rating tracking, a real follow-up piece, not a gap in this pass); home advantage (+24) and the MOV multiplier used exactly as published above. K-factor (4.0) and season-reversion weight (0.25, blended toward 1500 the first time a team is seen in a new season) are **chosen, not sourced** — no MLB-specific values are published anywhere found — flagged explicitly in the module docstring as open, revisit-with-backtesting-evidence parameters, not facts. Computed as a sequential Python walk over `gold.game_feature` ordered by date, not SQL window functions — a rating genuinely depends on every prior game's *outcome* and updates two teams at once, which doesn't fit the same-row-independent shape window functions need (unlike log5/Pythagenpat, which are pure rolling aggregates). Verified against production: 793 real predictions generated, hand-checked against manually computed Elo math before formal tests were written.

Sources: [How Our MLB Predictions Work](https://fivethirtyeight.com/methodology/how-our-mlb-predictions-work/) (page has moved since 538's site restructuring — treat as historical reference, methodology confirmed via secondary citation), [mlb-elo dataset README](https://github.com/fivethirtyeight/data/blob/master/mlb-elo/README.md)

## Pythagorean expectation — use Pythagenpat, not the textbook version

- Classic (Bill James): `win% = RS² / (RS² + RA²)`.
- **Pythagenpat** (David Smyth) uses a scoring-environment-adaptive exponent instead of a fixed 2: `exp = ((RS + RA) / G) ^ 0.287`. Adapts automatically across run environments (dead-ball era vs. today) — generally regarded as more accurate than both the fixed-exponent version and Davenport's earlier Pythagenport variant.

**Relevance:** `gold.game_feature.home_pyth_wpct`/`away_pyth_wpct` should use the Pythagenpat exponent, computed from the same season-to-date `home_run_diff`/`away_run_diff` columns already in the table — not the plain formula originally sketched in the migration comment.

Sources: [Wikipedia — Pythagorean expectation](https://en.wikipedia.org/wiki/Pythagorean_expectation), [arXiv — Relieving and Readjusting Pythagoras](https://arxiv.org/pdf/1406.3402)

## Run expectancy / Markov chain models

Models each half-inning as a Markov chain over 24 base-out states (8 base configurations × 3 out counts) plus terminal states, using observed state-transition frequencies (from real play-by-play data) to compute expected runs per state, and — extended with score/inning — win probability. This is the theoretical foundation behind most modern win-probability and RE24-style metrics.

**Relevance:** Not needed for `gold.game_feature` v1 (log5/Elo/Pythagenpat don't require it), but a natural follow-up: a team's actual base-out transition efficiency this season is a "true talent" signal independent of clustering luck, and could become its own feature later. **Correction (Plan 04D, ADR-076):** this section previously claimed `core.play` has the data to build this directly — checked directly against the live schema and that's wrong: `core.play` has `outs` but no runner-on-base columns at all (no equivalent of Retrosheet's `base1/2/3_run_id`/`bat_dest_id`/`run1/2/3_dest_id`), which a transition matrix needs. `raw.retrosheet_event` has exactly what's needed and is what `mlb_baseball/model/markov.py` (ADR-076) actually builds off. [calestini/markov-baseball](https://github.com/calestini/markov-baseball) is a clean, directly-adaptable reference implementation of the state space and transition-matrix construction.

**Extension (Plan 04D, ADR-077):** the transition matrix above only gives expected value, not a sampled run count — a simulator needs the latter. `simulate_half_inning`/`simulate_half_innings` (ADR-077) Monte Carlo-sample from `build_outcome_distribution`'s joint `(post_state, runs_scored)` distribution (not the marginal transition matrix, which discards which runs total went with which transition) to draw one plausible half-inning outcome at a time — the standard technique for turning a fitted Markov chain into a stochastic simulator, e.g. the "Simulating a season" approach in Bukiet/Harold/Palacios below. Verified against real 2019 `mlb` data three independent ways (real historical mean, simulated mean, and the RE24 table's own bases-empty/0-outs value) landing within ~3.4% of each other — see ADR-077 for the full protocol, including why walk-off-truncated half-innings must be excluded from the real-data side of this comparison. Not yet applicable to `gold.game_feature` or a win-probability model directly: this package simulates a single, isolated half-inning starting from bases-empty/0-outs, not a full 9-inning two-team game with score/inning state, which win probability needs; that composition is explicitly open future work (ADR-077's "Revisit if").

**Extension (Plan 04D, ADR-078):** `simulate_game` composes repeated `simulate_half_inning` calls into a full two-team game, applying real game-ending rules (walk-offs, and a skipped bottom half when the home team is already ahead at or past the configured `regulation_innings` parameter — 9 by default, matching a real regulation game, but not hardcoded) — the first `gold.game_feature`-shaped output this line of work produces (a full game's final score), though not yet wired into that table. Verified as an in-sample diagnostic against real 2019 `mlb` data (2,429 games, same season used for both estimation and comparison, not a held-out fold): total-runs and innings-played summary statistics (mean, median, p90) both close (within ~2%), but home win rate (52.9% real vs. 49.9% simulated) is an honestly-reported gap — this model has no home/away split, so it cannot reproduce real baseball's home-field advantage; see ADR-078 for the full protocol, and `scripts/verify_markov_calibration.py` to reproduce these figures from a clean clone. Also out of scope here: the 2020+ extra-innings placed-runner ("Manfred runner") rule, since this package's calibration season (2019) predates it — a future calibration against 2020+ seasons would need to model it or accept a biased extra-innings comparison.

**Extension (Plan 04D, ADR-079):** every check above (ADR-076/077/078) was in-sample -- same season for estimation and comparison. `scripts/verify_markov_calibration.py --estimate-seasons` closes that gap: estimated from 2015-2018, compared against real 2019, every aggregate gap widened honestly (e.g. total-runs mean gap grew from ADR-078's in-sample ~1.7% to a held-out ~5.7%). Root cause verified directly, not assumed: real average runs/game rose from 8.50 (2015) to 9.66 (2019) -- genuine run-environment drift across just a few real seasons (the "juiced ball" 2019 season), which a model estimated only from the lower-scoring prior seasons cannot know about. This is the honest cost of a genuinely out-of-sample check that an in-sample one structurally cannot reveal -- see ADR-079 for the full protocol and exact figures.

**Extension (Plan 04D, ADR-080):** ADR-078 flagged the simulator's home win rate (49.9% simulated vs. 52.9% real) as a gap caused by having no home/away split. Verified that premise directly before building anything -- 2019 alone showed no real home/away scoring difference (an anomaly, checked and nearly discarded the whole idea), but 2015-2018 all showed a real one. `estimate_outcome_distribution`'s new `bat_home` filter and `simulate_game`'s new `home_distribution` parameter let each side draw from its own real distribution instead of one combined one; simulated home win rate moved to 52.6%, closing most of the gap, stable across seeds. An open, honestly-reported question: the two sides' simulated run *means* came out nearly identical despite the win-rate gap closing, meaning the improvement isn't a simple mean-shift -- see ADR-080 for the full protocol.

Sources: [calestini/markov-baseball](https://github.com/calestini/markov-baseball), [A Markov Chain Approach to Baseball (Bukiet, Harold, Palacios)](https://pubsonline.informs.org/doi/pdf/10.1287/opre.45.1.14), ADR-078 (`docs/DECISIONS.md`) for the game-ending-rules/`vruns`/`hruns`/placed-runner-limitation evidence specifically, ADR-079 for the held-out-season evidence, ADR-080 for the home/away split evidence

## Leverage Index / Win Probability Added — not pre-game, noted for later

Leverage Index (Tom Tango) measures how much a single play can swing win probability (1.0 = average; 2.0+ = high-leverage late/close situations; near-zero = blowouts). Foundational to WPA and reliever-usage evaluation.

**Relevance:** in-game, not pre-game — doesn't feed `gold.game_feature`. Flagged for later if the project extends into in-game win-probability tracking or bullpen-usage features, not part of the win/loss prediction target.

Source: [FanGraphs Sabermetrics Library — LI](https://library.fangraphs.com/misc/li/)

## ML approaches — gradient boosting, and where deep learning fits

- Reported accuracy on **honest, leakage-free** approaches clusters in the **55-58% range** (e.g. a gradient-boosted model on 2018-19 data: 56.8% — [egitit/Predicting_MLB_outcomes](https://github.com/egitit/Predicting_MLB_outcomes)). MLB is famously hard to predict game-to-game; this range is a legitimate good result, not a shortfall.
- **Reality-check calibration**: several public repos claim 67-93%+ accuracy. These are almost certainly leakage artifacts (same-game box-score stats used as inputs), not something to benchmark against. **If our own model reports 70%+ accuracy, that's a signal to go hunting for leakage, not a result to celebrate.**
- Hierarchical Bayesian pitcher-batter matchup models (very recent, Nov 2025) combine pitcher/batter stats, handedness, recency, and base-stealing tendency into plate-appearance-level predictions, then roll up to game-level win probability via a game-theoretic framework for in-game decisions. Found more accurate matchup modeling worth up to **~1 additional win per 162-game season** in simulation. More sophisticated than v1 needs, but the plate-appearance-level matchup approach is a natural direction once `gold.game_feature`'s game-level model is working.
- Matrix factorization approaches exist specifically for the batter-vs-pitcher cold-start problem (limited head-to-head history) — relevant only if/when the project adds granular matchup features, not for v1.

Sources: [arXiv 2511.17733 — The Impacts of Increasingly Complex Matchup Models on Baseball Win Probability](https://arxiv.org/abs/2511.17733), [arXiv 2511.02815 — Assessing win strength in MLB win prediction models](https://arxiv.org/abs/2511.02815) (log-loss/Brier/calibration evaluation methodology directly matches our own — full read still pending, PDF text extraction failed in this environment), [arXiv 2402.01914 — Predicting Batting Averages in Specific Matchups Using Generalized Linked Matrix Factorization](https://arxiv.org/pdf/2402.01914), [arXiv 2410.21484 — A Systematic Review of ML in Sports Betting](https://arxiv.org/pdf/2410.21484), [Forrest31/Baseball-Betting-Model](https://github.com/Forrest31/Baseball-Betting-Model), [arjun-prabhakar/mlb_outcomes](https://github.com/arjun-prabhakar/mlb_outcomes)

## Leakage / validation discipline (confirms, doesn't change, ADR-032)

Walk-forward / rolling validation (predict period N using only data through N-1) is the consensus approach across every source checked — matches `gold.game_feature`'s point-in-time design and ADR-032's time-based split already. Common failure mode explicitly called out: using "closing line"/same-game stats inflates backtested accuracy without holding up in real prediction — the same class of trap as `core.game.winning_pitcher_id`, already designed around.

Source: [How to Build Sports Prediction Models in 2026](https://www.parlaysavant.com/insights/sports-prediction-models-2026)

## Model stacking / ensembling — "outputs as inputs"

A real, standard technique (not something to invent from scratch): train diverse base models (classical formulas, tree-based ML, etc.), then either (a) feed their outputs as *features* into a final model (what `gold.game_feature` already does by construction — Elo/Pythagenpat are themselves engineered features going into the gradient-boosted model), or (b) train a formal meta-learner on top of multiple base models' predictions (stacking proper). (a) is already the v1 plan; (b) is a legitimate later refinement once log5/Elo/Pythagenpat/gradient-boosting baselines all exist independently to stack.

**(b) is now actually built** (ADR-058, `mlb_baseball/model/stack.py`, `stack-v1`) — a logistic regression over `log5-v1`/`elo-v1`/`gbm-v1`'s own latest `gold.prediction` probabilities (plus `polymarket-v1`/`kalshi-v1`'s, as optional inputs with a missing-value indicator, currently non-missing for only a recent ~21-game window). Logistic regression, not XGBoost, chosen specifically *because* real production data turned out much smaller than assumed going in — only 47 real decided games currently have a prediction from all three base models (verified directly, not assumed), which is squarely the small-n regime where a linear combiner over a handful of already-strong inputs is the textbook-defensible choice and a boosted-tree meta-learner risks memorizing the training split outright. **Result on real, held-out production data: the stack did not beat `gbm-v1` (0.7174 vs 0.6932 log-loss, n=10 held-out) — an honest negative result, not force-fit into a win.** `train()`'s "only save if it beats every individual baseline" guard correctly declined to save it; no `stack-v1` predictions are served. See ADR-058 for the full numbers and reasoning, including why this is a plausible outcome (`gbm-v1` already ingests most of the same underlying signal directly) rather than just a training bug, and what would make this worth revisiting (more decided `gbm-v1` games, wider market coverage, a live market-matching extension).

## Feature engineering backlog (post-gbm-v1 finding)

gbm-v1 (ADR-033) barely beat Elo despite having 10 features to Elo's 2 — the current feature set doesn't carry much more signal than a bare Elo rating. Research below, cross-checked against what we actually already have ingested (`docs/DATA_SOURCES.md`) before proposing anything new to fetch — the point is using data we already have, not adding sources.

**Starting pitcher quality** — **correction, 2026-08-13**: this was previously cited as unanimous "research consensus" across three sources; an independent re-read of the actual papers found that's an overstatement, and one source was mischaracterized. Full citations and what each actually found:

- Donaker, G. (2005). *Applying Machine Learning to MLB Prediction & Analysis.* CS229 Final Project, Stanford University. [PDF](https://cs229.stanford.edu/proj2005/Donaker-MLBPredictionAndAnalysis.pdf) — does support the claim: "the two most significant weights were the sum of starter at-bats in the previous season and the starting pitcher's ERA in the previous season."
- Chen, L. & He, A. (2010). *Beating the MLB Moneyline.* CS229 Final Project, Stanford University. [PDF](https://cs229.stanford.edu/proj2010/ChenHe-BeatingTheMLBMoneyline.pdf) — also supports it: "matchups between starting pitchers [are] widely acknowledged to be the strongest influence on bookmaker odds."
- Cui, A. Y. (2020). *Forecasting Outcomes of Major League Baseball Games Using Machine Learning.* EAS 499 Senior Capstone Thesis, University of Pennsylvania (Wharton/SEAS). [PDF](https://fisher.wharton.upenn.edu/wp-content/uploads/2020/09/Thesis_Andrew-Cui.pdf) — **does not** support the claim as previously cited here. Across all three of its models, OBP is the most important feature and ISO typically second; the thesis's own words: "the pitching covariates show similar but generally weak feature importance, which is sensible since they are aggregate numbers from the prior season." That's the same lagged-aggregate leakage trap this section already diagnoses below — the thesis is evidence *for* building the rolling within-season pitcher stat this project built, not evidence that pitcher quality is a top predictor in the abstract.
- Li, S.-F., Huang, M.-L., & Li, Y.-Z. (2022). "Exploring and Selecting Features to Predict the Next Outcomes of MLB Games." *Entropy*, 24(2), 288. https://doi.org/10.3390/e24020288 — the paper's headline finding is that winning percentage, not a pitching stat, is the only feature its recursive feature elimination selects for every one of 30 team-specific datasets; ERA/WHIP-type features appear in some team subsets but "varied by team." More a validation of this project's Elo/log5/Pythagenpat baseline layer than a pointer toward pitcher quality specifically.

Net: 2 of 4 sources checked support "starting pitcher quality is a top predictor," and the two that don't (Cui 2020, Li et al. 2022) both point at *why* — a lagged season aggregate is a weak signal, exactly the leakage trap the next sentence below already diagnoses and the reason this project built a rolling within-season signal instead of using `raw.bref_pitching` directly. FIP/xFIP/SIERA (defense-independent pitching — strikeouts, walks, home runs are what a pitcher actually controls, per DIPS theory) are more predictive of *future* performance than ERA. **What we have**: `raw.bref_pitching` (full traditional stat line) and `raw.statcast_pitcher_expected` (Statcast's own `xera`, 2015+) both exist but are **season aggregates** — same leakage trap as `core.player_war` (ADR-032): usable only as a prior-season lag, not mid-season. For a genuine point-in-time, no-leakage, *within-season* signal, `core.play` has per-event data (`pitcher_id`, `event_code` — confirmed directly against real data: `3`=K, `14`/`15`=BB/IBB, `23`=HR, `2`/`16`/`18`-`22`=other PA-ending outcomes) back to 1901, enough to compute a rolling strikeout-rate/walk-rate/home-run-rate for a starter's own prior starts this season, the same window-function shape already used for team win%. Getting a true innings-pitched-denominated FIP requires reconstructing IP from out-sequences, real added complexity; a per-batter-faced K%/BB%/HR% composite is a legitimate, simpler proxy in the same spirit, at the cost of not being on a familiar ERA-like scale.

**Bullpen quality and fatigue** — research (InsidethePen usage-tracking analysis) is direct: relievers now handle 40%+ of innings, and WHIP/K%/BB% predict bullpen betting value better than ERA; fatigue (pitches thrown in the last 5 days, back-to-back appearances) measurably reduces effectiveness independent of quality. Buildable from `core.play` the same way as starter quality (identify a team's non-starting pitchers' appearances, roll up rate stats + a recency/workload count) — a real, separate, second piece of engineering from starter quality, not a byproduct of it.

**Team-level offensive true talent (xwOBA/barrel%/hard-hit%)** — Statcast's own expected-stats framework strips out park/luck/defense better than plain batting stats; barrel rate specifically is cited as one of the most stable, predictive batted-ball metrics. **What we have**: `raw.statcast_batter_expected` (xwOBA) and `raw.statcast_batter_exitvelo` (barrel%, hard-hit%, avg exit velo), both season-aggregate (2015+, Statcast era only) — same prior-season-lag treatment as WAR, not usable mid-season without leakage. **Superseded, not built (checked before ADR-041)**: both tables are player-only with no team column at all, and the only fallback (`raw.bref_batting.tm`) holds ambiguous city names ("New York", "Chicago" — doesn't disambiguate Mets/Yankees or Cubs/White Sox), confirmed directly. Would also duplicate team wOBA's already-built, strictly-better (within-season, no lag) coverage of the same "offensive true talent" ground — not worth a second, weaker version of the same signal.

**Team baserunning speed (Statcast Sprint Speed)** — not covered by anything else already built; WAR/OAA/bullpen/starter/wOBA all touch hitting, pitching, or fielding, none touch raw speed. **What we have**: `raw.statcast_sprint_speed` (2015+), season-aggregate like WAR/OAA, and — checked directly before proposing it — has its own `team_id` column holding MLB's numeric team id, matching `core.team.mlb_team_id` verbatim, no crosswalk needed at all (the easiest team-identity case of any feature built so far).

**Park factors** — standard methodology (FanGraphs, Baseball Prospectus): multi-year rolling ratio of a park's runs-per-game to the league average, scaled around 100. **What we have**: enough real historical `core.game` data (home/away scores by venue, back to 1871) to compute this ourselves directly — no external source needed, purely a derived feature from data already in `core`.

**Rest days** — `gold.game_feature.home_rest`/`away_rest` are already reserved columns in the schema (ADR-032), never populated. Straightforward: days since each team's prior game, computable directly from `core.game`'s date history. No research needed, just not built yet.

**Catcher framing (Statcast, `raw.statcast_framing.rv_tot`)** — a real, distinct pitching-staff-adjacent value signal not captured by anything built so far (starter/bullpen FIP measure results a pitcher controls directly; framing measures a catcher's effect on called-strike rate, a separate mechanism). Checked feasibility directly, not assumed: `raw.statcast_framing` is player-only (no team column, same shape as the already-rejected xwOBA/exitvelo tables), but unlike those, team identity is resolvable here via `core.player.mlbam_id` → `core.player_war` (`player_id`, `season`, `team_code`, reusing war.py's existing `_BREF_TO_RETRO` crosswalk) — confirmed against real 2024 data: Dingler→DET, Smith→LAD, Langeliers→OAK, Jeffers→MIN, all correct. Real coverage gap found and understood, not glossed over: only 367/708 (52%) rows resolve to a team — the unresolved half are consistently rookies/prospects with too little playing time for `core.player_war`'s min-PA threshold to include them (Basallo, Rushing, Jensen, Baldwin — all real 2024 rookie catchers, confirmed by name, not a join bug). Same lagged-season treatment as WAR/OAA required (season aggregate). Ready to build — ADR + migration + module + tests, same shape as oaa.py — not yet started.

### Recommended build order

1. ✅ **Rest days** — built (`mlb_baseball/model/features.py`).
2. ✅ **Starting pitcher true FIP + K%/BB%/HR%** — built (`mlb_baseball/model/starter.py`, ADR-034). Both approaches, not a forced choice — true FIP on the reserved `home_starter_era` column plus the raw rates in new `home_starter_k_pct`/`bb_pct`/`hr_pct` columns (migration 0016). Verified against real deGrom 2018 data, then at full scale (13,613 pitcher-seasons) against `raw.bref_pitching`, wired as a permanent `mlb doctor` reconciliation. **Known gap**: `raw.retrosheet_event` covers 1910-2025 only — 2026 (the live season) needs the equivalent from `raw.mlb_playbyplay`, a separate parsing task, not yet built.
3. ✅ **Park factors** — built (`mlb_baseball/model/park.py`, ADR-035). Trailing 3-year window, purely derived from `core.game`'s own historical scores, zero external dependency. Verified against real 2024 data: Coors Field correctly ranks highest (135.4), matching wide sabermetric consensus.
4. ✅ **Team offensive true talent → team wOBA** — built (`mlb_baseball/model/offense.py`, ADR-036), better than originally planned: a genuine within-season rolling number from `raw.retrosheet_event`, not a season-lagged Statcast aggregate. FanGraphs' own published formula, recreated (not scraped — confirmed they don't support scraping/API access at all). Verified: real 2023 league-average wOBA computed at .317, matching the known real value; real 2024 team values all land in .295-.333.
5. ✅ **wRC+** — built (`mlb_baseball/model/offense.py::compute_wrc_plus`, ADR-037). Park- and league-adjusted team wOBA. Sanity-checked algebraically (a league-average hitter in a neutral park must reduce to exactly 100 by definition — a real regression test, not just a manual check) and verified against real 2024 data: every value in 86.9-103.6, clustered around 100.
6. ✅ **Prior-season team WAR** — built (`mlb_baseball/model/war.py`, ADR-038). Closes the last ADR-032-reserved `gold.game_feature` column. Surfaced a real, separate team-identity crosswalk gap along the way: `core.player_war.team_code` uses bref's own abbreviations (`NYY`, `CHC`), genuinely different from Retrosheet's (`NYA`, `CHN`) that `core.team` uses — confirmed by direct comparison, not assumed. Verified: 2023's Braves and Rangers (both real, well-known strong teams) correctly rank highest entering 2024.
7. ✅ **Bullpen quality/fatigue** — built (`mlb_baseball/model/bullpen.py`, ADR-039). Team-level, not pitcher-level, by deliberate design — which reliever a manager uses today is an in-game decision, so per-pitcher composition would leak. Rolling season-to-date relief FIP/K%/BB% plus a trailing-3-day relief-outs fatigue signal, both no-leakage by the same construction as starter.py. Caught a real design bug pre-verification: without a full team-game backbone, both signals would silently go NULL for any specific game where a team happened to use zero relievers, regardless of real prior history — fixed before it ever ran against real data.
8. ✅ **Defensive value via Statcast OAA** — built (`mlb_baseball/model/oaa.py`, ADR-040). `raw.statcast_oaa.fielding_runs_prevented` (2016-2026, already ingested) is the real, free, modern substitute for FanGraphs' UZR/DRS, which depend on proprietary data with **no free path to replicate — a permanent wall under the $0-budget rule, confirmed directly via FanGraphs' own site returning HTTP 403 for every scrape attempt.** Same prior-season-lag treatment as WAR (it's a season aggregate). Confirmed two real data-shape quirks against production before building: one row per player per season *per position* (must sum, not dedupe), and Savant's own team-name spelling diverging from `core.team.nickname` in exactly three cases (D-backs/Rays/Guardians), fixed with a small remap.
9. ✅ **Prior-season team baserunning speed** — built (`mlb_baseball/model/speed.py`, ADR-041). `competitive_runs`-weighted average of `raw.statcast_sprint_speed.sprint_speed`, lagged one season. Not redundant with anything else built so far — no other feature touches raw speed. Team identity is the easiest case of any feature yet: `team_id` is MLB's own numeric id, matching `core.team.mlb_team_id` verbatim, no crosswalk needed. Also ruled out team-level Statcast xwOBA/barrel%/hard-hit% before building this — checked the schemas directly and found no team column at all on either source table, plus it would have duplicated team wOBA's already-better within-season coverage.
10. ✅ **Catcher framing** — built (`mlb_baseball/model/framing.py`, ADR-045). A real, distinct signal from everything else built — measures a catcher's effect on called-strike rate, not something FIP already prices in. Team identity resolved by reusing war.py's own `_BREF_TO_RETRO` crosswalk through `core.player_war`, not a new one. Verified against real 2024 data (Dingler→DET, Smith→LAD, etc., all correct); found and understood a real ~48% coverage gap traced to `core.player_war`'s own minimum-playing-time threshold excluding rookies/prospects, not a join bug.
11. ✅ **2026 (current-season) starter quality + wOBA/wRC+ + bullpen from raw.mlb_playbyplay** — starter and offense halves built (`mlb_baseball/model/starter.py::compute_live`, `mlb_baseball/model/offense.py::compute_live`/`compute_wrc_plus_live`, ADR-046). Verified against a real, identifiable pitcher (Shota Imanaga, 27 real 2026 starts) before writing the starter query: per-play outs matched exactly across several real innings by hand, and the resulting aggregate landed in normal ranges for a real MLB starter. All three gated on the relevant column `IS NULL` so they only fill the gap the Retrosheet-based versions leave — the two sources don't overlap in practice. **Bullpen closed** (`mlb_baseball/model/bullpen.py::compute_live`/`compute_upcoming`, ADR-051) — completed 2026 games via `compute_live` (same shape as `compute()`'s own team_game backbone/rolling-window/day-grain-fatigue treatment, just sourced from `raw.mlb_playbyplay`), and still-upcoming games via `compute_upcoming`, which — unlike starter's `compute_probable` — needs no `raw.mlb_probable`/`core.player` dependency at all: bullpen identity is team-level, resolved straight from `gold.game_feature.home_team_id`/`away_team_id` (already set by `features.py` for every upcoming row).

## Run totals (over/under) — regression, not classification against a line

**The question, checked directly before building anything (ADR-056):** predict a specific over/under line (classification: will the total exceed X.5?) or the raw expected combined runs (regression)? `raw.polymarket_market` does have real total-runs market data — 12,766 `sportsmarkettype = 'totals'` rows, a real `line` column (e.g. `"Tampa Bay Rays vs. New York Yankees: O/U 7.5"`), 12,629 of them for already-played games (in principle resolvable). But checking `mlb_baseball/conform.py`'s `_polymarket_market_rows` (the function that actually lands rows in `core.market`) shows it only ever resolves an outcome whose text matches a *team name* — the moneyline shape. A totals market's outcomes are literally `"Over"`/`"Under"` (confirmed directly: `SELECT outcome, count(*) FROM raw.polymarket_market m JOIN raw.polymarket_outcome o ON o.market_id = m.id WHERE m.sportsmarkettype = 'totals'` returns exactly `Over: 12766, Under: 12766`, zero team names), so every one of those rows fails the team-name match and is silently dropped before ever reaching `core.market`. `core.market` has **zero** usable total-runs data today. Building a second, genuinely different match/resolve path (an Over/Under outcome resolving against a specific numeric line, not a team) is real, new scope — a different join shape, a new "does this line's outcome match reality" resolution step — not a small extension of the existing moneyline path. **Decision: regression against the honest, directly-computable target is the safer, immediately-buildable v1**; matching a specific external line is real, separate follow-up work once `core.market`'s own totals-matching exists (tracked as a revisit, not built here).

**Label source, verified by hand before trusting it at scale**: `core.game.home_score + core.game.away_score`. Spot-checked two real 2026-08-03 games directly against MLB's own live-feed API (`statsapi.mlb.com/api/v1.1/game/{pk}/feed/live`) before trusting the column at scale — game_pk 824324 (Rockies 9, Rays 13, total 22) and game_pk 823520 (Yankees 7, Cardinals 13, total 20) both match `core.game` exactly. 216,729 decided regular-season games have both scores; range 0-49, mean 8.87, 99th percentile 22 — all plausible, no outliers suggesting a parsing bug.

**Feature selection, checked by correlation against real total-runs data, not copied from the win/loss model** — `corr()` computed directly in Postgres across all 216,729 decided games, `gold.game_feature` columns against `home_score + away_score`:

| column (summed home+away where applicable) | r | included? |
|---|---|---|
| `park_factor` | 0.118 | yes (REQUIRED) |
| `home_woba` + `away_woba` | 0.155 (0.137 / 0.114 individually) | yes |
| `home_wrc_plus` + `away_wrc_plus` | **-0.108** | yes, with caveat below |
| `home_starter_era` (FIP) + `away_starter_era` | 0.097 | yes |
| `home_bullpen_fip` + `away_bullpen_fip` | 0.097 | yes |
| `home_starter_k_pct` + `away_starter_k_pct` | -0.046 | yes |
| `home_starter_bb_pct`/`hr_pct`, bullpen `k_pct`/`bb_pct`/`fatigue` | 0.045-0.060 | yes |
| `home_run_diff`, `home_elo`+`away_elo`, win%/Pythagenpat | -0.017 to -0.010 | **no** |
| `home_oaa_prior`/`speed_prior`/`framing_prior`/`war_prior` | \|r\| < 0.011, plus 5-11% coverage | **no** |
| `temp_f`/`wind_speed_mph`/`wind_dir`/`sky`/`precip` | undefined — **0 of 216,729+ rows populated at all** | **no** |

The win/loss-oriented columns (win%, run-diff, Pythagenpat, Elo) all land within noise of zero — makes sense on reflection, not a red flag: a team can be "strong" via elite pitching (suppresses total runs) or elite hitting (inflates it), so the same win/loss rating doesn't carry a consistent sign for a run-total target the way it does for win/loss itself. Weather columns are a real, confirmed gap (reserved in the schema since ADR-032, never populated by anything built so far) — excluded for having literally nothing to offer, not a judgment call.

**wRC+'s negative correlation is a real, understood confound, not a bug** — worth flagging since it's counterintuitive (wRC+ is a hitting-*quality* stat; naively you'd expect a positive sign). `offense.py::compute_wrc_plus` divides team wOBA by `park_factor/100` specifically to strip out the park's scoring environment (that's the entire point of a park-adjusted stat). But a high-`park_factor` game also has a genuinely higher raw total (that's what park_factor measures), so wRC+'s own park-adjustment mechanically produces a negative naive correlation with the very quantity park_factor predicts positively — two features capturing overlapping ground through opposite mechanisms. Kept in the feature set anyway: XGBoost combines features rather than reading each in isolation, and wRC+ still carries real, distinct signal (team offensive quality independent of park) once park_factor is also available to the same tree.

**Naive baseline — "the park's trailing average total"** (this task's own framing, verified as sensible before building rather than assumed): real 2021-2025 league-wide average totals cluster tightly at 8.6-9.2 runs/game; Coors Field's own trailing average sits at 10.7-11.8 across the same seasons — a real, meaningfully different number a flat league-wide constant would miss entirely. Computed by reusing `park_factor` (already a trailing-window, no-leakage, ADR-035-verified signal) rather than building a second parallel trailing-runs-by-venue query: `baseline_total = league_trailing_avg_total(season) * park_factor / 100`, where the league-wide trailing average uses the identical `TRAILING_SEASONS`-year, games-weighted, strictly-prior-seasons window `park.py` already established for `park_factor` itself.

**Implemented** (`mlb_baseball/model/total.py`, ADR-056): `gold.total_prediction` (migration 0029) is a new table, not a reuse of `gold.prediction`'s win/loss-probability shape — stores `predicted_total`/`baseline_total`/`actual_total` (a regression point estimate plus the baseline it's judged against), history-preserving via the same `(mlb_game_pk, model_version, generated_at)` composite-PK precedent as `gold.prediction`. `train()` only saves a new model if it beats the park-trailing baseline on RMSE over the 2024-2025 validation split (same TRAIN_SEASON_CUTOFF=2023 split ADR-032 already established, reused for consistency) — never silently overwrites a working model with a worse one.

## Comprehensive Sabermetric and Advanced Feature Derivations (Packages 1–8)

All 8 feature families below implement the strict Formula and Cross-Reference Verification Doctrine (see `AGENTS.md`), ensuring exact backward-point-in-time correctness (`ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING`), deterministic hand-calculated test fixtures, and domain bound health assertions.

### 1. Plate Discipline: CSW%, Whiff%, and First-Pitch Strike% (`PIT-07`, ADR-089)
- **Citations**: Alex Fast & Nick Pollack (Pitcher List, 2019), "CSW: A New Metric for Pitch Quality and Pitcher Success"; FanGraphs Plate Discipline Library.
- **Formulas**:
  - $\text{CSW\%} = \frac{\text{Called Strikes} + \text{Swinging Strikes}}{\text{Total Pitches}}$
  - $\text{Whiff\%} = \frac{\text{Swinging Strikes}}{\text{Total Swings}}$
  - $\text{F-Strike\%} = \frac{\text{First-Pitch Strikes}}{\text{Total Plate Appearances}}$
- **Data Source & Point-in-Time Availability**: Computed from `raw.retrosheet_event` pitch sequences (`pitches` and `event_cd`). Entering-game rolling aggregation strictly prior to the scheduled game.
- **Validation**: Hand-calculated integration test in `tests/integration/test_model_plate_discipline.py`. Checked against MLB Statcast league benchmarks ($\approx 28\text{--}30\%$ CSW%, $\approx 22\text{--}26\%$ Whiff%, $\approx 59\text{--}62\%$ F-Strike%).

### 2. Batted-Ball Profiles: GB%, FB%, LD%, and HR/FB (`BAT-01`, ADR-090)
- **Citations**: Voros McCracken (2001), "Defense Independent Pitching Statistics"; Tom Tango, Mitchel Lichtman, Andrew Dolphin (2007), *The Book: Playing the Percentages in Baseball*; FanGraphs Batted Ball Metrics.
- **Formulas**:
  - $\text{BIP} = \text{GB} + \text{FB} + \text{LD} + \text{PU}$
  - $\text{GB\%} = \text{GB} / \text{BIP}$, $\text{FB\%} = \text{FB} / \text{BIP}$, $\text{LD\%} = \text{LD} / \text{BIP}$
  - $\text{HR/FB} = \text{HR} / \text{FB}$
- **Data Source**: Chadwick Retrosheet trajectory annotations (`G`, `F`, `L`, `P`) in `raw.retrosheet_event`.
- **Validation**: Hand-calculated deterministic fixtures in `tests/integration/test_model_batted_ball.py`. Bounded by mathematical sum invariant $\text{GB\%} + \text{FB\%} + \text{LD\%} + \text{PU\%} = 1.00$.

### 3. Base-Out Run Expectancy Matrix (RE24) and Leverage Index (`LEV-01`, ADR-091)
- **Citations**: Tom Tango (2006), "Run Expectancy Matrix (RE24)"; Dan Fox (Baseball Prospectus, 2006), "Introducing Leverage Index".
- **Formulas**:
  - $\Delta RE = RE(\text{State}_{\text{post}}) - RE(\text{State}_{\text{pre}}) + \text{Runs Scored}$
  - $\text{LI} = \frac{\Delta WP}{\overline{\Delta WP}}$
- **Data Source**: 24 transient base/out states computed from `raw.retrosheet_event` (`outs_ct`, `base1/2/3_run_id`, runner destinations).
- **Validation**: Hand-calculated transition expectations in `tests/integration/test_model_leverage.py`. Evaluated across historical Retrosheet play-by-play.

### 4. Defense-Independent Pitcher Estimators: xFIP, SIERA, and Platoon Splits (`PIT-06` / `PLN-03`, ADR-092)
- **Citations**: David Smyth (2005), "Expected FIP (xFIP)"; Matt Swartz (Baseball Prospectus, 2010), "Skill-Interactive ERA (SIERA)"; Tangotiger Platoon Modeling.
- **Formulas**:
  - $\text{xFIP} = \frac{13 \cdot (\text{FB} \cdot \text{lgHR/FB}) + 3 \cdot \text{BB} - 2 \cdot \text{K}}{\text{IP}} + cFIP$
  - $\text{SIERA} = 6.145 - 16.986 \cdot \frac{K}{PA} + 11.434 \cdot \frac{BB}{PA} - 1.858 \cdot \frac{GB - FB - PU}{PA} + 7.653 \cdot \left(\frac{K}{PA}\right)^2 \dots$
  - Platoon: rolling wOBA and K% partitioned by batter handedness (`bat_hand_cd` `'L'` vs `'R'`).
- **Validation**: Hand-calculated arithmetic fixtures in `tests/integration/test_model_pitcher_estimators.py`. Tie-out asserted with strict non-negative and domain bounds.

### 5. Statcast Contact Quality and Expected Metrics: xwOBA, xBA, xSLG (`STA-03`, ADR-093)
- **Citations**: MLB Advanced Media Statcast Specifications; Glenn Healey (2017), "Modeling Ball Flight and Expected Outcomes in Major League Baseball".
- **Formulas**:
  - $\text{Hard-Hit\%} = \frac{\text{Batted Balls with EV} \ge 95\text{ mph}}{\text{Total Batted Balls}}$
  - $\text{Barrel\%} = \frac{\text{Batted Balls in optimal EV/LA launch window}}{\text{Total Batted Balls}}$
  - $\text{xwOBA}, \text{xBA}, \text{xSLG}$: Probability of hit/total bases conditional on launch angle, exit velocity, and sprint speed.
- **Validation**: Hand-calculated test fixture in `tests/integration/test_model_statcast_expected.py`.

### 6. Multi-Year Component Park Factors & Environmental Weather (`PARK-01` / `WEA-01`, ADR-094)
- **Citations**: Alan Nathan (Physics of Baseball, 2015); FanGraphs Multi-Year Regressed Park Factors.
- **Formulas**:
  - Multi-Year Weighted: $\text{PF}_{3\text{yr}} = 0.50 \cdot \text{PF}_1 + 0.30 \cdot \text{PF}_2 + 0.20 \cdot \text{PF}_3$
  - Air Density Index ($ADI$): $ADI = \frac{P}{R_{\text{specific}} \cdot T} \cdot 100$, adjusting ball carry by ambient temperature and barometric pressure.
  - Effective Wind Velocity: $v_{\text{eff}} = v_{\text{wind}} \cdot \cos(\theta_{\text{wind}} - \theta_{\text{CF}})$.
- **Validation**: Hand-calculated physics vectors in `tests/integration/test_model_park.py`.

### 7. Comprehensive Baserunning: XBT%, UBR, wGDP, and BsR Total (`RUN-01`, ADR-095)
- **Citations**: Tom Tango & Mitchel Lichtman (*The Book*); FanGraphs Ultimate Base Running (UBR) and Weighted Grounded Into Double Play (wGDP).
- **Formulas**:
  - $\text{XBT\%} = \frac{\text{Advances of } > 1 \text{ base on single or } > 2 \text{ bases on double}}{\text{Advancement Opportunities}}$
  - $\text{UBR} = \text{Linear weight run values of non-steal baserunning advances}$
  - $\text{wGDP} = (\text{Double Play Opportunities} \cdot \text{lgGDP\%} - \text{GDP}) \cdot \text{Run Value}_{\text{GDP}}$
  - $\text{BsR Total} = \text{wSB} + \text{UBR} + \text{wGDP}$
- **Validation**: Hand-calculated baserunning advance fixture in `tests/integration/test_model_bsr.py`.

### 8. Starting Catcher Framing & CSAE% (`CAT-02`, ADR-096)
- **Citations**: Mike Fast (Baseball Prospectus, 2011), "Spinning Yarn: Catcher Framing"; Statcast Shadow Zone Called Strike Above Expected (CSAE%).
- **Formulas**:
  - $\text{CSAE\%} = \frac{\text{Called Strikes}}{\text{Total Taken Pitches}} - \text{League Strike Rate on Takes} (0.33)$
  - $\text{Framing Runs} = (\text{Called Strikes} - \text{Expected Strikes}) \cdot 0.125\text{ runs}$
- **Validation**: Hand-calculated fixture in `tests/integration/test_model_framing.py`.

### 9. Pitcher Strike Zone Command & Statcast Attack Zones (`COM-01`, ADR-097)
- **Citations**: Tom Tango & MLB Advanced Media (2018), "Statcast Attack Zones: Heart, Shadow, Chase, Waste"; Jeff Long, Harry Pavlidis, Martin Alonso (Baseball Prospectus, 2017), "Pitch Tunneling and Velocity Differentials".
- **Formulas**:
  - $\text{Heart\%} = \frac{\text{Pitches in Zone 5 (or center box)}}{\text{Total Pitches}}$
  - $\text{Shadow\%} = \frac{\text{Pitches on Zone Edges (1-4, 6-9)}}{\text{Total Pitches}}$
  - $\text{Chase\%} = \frac{\text{Pitches in Outer Quadrants (11-14)}}{\text{Total Pitches}}$
  - $\text{Fastball Velocity} = \overline{v}_{\text{FF, SI, FC}}$
  - $\text{Velocity Delta} = \overline{v}_{\text{Fastball}} - \overline{v}_{\text{Offspeed}}$
- **Validation**: Hand-calculated deterministic test fixture in `tests/integration/test_model_command.py`.

### 10. Pitch Movement, Vertical Break & Tunneling Separation (`SHP-01`, ADR-098)
- **Citations**: Alan Nathan (Physics of Baseball, 2016), "Magnus Force and Trajectory Analysis"; Jeff Long & Harry Pavlidis (Baseball Prospectus, 2017), "Pitch Tunneling and Vertical Separation".
- **Formulas**:
  - $\text{Fastball IVB (in)} = \overline{pfx\_z}_{\text{FF, SI, FC}} \times 12.0$ (Induced vertical break/ride)
  - $\text{Curve Drop (in)} = \overline{pfx\_z}_{\text{CU, KC, SL, ST, SV}} \times 12.0$ (Downward Magnus break)
  - $\text{Vertical Movement Separation (in)} = \text{IVB}_{\text{Fastball}} - \text{IVB}_{\text{Breaking}}$
  - $\text{Batting Chase\%} = \frac{\text{Swings on Pitches in Zones 11-14}}{\text{Total Pitches Seen in Zones 11-14}}$
  - $\text{Batting Heart Swing\%} = \frac{\text{Swings on Pitches in Zone 5}}{\text{Total Pitches Seen in Zone 5}}$
- **Validation**: Hand-calculated deterministic test fixture in `tests/integration/test_model_pitch_movement.py`.

### 11. Symmetric Matchup Difference Vectors (`INT-02`, ADR-099)
- **Citations**: Bill James (1981), "The Pythagorean Expectation and Matchup Deltas"; Nate Silver (Baseball Prospectus, 2006), "PECOTA Matchup Discrepancy Modeling".
- **Formulas**:
  - $\Delta \text{Metric} = \text{Home Metric} - \text{Away Metric}$
  - Starter Diffs: `starter_siera_diff`, `starter_xfip_diff`, `starter_csw_diff`, `starter_whiff_diff`, `starter_xwoba_diff`, `starter_fastball_velo_diff`, `starter_vert_sep_diff`
  - Bullpen Diffs: `bullpen_siera_diff`, `bullpen_xfip_diff`, `bullpen_csw_diff`, `bullpen_whiff_diff`, `bullpen_xwoba_diff`
  - Lineup / Defense Diffs: `offense_hard_hit_diff`, `offense_barrel_diff`, `offense_xwoba_diff`, `bsr_total_diff`, `catcher_framing_diff`
- **Validation**: Strict algebraic parity assertion across all rows in `tests/integration/test_model_diff.py`.

## Further reading — found, not yet fully read

- Retrosheet's own research collection (uses Retrosheet data specifically, updated regularly — 6 new articles added in 2025): [retrosheet.org/Research/Research.htm](https://retrosheet.org/Research/Research.htm). Flagged as directly relevant: Calzada, "Deepball: Modeling Expectation and Uncertainty in Baseball With Recurrent Neural Networks"; Soper, "Understanding the Value of the Next Run" (run expectancy); Nutaro, "Prospect Theory and the Favorite Long-Shot Bias in Baseball" (behavioral-economics angle on market/betting bias — relevant once `core.market` timing gap, issue #1, is fixed).
- Charlie Pavitt's sabermetrics research bibliography (large index of papers using Retrosheet data): [retrosheet.org/Research/Pavitt/Research Summaries.pdf](https://www.retrosheet.org/Research/Pavitt/Research%20Summaries.pdf)
- arXiv 2511.02815 (full text) — PDF text extraction failed in this environment (no `pdftotext`/working PDF library installed); worth fetching properly before building the evaluation harness, since its log-loss/Brier/calibration approach is exactly what we intend to use.
