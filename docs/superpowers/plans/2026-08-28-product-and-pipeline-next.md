# Product, pipeline, and research-database next steps

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the daily prediction path healthy and honest, then add the two capabilities the betting product actually needs (live market match + player-aware Markov), without deleting `mlb conform` / `mlb predict` and without adding more Engine packages.

**Architecture:** Keep PostgreSQL + the `mlb` CLI as orchestrators. Speed comes from incremental gold SQL, indexes, and checkpointed stages. SQLMesh owns set-based gold formulas after a tie-out; named `mlb_baseball/sql/*.sql` files remain the readable formula source until that cutover. Identity, Elo, Markov sim, and training stay Python (ADR-088).

**Tech Stack:** PostgreSQL 16 (`mlb` production / `mlb_test` tests), Python 3.12, `uv`, existing `mlb_baseball.model`, SQLMesh spike under `transforms/` (not production), GitHub issues #70 / #84.

**Spec:** [`docs/PRODUCT_DIRECTION.md`](../../PRODUCT_DIRECTION.md), [`docs/superpowers/specs/2026-08-28-pipeline-performance-design.md`](../specs/2026-08-28-pipeline-performance-design.md), ADR-266.

## Global Constraints

- Production database name is `mlb`. Test database is `mlb_test`. Say the target before any destructive or long `predict`/`conform` command.
- Never start a second exclusive workflow while `meta.ingestion_run` has `status=running` for `model` or `core`.
- $0/month. No paid odds feed. Kalshi + Polymarket only, kept as distinct `model_version`s.
- Statcast-derived pages are `local_research` until `SOURCE_RIGHTS.md` changes.
- Champion model on disk is `models/gbm-v1.json`. Do not expand `FEATURE_COLUMNS` without a saved matching artifact.
- Do not add a new Engine package. Wire or relabel existing ones via the Bucket B plan.

---

## File Structure

- Modify: `mlb_baseball/model/market.py` (Task 3 — live upcoming match)
- Modify: `mlb_baseball/model/markov.py` / `simulate.py` (Task 4 — player-aware distributions)
- Modify: `mlb_baseball/model/__init__.py` (Task 2 — checkpointed stages)
- Create: `migrations/00NN_raw_lookup_indexes.sql` only after hypopg proof (Task 2)
- Modify: `mlb_baseball/model/gbm.py` + `models/` only after Task 1 coverage is real (Task 5)
- Docs with every task: `plans/PROGRESS.md`, `docs/DECISIONS.md`, this file's checkboxes

---

### Task 1: Close the in-flight production predict, then recount

**Files:** none until the run ends. Then `plans/PROGRESS.md`.

**Interfaces:**
- Consumes: production `mlb` read-only.
- Produces: a dated PROGRESS row with Elo / starter / xFIP / RE24 / last `gold.prediction` coverage.

- [ ] **Step 1: Wait. Do not run `mlb predict` or `mlb conform` against `mlb`.**

  As of 2026-08-28 04:45 UTC pid **3860016** is a live `mlb predict` (exclusive workflow lock). Overlapping it will fail or stall.

- [ ] **Step 2: When `meta.ingestion_run` for that pid is `success` or `failed`, recount (read-only, database `mlb`)**

```sql
-- target: production mlb, read-only
SELECT status, started_at, finished_at, error
FROM meta.ingestion_run WHERE pid = 3860016;

SELECT count(*) AS rows,
       count(home_elo) AS elo,
       count(home_starter_id) AS starter,
       count(home_starter_xfip) AS xfip,
       count(home_starter_siera) AS siera,
       count(home_batting_re24) AS re24
FROM gold.game_feature;

SELECT model_version, max(generated_at), count(*)
FROM gold.prediction GROUP BY 1 ORDER BY 2 DESC;
```

- [ ] **Step 3: `mlb doctor` against production (read-only checks)**

  Run: `DATABASE_URL=postgresql:///mlb mlb doctor`
  Target stated: production `mlb`. Doctor is not supposed to write; if a check looks mutative, stop.

- [ ] **Step 4: Write the numbers into `plans/PROGRESS.md`.** If `home_elo` is still 0 after a successful run, that is P0 — file/fix before any retrain.

- [ ] **Step 5: Commit the PROGRESS evidence only.** No production writes in that commit.

---

### Task 2: Pipeline speed (issue #84 Phase 1 remaining)

**Files:**
- Possibly create: `migrations/00NN_raw_event_pitch_lookup_indexes.sql`
- Modify: `mlb_baseball/model/__init__.py` (`run()` / `enrich_feature_stage()` commit points)
- Test: `tests/integration/test_model_enrich_stage.py`, `tests/integration/test_ingest_tracking.py`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-08-28-pipeline-performance-design.md` §Phase 1.3 and §2.1
- Produces: measured before/after wall times in the commit message

- [ ] **Step 1: hypopg on production `mlb` (read-only hypothetical indexes; do not CREATE INDEX yet)**

  Target: production `mlb`. `CREATE EXTENSION IF NOT EXISTS hypopg` is a catalog write — **ask the owner before installing extensions on `mlb`**. Prefer `mlb_test` with a restored schema, or the owner-approved extension list in the spec (1.6).

- [ ] **Step 2: EXPLAIN (ANALYZE, BUFFERS) the PLT-01 / COM-01 / SHP-01 statements with and without hypothetical `(pit_id)`, `(bat_id)`, `(pitcher)`, `(batter)` indexes.**

  Build a real index in a migration only if the plan changes and measured time drops enough to pay for slower COPY ingest.

- [ ] **Step 3: Checkpoint `model.run()` — commit after base build, after each enrichment group, after Elo, after predictions.** Record progress in `meta` (new table needs a migration). A crash must resume, not rebuild from zero.

  Regression: kill the connection mid-enrichment in `mlb_test` and prove the next `run()` continues. Follow `tests/integration/test_ingest_tracking.py::test_failure_path_logs_error_and_leaves_connection_usable`.

- [ ] **Step 4: Do not parallelize enrichments until checkpoints exist (spec 2.3 depends on 2.1).**

---

### Task 3: Live pre-game Kalshi / Polymarket moneyline match

**Files:**
- Modify: `mlb_baseball/model/market.py`
- Modify: `mlb_baseball/conform.py` only if upcoming games cannot join `core.market` (today `core.game` is completed-only)
- Test: `tests/integration/test_model_market.py` — upcoming row, moneyline-only, Polymarket multi-type fan-out regression (same as ADR-053)

**Interfaces:**
- Consumes: `raw.kalshi_snapshot` / `raw.polymarket_snapshot` captured before `raw.mlb_schedule.game_datetime`; `gold.game_feature` rows with `home_win IS NULL`
- Produces: `gold.prediction` rows for `kalshi-v1` / `polymarket-v1` on still-upcoming games (one moneyline per game)

- [ ] **Step 1: Write the failing integration test** — an upcoming `gold.game_feature` row + a pre-cutoff moneyline snapshot must yield exactly one `gold.prediction` row; a spread/F5 snapshot must not.

- [ ] **Step 2: Implement the upcoming-game match.** Do not blend Kalshi and Polymarket. Reuse ADR-053's `sportsmarkettype = 'moneyline'` filter. This also unblocks issue #79 (serve view fan-out) once `core.market` carries a type or the view uses the same filter.

- [ ] **Step 3: CLI dispatch test** if a new flag is added (`tests/unit/test_cli_dispatch.py`).

- [ ] **Step 4: Health check: upcoming games with a snapshot but no market prediction.**

---

### Task 4: Player-aware Markov v1 (starter vs team offense)

**Files:**
- Modify: `mlb_baseball/model/markov.py` (`estimate_outcome_distribution` already has `bat_home`; add pitcher- or team-filtered counts)
- Named SQL: `mlb_baseball/sql/markov_transition_counts.sql` (parameterized filter, not a second formula)
- Test: `tests/integration/test_model_markov.py` + keep `scripts/verify_markov_calibration.py`

**Interfaces:**
- Consumes: `raw.retrosheet_event` pre/post state (existing)
- Produces: per-game home/away outcome distributions for `simulate_game`; a `gold.prediction` model_version (e.g. `markov-v1`) only after it beats Elo on the 2024–2025 holdout by the same 0.002 log-loss gate spirit as GBM

- [ ] **Step 1: v1 grain is team batting vs opposing starter, not every batter vs every pitcher.** Lineup-level comes after probable lineups exist (admission queue PLN-02 is still blocked).

- [ ] **Step 2: Shrink small samples toward the league matrix (empirical Bayes; *The Book* PA thresholds).** NULL distribution → league fallback, never a silent zero.

- [ ] **Step 3: Held-out calibration** — estimate through 2023, simulate 2024–2025, report home-win rate, total-runs mean, log-loss vs Elo/GBM/Kalshi on the matched sample.

- [ ] **Step 4: Joint parlay paths** — `P(home wins AND over 8.5)` = count of simulated games, not a copula. Do not expose `parlay.py` on the site until this exists.

---

### Task 5: GBM retrain (only after Task 1)

**Files:**
- Modify: `mlb_baseball/model/gbm.py` `OPTIONAL_COLUMNS` only if the new columns are populated in production
- Artifact: `models/gbm-v1.json` or a new `gbm-v2.json` that `MODEL_PATH` actually points at

- [ ] **Step 1: Confirm production non-null rates for every column in `FEATURE_COLUMNS`.** Drop any column that is NULL for all 2026 upcoming rows unless XGBoost missing-value handling is already the contract (it is — ADR-044) *and* historical rows are populated.

- [ ] **Step 2: `mlb train` against production `mlb` (owner-authorized; this writes `meta.model`).** Same 2023 / 2024–2025 split. Must beat Elo *and* log5 by `MIN_PRACTICAL_LOG_LOSS_IMPROVEMENT`. Also report log-loss vs `kalshi-v1`/`polymarket-v1` on the overlapping sample — beating Elo but losing to the market is not a betting product.

- [ ] **Step 3: If `eligible: false`, revert `FEATURE_COLUMNS` immediately (ADR-086 / ADR-044).**

---

### Task 6: Research mart (public-safe)

**Files:**
- Finish ADR-057: wire `mlb report` + doctor checks if still missing
- `docs/RESEARCH_QUERY_RUNBOOK.md` recipes for wOBA, FIP, RE24, wSB at player-season grain
- No Statcast in `public_safe` dumps

- [ ] **Step 1: Confirm whether `mlb report` exists in `cli.py`. If not, add it with a dispatch test.**
- [ ] **Step 2: Doctor: `gold.player_season` / `team_season` have rows.**
- [ ] **Step 3: Document the researcher entrypoint in `USER_MANUAL.md` and `MAP.md`.**

---

### Task 7: Bucket B wiring (parallel, not blocking 1–5)

Follow the Bucket B wiring plan on branch `metrics/bucket-b-triage-rubric` when that PR is available; until then use `docs/PACKAGE_VALIDATION_STATUS.md` as the classification table. Do not start Astro (Plan 05 / issue #15) until Tasks 1, 3, and 5 can put a real number on the daily board.

---

## Spec coverage

| PRODUCT_DIRECTION section | Task |
|---|---|
| Let in-flight predict finish | 1 |
| Do not delete conform/predict; speed | 2 |
| Live market match | 3 |
| Player-aware Markov + parlays | 4 |
| GBM retrain / gbm-v1 vs v2 artifact | 5 |
| Research database | 6 |
| Agy engines = wire, don't add | 7 |
| Plan 05 Astro | blocked on 1, 3, 5 |
