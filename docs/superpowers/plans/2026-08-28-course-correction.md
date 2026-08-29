# Course correction — research warehouse + model ladder

> Program plan. Per-package implementation is separate. Executed so far:
> the Layer-2 matchup estimator (W3a, ADR-271) and its daily `mlb predict`
> write path (W3b, ADR-272), both on `feat/matchup-markov` (PR #100).

**Spec:** [`../specs/2026-08-28-course-correction-design.md`](../specs/2026-08-28-course-correction-design.md)

## Workstreams

| ID | What | Status |
|---|---|---|
| W0 | Freeze + spec/ADR | this change |
| W1 | Daily predict finishes / checkpoints | already specified in `2026-08-28-product-and-pipeline-next.md` |
| W2 | Research marts + dump + `query.*` | next after W3a lands |
| W3a | `estimate_matchup_distribution` + shrink + tests | done (PR #100) |
| W3b | Write `markov-v1` into `gold.prediction` for upcoming games only | done (PR #100, ADR-272) |
| W4 | PA-outcome ML | blocked on W3 holdout vs Elo |
| W5 | SQLMesh promotion of ≤3 families | not a blocker |
| W6 | Astro | blocked on W1 + W3b + live market rows |

## W3a — matchup estimator (PR #100)

- [x] `shrink_outcome_distribution` (M=350, n=0 → league)
- [x] `markov_transition_counts_matchup.sql` (team, pitcher, exclude game, `before_date` from `gameinfo.date`)
- [x] `estimate_matchup_distribution` (`bat_home` / `pitcher_min_pa` backoff, cutoff-safe league prior)
- [x] `simulate_home_win_rate`
- [x] unit + integration tests against `mlb_test`; full suite, Ruff, and mypy clean
      (canonical path: `CONTRIBUTING.md` — `uv sync --extra dev`, `uv run ruff check .`,
      `uv run mypy`, `uv run sqlfluff lint`, `uv run pytest`; CI runs unit/lint/type
      and integration as separate jobs, `.github/workflows/ci.yml`)

## W3b — daily write path (PR #100, ADR-272)

- [x] `sim_predict.predict()` appends `markov-v1` for `home_win IS NULL` rows only
- [x] wired into `model.run()` after log5/Elo/GBM; deterministic seed per `mlb_game_pk`
- [ ] holdout of `markov-v1` vs Elo and Kalshi/Polymarket on the same games — gates promotion past `candidate` (W4 depends on it)
