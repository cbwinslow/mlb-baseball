# Course correction — research warehouse + model ladder

> Program plan. Per-package implementation is separate. First executed
> package: Layer-2 matchup estimator (ADR-271), **not** wired into daily
> `mlb predict` yet.

**Spec:** [`../specs/2026-08-28-course-correction-design.md`](../specs/2026-08-28-course-correction-design.md)

## Workstreams

| ID | What | Status |
|---|---|---|
| W0 | Freeze + spec/ADR | this change |
| W1 | Daily predict finishes / checkpoints | already specified in `2026-08-28-product-and-pipeline-next.md` |
| W2 | Research marts + dump + `query.*` | next after W3a lands |
| W3a | `estimate_matchup_distribution` + shrink + tests | **this change** |
| W3b | Write `markov-v1` into `gold.prediction` for upcoming games only | blocked on W3a |
| W4 | PA-outcome ML | blocked on W3 holdout vs Elo |
| W5 | SQLMesh promotion of ≤3 families | not a blocker |
| W6 | Astro | blocked on W1 + W3b + live market rows |

## W3a (this package)

- [x] `shrink_outcome_distribution` (M=350, n=0 → league)
- [x] `markov_transition_counts_matchup.sql` (team, pitcher, exclude game, before_date)
- [x] `estimate_matchup_distribution`
- [x] `simulate_home_win_rate`
- [x] unit + integration tests
- [ ] W3b: `mlb predict` writes `markov-v1` for `home_win IS NULL` rows only
