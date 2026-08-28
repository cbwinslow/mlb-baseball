# MLB Platform Assessment & Expansion Plan

## Executive Summary

This document evaluates the current state of the MLB research and forecasting platform, identifies gaps and opportunities, and proposes a prioritized expansion roadmap covering new features, GPU acceleration, product offerings, and monetization paths.

---

## Part 1: Current State Assessment

### What We Have Built (Impressive Foundation)

> [!NOTE]
> The platform is already deeper than most public MLB analytics projects. The combination of 129 seasons of historical data, 287-column feature engineering, a 12-model experiment lab, and prediction market integration is genuinely differentiated.

#### Data Estate
| Layer | Tables | Key Assets |
|-------|--------|------------|
| `raw` | 138 | 13.5M Statcast pitches (2008–2026), 16.7M Retrosheet plays (1898–2026), 16.5M Retrosheet events, 12.6M win probability records, 35K Polymarket + 1.8K Kalshi market contracts, Lahman/B-Ref/Chadwick register |
| `core` | 326 | 236K games, 25.5K players, conformed team/venue/market dimensions |
| `gold` | 9 | 287-column `game_feature` table, 33K predictions, `game_export` view, RE24 matrix |
| `meta` | 13 | Full provenance chain (ingestion runs, model runs, experiment snapshots, feature stability) |
| `serve` | 4 | Daily betting grid, pitcher cards, matchup previews, +EV prediction market screener |

#### Feature Engineering (28 Registered Families)
- **Team-level**: Win rates (season + L10), Pythagenpat, Elo, run differential, wOBA, wRC+, OBP/SLG/ISO/BB%/K%/BABIP, comprehensive BsR (wSB/XBT%/UBR/wGDP), prior WAR/OAA/Sprint Speed
- **Pitching**: Starter FIP/K%/BB%/HR%, xFIP, SIERA, CSW%/Whiff%/F-Strike%, batted ball profiles (GB%/FB%/LD%/HR-FB), attack zones (Heart/Shadow/Chase), fastball velocity + offspeed delta, IVB/Curve Drop/Vertical Separation/Spin RPM, platoon splits (vs LHB/RHB wOBA/K%), career experience (BF/IP), rest days + 7-day workload
- **Bullpen**: Relief FIP/K%/BB%, trailing 3-day fatigue, SIERA/xFIP, contact quality, attack zones
- **Catcher**: CSAE%, framing runs
- **Park/Weather**: 1/3/5yr park factors, component factors (HR/2B/3B/LHB-HR/RHB-HR), air density index, center-field wind vectors
- **Matchup Interactions**: 23 symmetric home-minus-away difference vectors, platoon matchup wOBA deltas, win-rate trends

#### Models & Evaluation
| Model | Type | Status |
|-------|------|--------|
| Log5 (Bill James) | Odds-ratio baseline | ✅ Production |
| Elo (margin-adjusted) | Sequential rating | ✅ Production |
| GBM (XGBoost) | 37-feature gradient boosting | ✅ Production |
| Stacking meta-learner | L2-regularized logistic (log5 + elo + gbm + markets) | ✅ Production |
| Run totals regression | Combined score prediction | ✅ Production |
| Markov simulator | 24-state base/out chain + pitch arsenal matchups | ✅ Production |
| Experiment lab | 12 families × calendar folds × bootstrap CIs | ✅ Verified |
| Feature selection | Permutation stability + forward-stepwise | ✅ Verified |

---

### Critical Gap: The GBM Only Uses 37 of 287 Features

> [!IMPORTANT]
> The production GBM model (`gbm-v1`) uses only 10 required + 27 optional columns from `gold.game_feature`. That means **250 features we built are not being used by the production model**. This includes all of the recent advanced pitching metrics (SIERA, xFIP, CSW%, pitch movement, attack zones), Statcast expected metrics (xwOBA, barrel%), catcher framing, weather physics, and all 23 matchup difference vectors.

This is the single highest-leverage improvement available right now.

---

## Part 2: GPU Assessment

### Hardware Available
| GPU | Compute Capability | VRAM | Status |
|-----|-------------------|------|--------|
| Tesla K80 (GPU 0) | 3.7 (Kepler) | 12 GB | ✅ Detected, idle |
| Tesla K80 (GPU 1) | 3.7 (Kepler) | 12 GB | ✅ Detected, idle |
| Tesla K40m | 3.5 (Kepler) | 11 GB | ✅ Detected, idle |

### Software State
| Component | Version | GPU-Compatible? |
|-----------|---------|-----------------|
| NVIDIA Driver | 470.256.02 | CUDA ≤ 11.4 only |
| System NVCC | 11.4 | ✅ Matches driver |
| CUDA Toolkit (also installed) | 11.8, 12.8 | ⚠️ 12.x won't work with driver 470 |
| XGBoost (pip) | 3.3.0 (built with CUDA 12.9) | ❌ Compute 3.7 dropped in XGBoost 2.x+ |
| PyTorch (system) | 2.12.0+cu130 | ❌ Not in venv; CUDA 13.0 >> driver 11.4 |
| LightGBM | Not installed | — |
| Numba/CuPy | Not installed | — |

### GPU Recommendation

> [!WARNING]
> The K80/K40 cards are Kepler architecture (compute 3.5/3.7). Modern XGBoost, PyTorch, and TensorFlow have **dropped support** for compute < 5.0. The installed XGBoost 3.3 was compiled against CUDA 12.9 and won't see these GPUs even if the driver matched.

**Practical GPU options that WILL work:**

1. **Monte Carlo simulation via Numba CUDA** — Numba's `@cuda.jit` still supports compute 3.5+. We can GPU-accelerate the Markov chain game simulator to run 100K+ simulated games per second instead of ~1K/s on CPU. This is the **highest-value GPU use case** for this project.

2. **Install XGBoost 1.7.x** (the last version supporting compute 3.5) alongside the current 3.3.x CPU version — but this adds complexity for marginal gain since XGBoost training on our dataset sizes (< 300K rows × 100 features) completes in seconds on CPU anyway.

3. **CuPy for matrix operations** — CuPy supports compute 3.5+ and can accelerate the RE24 transition matrix estimation and bootstrap confidence interval calculations.

**Not worth pursuing:** PyTorch/TensorFlow neural network training on these GPUs. The compute capability is too old for modern frameworks and the dataset isn't large enough to justify the engineering cost.

---

## Part 3: Expansion Roadmap

### Tier 1 — High Impact, Do Now (This Week)

#### 1A. Retrain GBM with Full 80+ Feature Set
The single most impactful change. The production GBM uses 37 features but we've built 287 columns. After feature selection (which we already have tooling for), we should retrain with the expanded feature set.

**Action items:**
- Run `mlb experiment snapshot --target home_win` to capture current state
- Run stepwise feature selection across the full 287-column set
- Retrain GBM-v2 with the selected expanded feature set
- Compare Log Loss / Brier score against GBM-v1 on held-out seasons
- If improved, promote to production and update `serve.*` views

#### 1B. Populate `gold.game_feature` with Data
`gold.game_feature` currently has 0 rows. We need to run the full feature pipeline:
```bash
mlb features       # Build base features
mlb predict        # Generate predictions
```

---

### Tier 2 — Medium Impact, This Sprint

#### 2A. GPU-Accelerated Monte Carlo Game Simulator
Install `numba` with CUDA support. Rewrite the core Markov simulation loop as a CUDA kernel. Target: simulate 100K+ game outcomes per second across all three GPUs (~36 GB combined VRAM).

**Use cases:**
- Full game run-distribution estimation (not just expected runs)
- Win probability with confidence intervals
- Over/under probability distributions
- Player prop distributions (strikeouts, hits, etc.)

**Implementation:**
```python
# mlb_baseball/model/gpu.py
from numba import cuda
import numpy as np

def get_device():
    """Return 'cuda' if GPU available, else 'cpu'."""
    try:
        from numba import cuda
        if cuda.is_available():
            return 'cuda'
    except ImportError:
        pass
    return 'cpu'
```

#### 2B. Player-Game Props Prediction System
New model targets beyond game winner and total runs:
- Pitcher strikeouts (over/under)
- Pitcher outs recorded / innings pitched
- Batter hits, total bases, home runs
- First-five-inning winner and total

These are high-value Kalshi/Polymarket contract types that our data already supports.

#### 2C. Live In-Game Win Probability Updates
We already have `raw.mlb_win_prob` (12.6M rows) and `raw.mlb_playbyplay`. Build a real-time websocket listener that:
- Polls MLB StatsAPI every 30 seconds during live games
- Updates in-game win probability using our Markov model given current base/out state
- Recalculates +EV signals against live Polymarket/Kalshi contract prices
- Pushes updates to `serve.live_game_state`

---

### Tier 3 — Strategic, Next 2 Weeks

#### 3A. Season Projection System (PECOTA/ZiPS-style)
- Per-player rest-of-season projection using aging curves, regression to the mean, and Marcel-style weighting
- Team-level projected wins and playoff odds via remaining-schedule simulation
- Daily updated standings projections

#### 3B. Lineup Optimization Engine
Use the player-level Markov model to:
- Estimate expected runs for any batting order permutation
- Identify optimal lineup construction given platoon matchups
- Quantify the cost of suboptimal lineup decisions

#### 3C. Historical Replay & Backtest Dashboard
An interactive web interface (Astro/Vite) showing:
- Historical model performance charts (calibration plots, Brier over time)
- Season-by-season accuracy breakdowns
- Head-to-head model comparison tables
- Feature importance visualizations

#### 3D. Betting Edge Scanner (Premium Feature)
Expand `serve.prediction_market_alpha` into a full edge-detection system:
- Kelly criterion position sizing
- Bankroll simulation (Monte Carlo on GPU)
- Track record with verified timestamped picks
- Alerts when edges exceed user-defined thresholds

---

### Tier 4 — Differentiators, Ongoing

#### 4A. Pitch-Level Neural Sequence Model
The 13.5M Statcast pitch rows support training a pitch-outcome sequence model:
- Input: pitch type, velocity, spin, location, count, base/out state, batter/pitcher identity
- Output: probability of strike/ball/contact/whiff/foul/hit
- Use: Feed into Markov simulator as pitch-level transition probabilities

This is where the GPUs could eventually help if upgraded to Ampere+ cards.

#### 4B. Injury/Rest Impact Model
- Correlate IL stint returns, rest patterns, and travel schedules with performance
- Flag fatigue risk games for starters and bullpens
- Incorporate travel distance and timezone changes

#### 4C. Umpire Strike Zone Model
- Quantify umpire tendencies from Statcast pitch data
- Estimate home/away bias, zone size, and consistency
- Include as matchup feature in prediction models

#### 4D. Weather Physics Model Enhancement
- Go beyond air density index to model temperature effects on ball carry, spin decay, and pitcher grip
- Incorporate humidity, altitude, and dew point
- Cross-reference with park-specific dimensions

---

## Part 4: Feature Inventory — What's Built vs What's Wired

> [!IMPORTANT]
> This table identifies which of our 28 feature families are actually feeding into production models versus sitting unused in `gold.game_feature`.

| Feature Family | In GBM-v1? | In Stack? | In Markov? | In Totals? | Action |
|---------------|-----------|---------|----------|----------|--------|
| `game_base_v1` (win rate, runs, rest) | ✅ | Via log5/elo | ❌ | ✅ (park_factor) | — |
| `starter_prior_v1` (FIP, K%, BB%, HR%) | ✅ | ❌ | ❌ | ❌ | Wire into totals |
| `bullpen_v1` (FIP, K%, BB%, fatigue) | ✅ | ❌ | ❌ | ❌ | Wire into totals |
| `park_factor_v1` / `park_weather_v1` | ✅ (basic) | ❌ | ❌ | ✅ (basic) | Expand to full component factors |
| `team_offense_v1` (wOBA, wRC+) | ✅ | ❌ | ❌ | ❌ | Wire into totals |
| `war_prior_v1` | ✅ | ❌ | ❌ | ❌ | — |
| `oaa_prior_v1` | ✅ | ❌ | ❌ | ❌ | — |
| `speed_prior_v1` | ✅ | ❌ | ❌ | ❌ | — |
| `bsr_v1` / `bsr_comprehensive_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `diff_v1` / `matchup_diff_v2` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `trend_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `experience_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `plate_discipline_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `batted_ball_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `re24_leverage_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `pitcher_estimator_platoon_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `statcast_expected_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `pitcher_command_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `pitch_movement_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `platoon_splits_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `catcher_framing_v2` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |
| `starter_workload_v1` | ❌ | ❌ | ❌ | ❌ | **Add to GBM-v2** |

**19 of 28 feature families are NOT being used by any production model.** This is the biggest opportunity.

---

## Part 5: GPU Integration Plan (Simple, with CPU Fallback)

### Architecture

```
mlb_baseball/compute.py          # Device detection + fallback
mlb_baseball/model/simulate.py   # GPU-accelerated Monte Carlo
```

### `compute.py` — Simple Device Switch
```python
"""Compute device detection with automatic CPU fallback."""

import os
import logging

logger = logging.getLogger(__name__)

_FORCE_CPU = os.environ.get("MLB_FORCE_CPU", "").lower() in ("1", "true", "yes")


def gpu_available() -> bool:
    """Check if Numba CUDA is available and not force-disabled."""
    if _FORCE_CPU:
        return False
    try:
        from numba import cuda
        return cuda.is_available()
    except ImportError:
        return False


def get_device() -> str:
    """Return 'cuda' or 'cpu'."""
    if gpu_available():
        logger.info("GPU detected, using CUDA acceleration")
        return "cuda"
    logger.info("Using CPU (set MLB_FORCE_CPU=0 and install numba for GPU)")
    return "cpu"
```

### Environment Variable Override
```bash
# Force CPU even if GPU is available
MLB_FORCE_CPU=1 mlb predict

# Use GPU (default when available)
MLB_FORCE_CPU=0 mlb predict
```

---

## Part 6: Recommended Implementation Sequence

| # | Task | Impact | Effort | GPU? |
|---|------|--------|--------|------|
| 1 | Populate `gold.game_feature` (run pipeline) | 🔴 Critical | Low | No |
| 2 | Retrain GBM-v2 with 80+ features | 🔴 Critical | Medium | No |
| 3 | Install `numba[cuda]` + `compute.py` device switch | 🟡 Medium | Low | Yes |
| 4 | GPU Monte Carlo Markov simulator | 🟡 Medium | Medium | Yes |
| 5 | Player-game prop predictions | 🟡 Medium | Medium | No |
| 6 | Live in-game win probability | 🟡 Medium | Medium | No |
| 7 | Season projection system | 🟢 Strategic | High | Monte Carlo |
| 8 | Betting edge scanner (premium) | 🟢 Strategic | Medium | Monte Carlo |
| 9 | Documentation site (Astro/Starlight) | 🟢 Strategic | Medium | No |
| 10 | Pitch-level sequence model | 🟢 Future | High | Needs newer GPU |

---

## Part 7: Product Offering Summary

### Free Tier
- Daily game predictions (winner, totals)
- Historical model accuracy dashboard
- Open-source codebase and methodology docs

### Premium Tier ($10–25/month)
- Real-time in-game win probability updates
- +EV prediction market edge scanner (Polymarket/Kalshi)
- Player prop predictions with confidence intervals
- Lineup optimization recommendations
- Email/push alerts when edges exceed thresholds
- API access for programmatic consumers

### Research Tier (Pay-what-you-want / Patreon)
- Full methodology papers with academic citations
- Jupyter notebooks with reproducible analysis
- Access to feature engineering pipeline
- Model training logs and experiment comparisons
