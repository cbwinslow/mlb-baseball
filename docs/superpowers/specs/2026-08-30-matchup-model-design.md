# Plate-appearance matchup model — design

**Status:** Owner-reviewed 2026-08-30 (decisions recorded below). Next step:
`superpowers:writing-plans` → implementation plan.

**Relation to existing plans:** this is `plans/04D` ("estimate transition
matrices and run expectancy **by context**; simulate plate appearances,
innings, games") made concrete, plus the 2026-08-19 owner direction in
`plans/04` about plate-appearance-level modelling. It is the near-term
statistical version; the "eventual" PyTorch sequence/attention model in
`plans/04` is a separate, later track. Grok built `markov-v1` (ADR-271/272);
this is v2.

## Why this spec exists

`markov-v1` (ADR-272) sits at ~50.4% game-winner accuracy and loses to
`elo-v1` on log loss even fed the realized starter (ADR-275 holdout: Δ
−0.0152, 95% CI [−0.031, −0.0001], n=389). Root cause, from the review:

- It estimates one **team-batting-side vs starting-pitcher** plate-appearance
  outcome distribution, shrunk M=350 toward the league mean.
- MLB team-level offensive/defensive rates are similar enough that after that
  shrink the distribution is close to league-average for almost every game,
  so the simulated win probability lands near 50/50.
- It uses **zero** of `gold.game_feature`'s ~130 engineered columns and knows
  nothing about who is actually batting.

The engine underneath — the 24-state base/out chain, the absorbing-chain
run-expectancy solve, the game simulator with real ending rules, the
empirical-Bayes shrinkage — is sound and stays. What changes is **what
distribution feeds the simulator**: from "team vs starter" to "this specific
batter vs this specific pitcher, in this park."

`docs/RESEARCH.md`: "the plate-appearance-level matchup approach is a natural
direction once the game-level model is working"; a Nov-2025 hierarchical
pitcher-batter matchup model found "~1 additional win per 162-game season" in
simulation. This is an incremental edge, not a leap past the 55–58% ceiling.

## Goals

1. A served `markov-v2` (or renamed) whose held-out log loss and accuracy
   **beat `elo-v1`** on the ADR-274 promotion bar (CI excludes zero, point
   estimate ≥ 0.002 log loss), on a real point-in-time holdout.
2. Per-PA outcome probabilities conditioned on batter, pitcher, handedness,
   and park — reusing the existing simulator, not a new one.
3. A lineup-aware game simulation for upcoming games (each of the 9 batters
   modeled, in order), with an honest fallback when the lineup isn't posted
   yet.
4. Every intermediate model transparent and independently scored; the PA
   outcome model itself calibrated against held-out seasons before it is
   composed into a game.

## Non-goals

- Beating the betting markets. That's a later bar (needs issue #107 fixed
  first) and a separate review.
- In-game / live win probability. `markov.py` has the machinery
  (`simulate_in_game_win_probability`); wiring it is out of scope here.
- Pitch-sequencing / count-state modeling. `pitch_seq_tx` and count columns
  exist; a count-conditioned chain is a possible refinement, deferred.
- Any new data **source**. Everything below uses `raw.retrosheet_event`,
  `raw.mlb_playbyplay`, `raw.statcast_pitch`, and the MLB Stats API we
  already ingest (`docs/DATA_SOURCES.md`).

## What we have and what's missing

| Need | Have | Gap |
|---|---|---|
| Historical PA rows w/ batter, pitcher, handedness | `raw.retrosheet_event` (`bat_id`, `pit_id`, `bat_hand_cd`, `pit_hand_cd`, `bat_lineup_id`, `event_cd`), 1910–2025 | 2026 needs `raw.mlb_playbyplay` (parsed, per ADR-034's known gap) |
| Batter / pitcher true-talent rates (K%, BB%, HR%, BABIP), point-in-time | `starter.py` builds rolling starter rates into `gold.game_feature`; `raw.retrosheet_event` supports the same for any batter | No per-**batter** rolling rate table yet |
| Park factors | `park.py` → `gold.game_feature.*park_factor*` | none |
| Realized lineups (for training/holdout) | `raw.mlb_boxscore_batting.batting_order` (completed games, 2026+); `raw.retrosheet_event.bat_lineup_id` (1910–2025) | none for the training side |
| **Probable lineups (for upcoming games)** | — | **Missing.** MLB posts them ~2–4h pre-game; the schedule endpoint hydrates them (`hydrate=lineups`). New table + a near-game poll. |

## Approaches

### A — Hierarchical / multinomial PA outcome model → existing simulator (recommended)

A model that, for a (batter, pitcher, park, handedness) tuple, outputs a
categorical distribution over PA outcomes: `{K, BB, HBP, 1B, 2B, 3B, HR,
IP_OUT}` (in-play outs; SF/errors folded in). Then map each outcome to its
base/out transition (mostly deterministic; hits use league baserunner-advance
rates) and hand the resulting per-PA distribution to `markov.simulate_game`,
one distribution per lineup slot.

Estimator: **partial-pooling / empirical Bayes**, not a single flat GLM.
Three levels, shrunk in sequence:
1. league PA outcome rates (by handedness matchup L/L, L/R, R/L, R/R),
2. batter's own rate and pitcher's own rate this season-to-date (the
   "true talent" estimates, à la Tango's `log5` for each outcome),
3. the specific batter×pitcher head-to-head count, shrunk hard (n is
   typically 0–15 lifetime).

Combine batter-rate and pitcher-rate into an expected PA distribution with a
per-outcome `log5` (odds-ratio) formula against the league rate, then blend in
the head-to-head sample by its own `M`. Park is a multiplicative adjustment on
HR and (weaker) on hits.

- **Pro:** transparent, each level independently checkable; reuses the whole
  simulator; `log5`-per-outcome is textbook (`RESEARCH.md` "Head-to-head win
  probability (log5)"); handles cold-start by construction.
- **Pro:** the PA model is itself a scoreable artifact (calibrate P(K) etc.
  against held-out seasons before composing a game).
- **Con:** more moving parts than a flat regression; the "map outcome →
  transition" step needs its own validation (baserunner advancement is not
  fully deterministic).
- **Con:** compute — 9 lineup slots × ~4 PA/game × `n_games` sims. Roughly
  3–4× `markov-v1`'s per-game cost. Manageable at `n_games` ~2000–5000.

### B — Matrix factorization for batter×pitcher

Learn low-rank batter and pitcher embeddings from the full head-to-head
matrix, predict each cell's outcome distribution (`RESEARCH.md` "Matrix
factorization … for the batter-vs-pitcher cold-start problem").

- **Pro:** principled cold-start; can capture "this batter struggles with
  this *type* of pitcher" without hand-coding pitch types.
- **Con:** far less transparent — an embedding is not auditable the way a
  `log5` blend is; harder to explain a promotion review; a bigger first
  build. **Revisit if A plateaus.**

### C — Feed `markov-v1`'s probability + features into a logistic/GBM

Take `markov-v1`'s win probability as one column alongside `home_elo`,
park, bullpen, platoon, rest, etc., and fit a game-winner model on all of it
(`plans/04F`, `stack.py`).

- **Pro:** cheapest; literally "combine efforts."
- **Con:** `stack.py` already tried stacking log5/elo/gbm/market and **did not
  beat `gbm-v1`** (ADR-058). `markov-v1` is ~uninformative (~50%), so adding
  it to a stack adds noise, not signal. This is worth *one* quick check
  (add `markov-v1` to the existing `stack.py` inputs, re-run its holdout) but
  is not expected to be the answer.

### Recommendation

**A**, with **C as a 30-minute sanity check first** (add markov to the stack,
confirm it doesn't magically help — it won't, but cheap to rule out). B is the
fallback if A's accuracy plateaus below Elo.

## Design (Approach A)

### 1. Data — probable lineup ingestion

- New `raw.mlb_lineup` (or extend the schedule hydrate): `game_pk`, `team_id`,
  `player_id`, `batting_order` (1–9), `_captured_at`, `_loaded_at`. Append-only
  snapshots, change-detected per `(game_pk, team_id, batting_order)` like the
  probable-pitcher pattern (ADR-047/048).
- Fetched by a **near-game poll** — the existing 5-minute `mlb_api_update`
  already runs; add a `hydrate=lineups` call scoped to games starting in the
  next ~6 hours, so it isn't 30 teams every 5 minutes.
- `docs/DATA_SOURCES.md` row for MLB Stats API updated in the same change
  (it's the same source, new endpoint field).
- Health check: `upcoming games starting <3h from now that have a lineup`.

### 2. Per-batter rolling rate table

- `mlb_baseball/model/batter.py` + SQL, mirroring `starter.py`'s shape:
  point-in-time rolling K%, BB%, HBP%, 1B%, 2B%, 3B%, HR%, IP-out% for every
  batter, from `raw.retrosheet_event` (1910–2025) and `raw.mlb_playbyplay`
  (2026), by handedness of the opposing pitcher.
- Landed as new `gold.game_feature` columns? **No** — this is per-batter, not
  per-game. A separate `gold.batter_rate` keyed `(player_id, as_of_date,
  vs_hand)`, or computed on the fly in the matchup SQL. Decide in review.
- Same leakage discipline as `starter.py`: strictly games before the cutoff,
  reconciled against `raw.bref_batting` season totals via `mlb doctor`.

### 3. PA outcome model

`mlb_baseball/model/pa_outcome.py`:

- `estimate_pa_distribution(conn, *, batter_id, pitcher_id, park_factor,
  bat_hand, pit_hand, before_date, seasons) -> dict[Outcome8, float]`
- League rates by handedness matchup (cached per cutoff, like the current
  league prior).
- `log5` per outcome: `p = (b * l / g) / ((b * l / g) + (1-b)(1-l)/(1-g))`
  extended to the multinomial by normalizing across the 8 outcomes.
- Head-to-head sample blended by its own `M_h2h` (small — start at 20 PA,
  tune on the holdout).
- Park: HR rate `× hr_park_factor`, hit rates `× (1 + 0.3*(hits_park - 1))`.
- Returns something the simulator can consume: reuse
  `markov.adjust_outcome_distribution_for_matchup` *or* build the base/out
  distribution directly from the 8-outcome vector + league advancement rates.
  The latter is cleaner; the former is already written. Review call.

### 4. Lineup-aware game simulation

`markov.py` extension (or `sim_predict` v2):

- `simulate_game_with_lineups(away_lineup_dists, home_lineup_dists, rng,
  ...)` — like `simulate_game` but each half-inning steps through the batting
  order (persisted across innings), drawing from that slot's PA distribution.
- The 24-state base/out chain is unchanged; only the outcome draw per PA now
  depends on which batter is up.
- Pitcher change modeling (owner decision: in v2.0). The starter is pulled
  when a simulated game crosses a hook threshold — batters faced / pitches
  (estimate ~3.8 pitches/PA) / times through the order / runs allowed —
  fit against real 2023–2025 hook data (`raw.retrosheet_event` has the pitch
  count and the pitcher of record per PA). After the hook, the lineup's PA
  distributions are recomputed against the **opposing bullpen's** aggregate
  rate line (`bullpen.py` already estimates these, with a fatigue signal).
  A single bullpen "unit" rate in v2.0 — modeling individual relievers by
  leverage is a v2.1 refinement.

### 5. Fallback when no lineup is posted

Most `mlb predict` runs happen at 06:00 UTC — lineups aren't out. Fallback,
in order:
1. the most recent *actual* lineup that team used (from
   `raw.mlb_boxscore_batting`), with today's opposing pitcher/park;
2. failing that, the team's 9 most-frequent batting-order slots this season;
3. failing that, `markov-v1`'s team-level distribution (graceful degrade).

The served prediction records which tier it used, so the holdout can score
"lineup known" and "lineup fallback" separately — and the deployed cron can
optionally re-run `predict` for that day's slate once lineups post.

### 6. Evaluation

- **PA model first, standalone:** held-out season, compare predicted P(K),
  P(BB), P(HR)… to realized rates — reliability curves + Brier per outcome.
  Must be calibrated before composing a game (Plan 04D contract).
- **Game model:** extend `scripts/eval_markov_holdout.py` — it already
  recomputes per-game and pairs against stored baselines. Add a `markov-v2`
  path and a `--lineup-mode {realized,fallback}` flag.
- Bar: beat `elo-v1` on the ADR-274 gate. Then a promotion review (ADR-274)
  → promote / hold / return-with-gaps.

## Build sequence (small PRs, each measured)

0. **`markov/` package split** (ADR-275 follow-up) — pure `markov/core`
   (state, RE solve, simulator, shrink — no I/O) vs `markov/estimate` (reads
   the DB). Mechanical, no behaviour change, unblocks clean library
   signatures for everything below. Own PR, done first.
1. **C sanity check** — add `markov-v1` to `stack.py` inputs, re-run its
   holdout, record the (expected null) result. ~half a day.
2. **Lineup ingestion** — `raw.mlb_lineup`, hourly poll (`0 * * * *`) +
   scoped `predict` re-run, `DATA_SOURCES.md`, health check, idempotency
   test. Independent of the model.
3. **`batter.py` + `gold.batter_rate`** — per-batter rolling rates, matview,
   `mlb doctor` reconcile against `raw.bref_batting`. Independent; useful on
   its own (this is a `baseballr`-style public lookup).
4. **`pa_outcome.py`** — the multinomial `log5` blend + park. Its standalone
   calibration eval (reliability + per-outcome Brier on a held-out season)
   is the acceptance gate for this PR — no game composition yet.
5. **hook model** — when is the starter pulled? Fit batters-faced / pitch-
   count / TTO / runs thresholds on 2023–2025 real hook data. Own small PR.
6. **`simulate_game_with_lineups`** — steps the batting order across innings,
   applies the hook (→ bullpen rate line), unit-tested (walk-offs, extras,
   order persistence, mid-game pitcher switch).
7. **`markov-v2` writer** in `sim_predict` + the fallback tiers + provenance.
8. **Holdout + promotion review.** Beats Elo → ADR-27x promotion, retire the
   v1 writer. Doesn't → ADR-27x return-with-gaps, consider Approach B.

Steps 2 and 3 are safe to start in parallel with 0/1 and are independently
valuable. Steps 4–8 are the model and are sequential.

## Risks

- **Leakage.** Batter/pitcher season aggregates are the classic trap
  (`RESEARCH.md`, ADR-032). Everything point-in-time, rolling, cutoff-scoped —
  same discipline as `starter.py`. The `mlb doctor` reconcile catches drift.
- **Cold-start still bites.** Even the hierarchical blend leans heavily on
  batter-rate × pitcher-rate for a rookie or a first-ever matchup. That's
  fine — it degrades to "good batter vs good pitcher," which is more signal
  than markov-v1 has now.
- **Compute.** 3–4× per-game cost. Acceptable for a ~400-game daily slate at
  `n_games` 2000; the holdout (2000+ completed games × both lineup modes) is
  a multi-hour run — budget for it, or sample.
- **The ceiling is real.** Best case this is Elo + ~1 win/162. If the holdout
  says "beats Elo by 0.003 log loss," that *is* the win — don't chase 60%.
- **2026 PA data.** `raw.retrosheet_event` stops at 2025; the live season
  needs `raw.mlb_playbyplay` parsed to the same shape (ADR-034 known gap).
  Step 4 has to handle both or the 2026 holdout is thin.

## Owner decisions (2026-08-30)

1. **`markov-v2` is a new model version.** `markov-v1` keeps writing during
   the build. Once `markov-v2` is validated and strictly supersedes v1
   (everything v1 does, plus more, and it beats v1 on the holdout), the v1
   writer is retired — the ADR-274 review that promotes v2 records that.
2. **Materialized.** `gold.batter_rate` (or a matview) keyed
   `(player_id, as_of_date, vs_hand)`, refreshed in the daily path like the
   other `gold` enrichments. Faster daily runs; the holdout can point at a
   historical snapshot.
3. **Model bullpen changes in v2.0.** A starter is pulled after a
   pitch/batter/inning threshold (tuned on real hook data) and the lineup's
   PA distributions switch to the opposing bullpen's rates (`bullpen.py`
   already estimates these). Not deferred.
4. **Lineup poll: separate hourly job** (`scripts/mlb_lineups_update.sh`,
   `0 * * * *`), not the 5-minute cron — lineups change on the scale of
   hours, and the 5-minute `mlb_api_update` is already the tightest loop on
   the box. The hourly job also triggers a scoped `mlb predict --slate today`
   re-run so served `markov-v2` rows upgrade from the fallback tier to the
   real lineup once it posts.

## On reusability ("think like `baseballr`")

Every piece below is built as a **library function with a clean signature and
no hidden coupling**, usable standalone by someone who just wants, say, a
batter's point-in-time K% or a park-adjusted PA distribution — not only by
the daily pipeline:

- `batter.rates(conn, player_id, as_of, vs_hand) -> RateLine` — pure lookup.
- `pa_outcome.estimate(conn, *, batter_id, pitcher_id, park, hands, before)
  -> PaDistribution` — the log5 blend, no pipeline state.
- `markov.simulate_game_with_lineups(...)` — takes distributions, returns a
  `GameResult`; knows nothing about `gold.game_feature`.
- `sim_predict` is the only piece that knows about the schema and the daily
  slate; it composes the library pieces.

This matches the split `markov.py` should already have (ADR-275 follow-up:
pure `markov/core` vs `markov/estimate` that reads the DB). The matchup work
is a good forcing function to do that split.
