# MLB Platform User Manual & Operations Guide

This manual is the hands-on operational guide for engineers, researchers, and data scientists working with the MLB Research & Forecasting Platform. It explains how all the moving parts fit together and provides step-by-step CLI commands for running ingestion, feature engineering, simulations, model training, and health audits.

---

## 1. Architecture Overview & Data Flow

```
[Raw Sources: Statcast / Retrosheet / Odds]
                    │
                    ▼  (Atomic download & ingestion)
           raw.* Database Tables
                    │
                    ▼  (Multi-pass conformance & entity resolution)
          core.* Database Tables
                    │
                    ▼  (Vectorized SQL & SQLMesh transformations)
          gold.game_feature & gold.game_export (80+ point-in-time features)
                    │
       ┌────────────┴────────────┐
       ▼                         ▼
 [Machine Learning Models]   [Markov Simulator]
(GBDT / Logistic / Stacking) (24-State Absorbing Chains)
       │                         │
       └────────────┬────────────┘
                    ▼
          gold.prediction & Evaluation Marts
                    │
                    ▼  (Astro / Web Serving Layer)
          serve.* Read-Only Marts (Odds Grid / Visualizations)
```

---

## 2. Quickstart & CLI Commands

The platform includes a CLI entrypoint `mlb` (configured in `pyproject.toml`).

### 2.1 Database & System Health Check
Verify database connectivity, schema integrity, and feature boundary constraints:
```bash
# Run full system diagnostics and health assertions
mlb doctor

# Or execute python health checks directly
.venv/bin/python -m mlb_baseball.model.health_check
```

### 2.2 Ingestion & Conformance
Bootstrap historical data or run daily incremental updates:
```bash
# Bootstrap Retrosheet and Statcast data for specified seasons
mlb bootstrap --seasons 2018-2025

# Run daily update connector
mlb update --date 2024-10-01

# Reconcile player identities and game keys across sources
mlb conform
```

### 2.3 Feature Generation & Enrichment
Compute all 80+ sabermetric, command, movement, and matchup difference features into `gold.game_feature`:
```bash
# Build/refresh all gold features
mlb feature build

# Run specific feature family enrichment
.venv/bin/python -c "
import psycopg
from mlb_baseball.model import enrich_feature_stage
with psycopg.connect('dbname=mlb') as conn:
    enrich_feature_stage(conn)
"
```

### 2.4 Markov Game & Matchup Simulation
Simulate inning run distributions or full full-game matchups with pitch arsenals:
```bash
# Run 10,000 game simulations with custom pitch arsenal edge
.venv/bin/python -c "
import random, psycopg
from mlb_baseball.model import markov
with psycopg.connect('dbname=mlb') as conn:
    dist = markov.estimate_outcome_distribution(conn, [2024])
    rng = random.Random(42)
    # Simulate matchup: Home Pitcher edge +1.2 runs/100, Away Pitcher edge -0.5
    result = markov.simulate_matchup_game(dist, rng, home_edge_runs_per_100=1.2, away_edge_runs_per_100=-0.5)
    print(f'Final Score: Away {result.away_runs} - Home {result.home_runs} ({result.innings} innings)')
"
```

### 2.5 Model Training & Evaluation
Train calibrated ML models and evaluate out-of-sample log-loss, Brier score, and ROI:
```bash
# Train baseline Log5, Logistic, and LightGBM models
mlb train --target home_win --train-seasons 2018-2023 --val-season 2024

# Evaluate calibration and Brier decomposition on held-out test sets
mlb eval --model-id lgbm_win_v2 --test-season 2025
```

---

## 3. Serving Layer & Web Platform Roadmap

To power an OddsTrader/Baseball Savant-style research and forecasting website:
1. **Frontend**: Astro + Tailwind + React/Svelte components.
2. **Hosting**: Cloudflare Pages / Netlify / Vercel (free static hosting + serverless functions for live predictions).
3. **Database**: PostgreSQL (or Neon Serverless Postgres for cloud deployment).
4. **Key Web Pages**:
   - **Daily Betting Grid**: Matchups, starting pitchers, live market odds, model win probability, and calculated $+EV$ edge.
   - **Pitcher Attack Zone Heatmap**: Interactive SVG strike zone rendering heart, shadow, chase, and waste pitch distributions.
   - **Pitcher Profile & Strasburg Curveball Drop Cards**: Visualizing Induced Vertical Break (IVB) and vertical separation.
   - **Matchup Simulator Tool**: Allows users to select any pitcher vs lineup and simulate 1,000 games instantly in browser via WASM/Markov.
