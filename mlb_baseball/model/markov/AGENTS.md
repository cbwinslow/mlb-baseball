# Markov Simulation DOX

## Purpose

Own the base/out-state Markov mathematics and its database-backed estimators. This
subtree is intentionally split so pure probability/simulation mechanics can be
understood and tested independently from PostgreSQL and source-query concerns.

## Ownership

- `core.py` owns in-memory state definitions, physical/probability invariants,
  transition/outcome distributions, run expectancy, empirical-Bayes shrinkage,
  game/half-inning simulation, matchup adjustments, and in-game simulation.
- `estimate.py` owns PostgreSQL reads from Retrosheet/Statcast and conversion of
  database rows into the pure types/functions in `core.py`.
- `__init__.py` is the package import facade and must not reintroduce unnecessary
  database/ML dependency coupling into pure-core imports.

## Local Contracts

### Pure-core boundary

`core.py` must remain free of database access, SQL, network I/O, and source-client
objects. It should be importable and unit-testable using only in-memory values plus
its mathematical dependencies.

Do not move a convenience database lookup into `core.py`; put source estimation in
`estimate.py` or another adapter and pass the resulting typed values into core.

### State model

- The chain uses 24 transient base/out states: 8 base configurations x 3 out
  counts.
- All states at three outs collapse to the single `TERMINAL` absorbing state;
  base occupancy after the half-inning ends has no meaning.
- `EMPTY_ZERO_OUTS` is the canonical half-inning start state.
- Transition-count inputs must satisfy baseball conservation constraints before
  probabilities are built. Impossible rows raise `MarkovError`; they are never
  silently normalized away.
- Outgoing probabilities must sum to one within the defined numerical tolerance.

### Simulation failure semantics

`DegenerateSimulation` is a distinct `MarkovError` subtype for a distribution that
cannot resolve simulated ties within the bounded simulation contract. Preserve
that distinction so callers can skip one degenerate matchup without swallowing a
real data/invariant violation.

Simulation caps/prior constants affect results and are model parameters, not
arbitrary implementation details. Changes to `SIM_MAX_INNINGS`, matchup prior
strength, or unresolved-trial policy require reproducibility/evaluation review.

### Estimation and source readiness

`estimate.py` reads named SQL resources and hands typed rows/distributions to
`core.py`.

- Retrosheet event and game-info relations are separate connector dependencies;
  readiness checks must require both.
- When required source tables have not been bootstrapped, estimator functions that
  document the "not ready yet" contract return empty values rather than raising an
  opaque PostgreSQL undefined-table exception or manufacturing zero-filled data.
- SQL belongs in `mlb_baseball/sql/` resources; do not grow large estimator SQL
  strings inline.

### Point-in-time matchup estimation

Matchup estimates must remain cutoff-safe:

- `exclude_game_id` removes the target game;
- `before_date` includes only games strictly before the cutoff date;
- league shrinkage priors must use the **same cutoff and batting-side filters** as
  the sparse matchup sample;
- pitcher/batting-team filters and PA counts must not accidentally include the
  target/future game;
- a sparse sample is shrunk toward an appropriate prior rather than treated as a
  fully trusted estimate.

A future-informed league prior is still leakage even if the target-specific rows
were filtered correctly.

### Baseball-side semantics

`bat_home` uses source values `'1'` (home batting side) and `'0'` (away batting
side). Invalid textual values such as `'home'`/`'away'` must fail loudly instead of
silently matching zero rows.

Non-plate-appearance transitions can remain part of the base/out chain while PA
counts used for shrinkage weights follow the documented Retrosheet event flag
semantics.

## Work Guidance

Before changing Markov behavior:

1. read the relevant core/estimate function and named SQL resource;
2. read the focused unit/integration/evaluation tests;
3. state whether the change is mathematical, source-estimation, performance, or
   model-policy work;
4. preserve deterministic seeded behavior where tests/evaluation depend on it;
5. add a hand-checkable small example for new invariants/formulas before relying
   on Monte Carlo aggregate tests.

Do not use Monte Carlo to test a quantity that has a deterministic analytic or
small-state check available.

Do not optimize simulation with GPU/Numba/vectorization until profiling identifies
a real bottleneck and before/after results preserve statistical behavior.

## Verification

Use the focused Markov/unit tests and database estimator/integration tests that
exercise the changed contract, then broader model verification if result
probabilities change.

Representative checks:

```bash
uv run pytest tests/unit -q -k markov
uv run pytest tests/integration -q -k markov
uv run ruff check mlb_baseball/model/markov tests
uv run mypy mlb_baseball/model/markov
```

For a probability/model-policy change, record seeds, sample size, cutoff seasons,
and before/after calibration/evaluation evidence rather than only asserting the
simulation "looks right."

## Child DOX Index

No child DOX files. `core.py` and `estimate.py` are already the durable local
boundary; add file sidecars only if one grows enough non-obvious contract surface
to justify another progressive-disclosure layer.
