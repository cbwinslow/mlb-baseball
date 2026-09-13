## Why

`openspec/project.md` makes v1.1 the release that turns the research database
into a *platform*: a point-in-time feature set, a walk-forward backtest harness,
and one reference baseline model (Elo v2) with a model card. None of it ships,
and the first cut of this change (commits `a3dbe1b`, `7faf584`) was scoped
against a product framing the owner has since replaced.

**The product is a framework distributed as code** — the shape of `pybaseball` /
`baseballr`, but fuller. A user `pip install`s it, runs it, and it bootstraps MLB
data from the original sources into *their own* local environment. We ship code,
schema, and build logic; we do not ship data as the primary artifact. Two
consequences reshape this change:

1. **Redistribution rights stop constraining the feature and model layer.** They
   constrain exactly one thing: the optional `mlb export` → Hugging Face
   snapshot, which keeps its existing per-table exclusions
   (`docs/SOURCE_RIGHTS.md`, `export.py`'s `BACKBONE_EXCLUDED`). The user already
   has the source data locally because they fetched it. The previous plan treated
   `feat.*` as a publication problem. It is not one.
2. **The derived layer does not have to live in PostgreSQL.** Postgres earns its
   place for `raw` and `core`: `bootstrap` and `conform` (cross-source identity
   reconciliation) genuinely need a constrained relational engine. Features and
   models do not — they are recomputable artifacts over a fixed grain, which is
   what DuckDB is for, and what an analyst with no server can actually run.

The result is far smaller than the first cut: no Postgres `feat` schema, no
migration, no Feast, no feature-registry YAML, no four-check leakage battery.
One local DuckDB file, three feature relations, a one-page retrieval function,
and two leakage checks that test the *store* rather than a model.

This change is **slice 1 of 3** (see the roadmap at the end): the store exists,
its contract is honest, and a user can verify both on their own build.

## What Changes

- **`mlb build` emits one local DuckDB file.** It reads PostgreSQL `core` /
  `gold`, builds the feature relations, and writes them into a single DuckDB
  database (default `~/.mlb/mlb.duckdb`, overridable). It wraps the existing
  `migrate` → `conform` → `report` steps rather than replacing them; those
  commands keep working unchanged.
- **A hard boundary at `core`.** PostgreSQL stays authoritative for `raw` and
  `core`. **The feature and model layer is DuckDB-only** — features are built
  there, and models read only from there. Recorded as an ADR (drafted in this
  change as `adr-features-in-duckdb.md`, folded into `docs/DECISIONS.md` at
  implement time) because it scopes — rather than contradicts — the root
  `AGENTS.md` invariant "PostgreSQL is the authoritative system of record."
- **Three feature relations, all in DuckDB.**
  - `feat.player_form` and `feat.pitcher_form` — one row per
    `(entity_id, event_ts, feature_version)`.
  - `feat.game` — a curated wide game-grain assembly (~30–40 columns) built from
    the two form relations plus game context. This is what the first notebook
    loads.
- **Time windows are COLUMNS, never rows.** `woba_7d`, `woba_30d`, `woba_std` —
  no `window` key anywhere, in no primary key and no index. Every rate carries
  its numerator **and** its exposure denominator as columns
  (`woba_30d` alongside `woba_num_30d` and `pa_30d`), so a user can re-derive
  PA/BF-based windows themselves from what ships.
- **Append-only.** A formula change is a new `feature_version`, never an
  `UPDATE`. Rows are frozen at the artifact/release level.
- **Four clocks.** `event_ts` (end of the last game included), `available_ts`
  (`event_ts` + a documented per-source lag), `created_ts` (when the build wrote
  the row), and the decision time the caller supplies at retrieval.
- **`mlb_research.get_historical_features(entity_df, features, timestamp_col=…)`.**
  Feast's signature and vocabulary — feature refs `"view:feature"`, one row out
  per row in, missing stays missing — implemented as a single parameterized
  DuckDB `ASOF LEFT JOIN` filtered on `available_ts <= t` **and**
  `created_ts <= t`. About a page of code. **No Feast**, recorded as a decision
  with its adoption trigger.
- **Two leakage checks, both about the store.** (1) the `available_ts <= t` /
  `created_ts <= t` enforcement; (2) the doubleheader / same-day case — game 2
  cannot see game 1's box score. The "label shuffle" and "inject the outcome"
  checks are *model* diagnostics, not store checks: they move to a notebook
  recipe in slice 3 and are not part of the shipped battery.
- **`mlb verify`.** A new command that runs the leakage checks and the existing
  tie-out checks against the user's own build, so a stranger can audit their
  copy without reading our CI.
- **`mlb_baseball` gains a dependency on `mlb_research`** (not the reverse).
  `mlb verify` calls the same shipped retrieval API an outside analyst calls —
  one implementation, both products. `mlb_research` stays free of
  `mlb_baseball`. Slice 2 moves the harness across this same direction.
- **`gold.game_feature` is left alone.** It is the internal Engine's
  ~240-column table carrying 178 registered feature families
  (`docs/FEATURE_REGISTRY.md`). It is **never** part of the public or DuckDB
  surface, and re-parenting it onto `feat.*` is explicitly not this work — nor
  slice 2's, nor slice 3's.
- **The `delivery` capability is relaxed from an implementation to a
  guarantee.** The current requirement mandates "append-only feature snapshot
  tables keyed by entity and an availability timestamp, an as-of retrieval
  contract, a machine-readable feature registry" — a table shape and a
  framework. It is rewritten to mandate what must be *true* (see Capabilities).

Out of scope for this slice: the walk-forward harness extraction and Elo v2 (see
the roadmap); re-parenting `gold.game_feature`; consolidating
`meta.feature_snapshot` / `meta.experiment_snapshot` /
`gold.game_feature_snapshot`; triaging the 178 Engine families (Phase B); any
model; a hosted feature-serving API; team / matchup feature grains.

## Capabilities

### New Capabilities

_None — the `delivery` capability already covers the feature store and the
reference baseline._

### Modified Capabilities

- `delivery`: rewrite two requirements.
  - *The public distribution is a research platform, not only a data dump* —
    replace the mandated implementation (snapshot tables, registry YAML, a
    leakage battery) with the mandated **guarantee**: a point-in-time feature
    set; every value derived only from records both observable and already in
    the build before its row's stated cutoff; missing stays missing; published
    files immutable within a release tag; retrieval a documented join
    demonstrated by a runnable example. No table shape or framework mandated.
    Also replace "reproducible without a PostgreSQL server" — which the
    framework-as-code framing makes wrong — with **reproducible from the user's
    own build** (we ship build logic, and the user runs it against their own
    environment), plus a separate guarantee that *retrieval* needs no server.
  - *The public distribution includes one reference baseline model* — add that
    every input the baseline consumes must be reproducible from the analyst's
    own build: no project-only feed, no shipped trained artifact, no table whose
    build logic we withhold.

## Impact

- **New:** `mlb build` and `mlb verify` commands; a DuckDB build-path resolver;
  `mlb_baseball/sql/feat_*.sql` (DuckDB dialect) for the three feature
  relations; `mlb_research.get_historical_features` +
  `mlb_research.leakage_checks`; `docs/FEATURE_STORE.md`;
  `openspec/changes/feature-store-v1/adr-features-in-duckdb.md` (→ `docs/DECISIONS.md`);
  unit tests for retrieval and the leakage checks; integration tests for the
  build.
- **Changed:** `mlb_baseball/cli.py` (two new subcommands; existing ones
  untouched); `pyproject.toml` (`duckdb` and `mlb-research` become runtime
  dependencies of `mlb-baseball`, moving out of the `dev` extra);
  `packages/mlb-research/pyproject.toml` (version bump); `.sqlfluff` (a DuckDB
  dialect scope for the new SQL only); `openspec/specs/delivery/spec.md` (via
  the delta); `openspec/project.md` (v1.1 progress + the Postgres/DuckDB
  boundary); `docs/DATA_DICTIONARY.md`, `docs/RESEARCH.md`,
  `docs/SQL_OWNERSHIP.md`, `docs/PUBLIC_API.md`, `docs/DECISIONS.md`.
- **NOT changed:** `gold.game_feature` and its builder; `model/features.py`;
  `model/experiment.py`; `model/elo.py`; the 178 Engine families; `conform.py`;
  ingestion; `export.py`'s rights gate; the Markov engine. No new PostgreSQL
  migration and no `feat` schema in PostgreSQL. No Phase B/C work.
- **New runtime dependency:** `duckdb` (already adopted tooling per
  `openspec/project.md`; already a dependency of `mlb-research`).

---

## Roadmap — the other two slices

The full v1.1 scope (DuckDB build artifact, ADR, feature relations, retrieval
API, harness extraction, dependency inversion, Elo v2, model card, spec
relaxation, three-command CLI) is more than one reviewable PR. It splits into
three independently-shippable slices. Only slice 1 is specified in `tasks.md`;
slices 2 and 3 become their own OpenSpec changes.

**Slice 2 — `feature-store-v1-harness` — done.** Extracted the walk-forward
harness out of `mlb_baseball/model/experiment.py` into
`mlb_research.backtest`: `time_ordered_folds()` (time-ordered, never random),
the as-of frame split, the fit/score loop (`run_backtest`), numpy log loss /
Brier / a reliability (calibration) table via a hand-rolled IRLS logistic fit
(replacing the `sklearn.LogisticRegression` call), and the matched-sample
"common games" paired comparison (`paired_comparison`). **numpy + pandas
only** — model fitting is a caller-supplied `fit_fn` / `predict_fn` callback
pair, so sklearn, xgboost, and a hand-written Elo are the *caller's*
dependency, not the package's; a sequential/stateful model (Elo) gets its
test rows in cutoff order, predicting before its own update folds in.
`experiment.py`'s `run()` is now a thin adapter calling the shared harness
across the dependency direction slice 1 establishes — one implementation,
both products. `experiment.py`'s public API and `meta.experiment*` writes
are behaviorally unchanged (`tests/integration/test_experiment.py` passes
unmodified), including `compare()`: a `paired_comparison`-based rewrite
would have conflicted with the CLI's existing flat per-model-per-fold
output (`mlb experiment compare`), so per an owner decision (2026-09-13,
`openspec/changes/feature-store-v1-harness/tasks.md` task 5.5) `compare()`
is untouched and `paired_comparison` ships as an `mlb_research` utility
with no `mlb_baseball` caller yet.

**Slice 3 — `feature-store-v1-baseline` — done, narrowed (2026-09-13).**
Elo v2 and its model card, both pure numpy inside `mlb_research`: team Elo
plus home field (v1's math, unchanged), plus a preseason prior that fades,
plus a starter-quality adjustment (z-scored `fip_like_30d`, train-fold-only
statistics). The card backtests Elo v2 with the starter adjustment on vs.
off (a home-field-only baseline, same model, one config difference) and
reports a matched-sample `paired_comparison` between the two, with a
limitations section — reproducible by a user running the shipped harness on
their own build, no database, no market data.

Narrowed from the original sketch above via brainstorming with the owner:
investigating `raw.mlb_probable` found roughly five weeks of history, nowhere
near enough to backtest a probable-starter adjustment against, so the model
uses the **actual** starter (`feat.game`'s existing `starter_is_actual =
TRUE`), not the probable one. The notebook recipe carrying the two *model*
leakage diagnostics (label shuffle, injected outcome), the `mlb export` /
Hugging Face publish wiring for the card, market comparison, and the
probable-starter swap itself are all deferred to their own later changes —
see `openspec/changes/feature-store-v1-baseline/proposal.md` for the full
scope and reasoning.
