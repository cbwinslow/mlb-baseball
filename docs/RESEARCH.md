# Phase 2 Research — Models and Techniques

A running, source-cited knowledge base of sabermetric and ML techniques evaluated for Phase 2 (see ADR-032). Organized by technique, not chronologically — update an existing section rather than appending a new dated entry. Each entry: what it is, the concrete formula/method where one exists, source(s), and a note on how (or whether) it applies to `gold.game_feature`/the win-probability model.

## Head-to-head win probability (log5)

**Formula:** `P(A beats B) = WPa² / (WPa² + WPb²)`, where `WPa`/`WPb` are the two teams' winning percentages.

Independently derived twice: Bill James proposed it axiomatically in 1981 (the "log5" method); a SABR paper by Richards derives the same formula constructively (via a neutral-proxy-team thought experiment) and validates it directly against 204,858 decisive MLB games, 1871-2013 — **97.90% efficiency ratio**, Brier skill score 0.0556 above naive baseline, consistent (90-94%+ efficiency) across eras. A refined version adjusting for league composition (`P'`) reaches 98.32%.

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

**Relevance:** `core.play` has the inning/half-inning/outs data (16M+ rows, 1901+) to build this directly. Not needed for `gold.game_feature` v1 (log5/Elo/Pythagenpat don't require it), but a natural follow-up: a team's actual base-out transition efficiency this season is a "true talent" signal independent of clustering luck, and could become its own feature later. [calestini/markov-baseball](https://github.com/calestini/markov-baseball) is a clean, directly-adaptable reference implementation of the state space and transition-matrix construction.

Sources: [calestini/markov-baseball](https://github.com/calestini/markov-baseball), [A Markov Chain Approach to Baseball (Bukiet, Harold, Palacios)](https://pubsonline.informs.org/doi/pdf/10.1287/opre.45.1.14)

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

## Feature engineering backlog (post-gbm-v1 finding)

gbm-v1 (ADR-033) barely beat Elo despite having 10 features to Elo's 2 — the current feature set doesn't carry much more signal than a bare Elo rating. Research below, cross-checked against what we actually already have ingested (`docs/DATA_SOURCES.md`) before proposing anything new to fetch — the point is using data we already have, not adding sources.

**Starting pitcher quality** — research consensus (Wharton thesis, CS229 Stanford project, MDPI feature-selection study) ranks this among the most predictive single factors, more so than team-level pitching stats alone. FIP/xFIP/SIERA (defense-independent pitching — strikeouts, walks, home runs are what a pitcher actually controls, per DIPS theory) are more predictive of *future* performance than ERA. **What we have**: `raw.bref_pitching` (full traditional stat line) and `raw.statcast_pitcher_expected` (Statcast's own `xera`, 2015+) both exist but are **season aggregates** — same leakage trap as `core.player_war` (ADR-032): usable only as a prior-season lag, not mid-season. For a genuine point-in-time, no-leakage, *within-season* signal, `core.play` has per-event data (`pitcher_id`, `event_code` — confirmed directly against real data: `3`=K, `14`/`15`=BB/IBB, `23`=HR, `2`/`16`/`18`-`22`=other PA-ending outcomes) back to 1901, enough to compute a rolling strikeout-rate/walk-rate/home-run-rate for a starter's own prior starts this season, the same window-function shape already used for team win%. Getting a true innings-pitched-denominated FIP requires reconstructing IP from out-sequences, real added complexity; a per-batter-faced K%/BB%/HR% composite is a legitimate, simpler proxy in the same spirit, at the cost of not being on a familiar ERA-like scale.

**Bullpen quality and fatigue** — research (InsidethePen usage-tracking analysis) is direct: relievers now handle 40%+ of innings, and WHIP/K%/BB% predict bullpen betting value better than ERA; fatigue (pitches thrown in the last 5 days, back-to-back appearances) measurably reduces effectiveness independent of quality. Buildable from `core.play` the same way as starter quality (identify a team's non-starting pitchers' appearances, roll up rate stats + a recency/workload count) — a real, separate, second piece of engineering from starter quality, not a byproduct of it.

**Team-level offensive true talent (xwOBA/barrel%/hard-hit%)** — Statcast's own expected-stats framework strips out park/luck/defense better than plain batting stats; barrel rate specifically is cited as one of the most stable, predictive batted-ball metrics. **What we have**: `raw.statcast_batter_expected` (xwOBA) and `raw.statcast_batter_exitvelo` (barrel%, hard-hit%, avg exit velo), both season-aggregate (2015+, Statcast era only) — same prior-season-lag treatment as WAR, not usable mid-season without leakage.

**Park factors** — standard methodology (FanGraphs, Baseball Prospectus): multi-year rolling ratio of a park's runs-per-game to the league average, scaled around 100. **What we have**: enough real historical `core.game` data (home/away scores by venue, back to 1871) to compute this ourselves directly — no external source needed, purely a derived feature from data already in `core`.

**Rest days** — `gold.game_feature.home_rest`/`away_rest` are already reserved columns in the schema (ADR-032), never populated. Straightforward: days since each team's prior game, computable directly from `core.game`'s date history. No research needed, just not built yet.

### Recommended build order

1. ✅ **Rest days** — built (`mlb_baseball/model/features.py`).
2. ✅ **Starting pitcher true FIP + K%/BB%/HR%** — built (`mlb_baseball/model/starter.py`, ADR-034). Both approaches, not a forced choice — true FIP on the reserved `home_starter_era` column plus the raw rates in new `home_starter_k_pct`/`bb_pct`/`hr_pct` columns (migration 0016). Verified against real deGrom 2018 data, then at full scale (13,613 pitcher-seasons) against `raw.bref_pitching`, wired as a permanent `mlb doctor` reconciliation. **Known gap**: `raw.retrosheet_event` covers 1910-2025 only — 2026 (the live season) needs the equivalent from `raw.mlb_playbyplay`, a separate parsing task, not yet built.
3. **Park factors** — purely derived from data we already have, no leakage risk (multi-year rolling, always using seasons strictly before or a trailing window, not the current in-progress season's still-accumulating data).
4. **Bullpen quality/fatigue** — real value per research, but a distinct, second body of core.play engineering work from starter quality, not a quick add-on.
5. **Team offensive true talent (xwOBA/barrel%)** — season-lagged like WAR, same shape as the already-reserved-but-unbuilt `home_war_prior`/`away_war_prior` columns; 2015+ only (Statcast era), so pre-2015 games would carry this as NULL.
6. **2026 (current-season) starter quality from raw.mlb_playbyplay** — closes starter.py's biggest practical gap (no signal for the live season `mlb predict` actually serves), separate parsing work against a different schema than Retrosheet's.

## Further reading — found, not yet fully read

- Retrosheet's own research collection (uses Retrosheet data specifically, updated regularly — 6 new articles added in 2025): [retrosheet.org/Research/Research.htm](https://retrosheet.org/Research/Research.htm). Flagged as directly relevant: Calzada, "Deepball: Modeling Expectation and Uncertainty in Baseball With Recurrent Neural Networks"; Soper, "Understanding the Value of the Next Run" (run expectancy); Nutaro, "Prospect Theory and the Favorite Long-Shot Bias in Baseball" (behavioral-economics angle on market/betting bias — relevant once `core.market` timing gap, issue #1, is fixed).
- Charlie Pavitt's sabermetrics research bibliography (large index of papers using Retrosheet data): [retrosheet.org/Research/Pavitt/Research Summaries.pdf](https://www.retrosheet.org/Research/Pavitt/Research%20Summaries.pdf)
- arXiv 2511.02815 (full text) — PDF text extraction failed in this environment (no `pdftotext`/working PDF library installed); worth fetching properly before building the evaluation harness, since its log-loss/Brier/calibration approach is exactly what we intend to use.
