# Course correction: research warehouse + model ladder

**Status:** Design spec. Owner-authorized execution 2026-08-29 ("proceed how
you want"). First code slice is Layer-2 matchup Markov in `markov.py`
(ADR-271). Daily `mlb predict` wiring landed as W3b (ADR-272).

**Companion plan:** [`2026-08-28-course-correction.md`](../../archive/superpowers-plans/2026-08-28-course-correction.md)

**Decision record:** ADR-271 in [`../../DECISIONS.md`](../../DECISIONS.md)

---

## Two products, one warehouse

| Product | Job |
|---|---|
| **A. Research database** | Documented grains, cited formulas, `mlb dump`, thin Python readers over *our* tables |
| **B. Prediction ladder** | Elo/log5 → matchup Markov sim → optional PA-outcome ML → market comparison |

pybaseball fetches. We store, conform, and query. Do not wrap pybaseball as
a user-facing API.

## SQL vs SQLMesh

Both, one writer per table. Named `mlb_baseball/sql/*.sql` is the formula
Python runs today. SQLMesh promotes that same formula after a tie-out.
Researchers query PostgreSQL tables and never install SQLMesh.

## Model ladder

RE24 is the value of a base-out state (accounting). The predictor is
P(PA outcome | state, matchup). Layer 2 (this slice) estimates that from
Retrosheet for pitching team/pitcher vs batting team, shrinks toward
league with M=350 PA (*The Book*), and can feed `simulate_game`.

Only Retrosheet events strictly before the target game's date are
eligible, and the target game's own events are excluded — the SQL
contract's `before_date` and `exclude_game_id` parameters, applied to
both the matchup sample *and* the league prior it shrinks toward. `n`
for the shrink is plate appearances (`bat_event_fl = 'T'`), not the raw
transition-row count.

Pitch-level ML and extra GBM columns are not next.

## Freeze

No new Engine packages, no `FEATURE_COLUMNS` expansion, no Astro until
tomorrow has a model % and a market %.
