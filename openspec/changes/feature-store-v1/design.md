## Context

See `proposal.md` — Why. What matters here is the existing ground this slice
stands on, and what it deliberately does not touch.

- **`mlb` is one PostgreSQL warehouse with a `raw` / `core` / `gold` / `meta`
  ladder.** `conform.py` (1,999 lines) builds `core` by reconciling identities
  across Retrosheet, Lahman, the Chadwick register, the MLB Stats API,
  Polymarket and Kalshi — cross-source joins, fuzzy team/venue matching,
  `game_pk` backfill at an ~85% match rate. That work needs a real relational
  engine and is not moving.
- **`gold.game_feature`** is a ~240-column whole-game table built by
  `model/features.py::build` from `mlb_baseball/sql/game_feature_rebuild.sql`
  (`TRUNCATE` + full rebuild; PIT safety expressed as
  `ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING`). It carries **178**
  registered feature families (`docs/FEATURE_REGISTRY.md`) and is read across
  `export.py`, `live.py`, `pipeline.py`, `audit.py`, `research.py`, `cli.py`.
  It is the internal Engine's table and Phase B's triage target.
- **`model/experiment.py`** (1,586 lines) is a working walk-forward harness —
  `folds()`, `_common_rows()` (paired same-game comparison), `_calibration()`,
  `_metrics()` (log loss, Brier, bootstrap CIs) — but it imports sklearn and
  xgboost at module scope and reads `gold.game_feature` through psycopg. Slice 2
  extracts it; this slice leaves it alone.
- **`packages/mlb-research`** is a standalone PyPI loader (`load(table, …)`)
  that already depends on `duckdb` + `pandas` and deliberately does **not**
  depend on `mlb_baseball`.
- **Project SQL rules** (`openspec/project.md`, `docs/SQL_OWNERSHIP.md`): build
  logic lives in versioned `.sql` files run by Python; no SQL strings embedded
  in Python (`scripts/lint_sql_ownership.py` + a pre-commit hook enforce it);
  `mlb_baseball/sql/__init__.py::read_sql` loads them and rejects any name
  containing a path separator. `.sqlfluff` sets `dialect = postgres`
  project-wide.
- **`mlb` has 171 top-level CLI subcommands.** `bootstrap` exists; `build` and
  `verify` are free names.

## Goals / Non-Goals

**Goals**

- One local DuckDB file that a user produces themselves and that every feature
  and model read goes through.
- Three feature relations with an entity grain, append-only semantics, windows
  as columns, and exposure kept next to every rate.
- A retrieval function with Feast's ergonomics and none of Feast's weight.
- Two leakage checks that fail when the *store* is wrong, and pass or fail
  without any model.
- A `delivery` requirement that states a guarantee an implementation can be
  judged against, instead of prescribing the implementation.

**Non-Goals (design-level, beyond the proposal's scope list)**

- Making the DuckDB file a *distribution* artifact. It is a build output on the
  user's disk. Publication of `feat.*` Parquet is slice 3.
- Making the PostgreSQL build path optional. `bootstrap` and `conform` still
  need Postgres; only the derived layer moves.
- Any incrementality. `mlb build` is a full rebuild of the feature relations,
  matching how `conform` and `report` already work.

## Decisions

### D1 — No Feast: build its signature and vocabulary, not its framework

`mlb_research.get_historical_features(entity_df, features, timestamp_col=…)`
uses Feast's exact call shape, its `"view:feature"` reference strings, and its
contract (one row out per row in, PIT-correct, missing stays missing). The
implementation is a single parameterized DuckDB query — roughly a page.

Rationale: everything Feast would give us here we would have to configure
anyway (a registry file, an offline store, a provider), and everything it gives
us that we would *not* configure — online serving, materialization jobs, a
feature server — is Phase C at the earliest. Matching its vocabulary buys the
familiarity without the dependency, and keeps the tables shaped so an adopter
is a small step away.

- **Adoption trigger, recorded:** a real user asks for Feast. At that point it
  is roughly a one-day add, because the relations are already entity-keyed with
  an availability timestamp — which is exactly the shape Feast's offline store
  expects.
- **Alternative rejected — adopt Feast now.** A framework, a registry format, a
  provider abstraction, and a materialization concept, for three relations and
  one join. `openspec/project.md`'s tooling section requires a measured unmet
  requirement before adopting; there is none.
- **Alternative rejected — invent our own vocabulary.** Costs the familiarity
  for nothing.

### D2 — PostgreSQL stops at `core`; the feature and model layer is DuckDB-only

`mlb build` reads PostgreSQL `core` / `gold` and writes the feature relations
into a local DuckDB database. Features are built there. Models read only there.
No `feat` schema in PostgreSQL, no migration, no `feat.asof_*` SQL functions.

Rationale: the two layers have different jobs. `raw` / `core` is a system of
record — constraints, identity reconciliation, provenance, concurrent writers,
incremental ingest. `feat` is a *derived, reproducible artifact* — write-once,
read-heavy, columnar, single-writer, and thrown away and rebuilt whenever a
formula changes. Postgres is right for the first and unremarkable for the
second; DuckDB is right for the second and cannot do the first. Splitting at
`core` also makes the analyst's path real: they run the same build we do, get
the same file, and need no server to query it.

This scopes the root `AGENTS.md` invariant, it does not contradict it —
PostgreSQL remains the authoritative system of record **for raw source data**;
derived features are reproducible artifacts. That reconciliation is why this
needs an ADR (`adr-features-in-duckdb.md`, drafted in this change, folded into
`docs/DECISIONS.md` at implement time).

- **Alternative rejected — features in PostgreSQL, mirrored to DuckDB.** Two
  writers of the same formula, a parity test forever, and a common-SQL-subset
  constraint on every future feature. The previous cut of this design chose it
  (old D4) and paid for it in scope.
- **Alternative rejected — everything in DuckDB, drop PostgreSQL.** `conform.py`
  is a real relational workload with real constraints. Nothing about this change
  argues for moving it, and doing so would risk the part of the system that
  already works.

### D3 — The build artifact: one file, resolved in a fixed order, built by versioned SQL

One DuckDB database file holding all three relations under a `feat` schema.
Path resolution, highest precedence first:

1. `--db <path>` on `mlb build` / `mlb verify`, and the `db=` argument to
   `get_historical_features`;
2. `MLB_DUCKDB_PATH`;
3. `~/.mlb/mlb.duckdb` (directory created on first build).

One file rather than a Parquet directory because a build is one atomic thing to
hand around, back up, or delete, and DuckDB reads its own tables faster than it
reads Parquet. Parquet export stays available for publication (slice 3) — the
file is the working artifact, not the distribution format.

The build logic is versioned `.sql`, per the project rule, in
`mlb_baseball/sql/`. Two mechanical consequences to handle explicitly:

- `.sqlfluff` is `dialect = postgres` project-wide and the new SQL uses DuckDB
  syntax (`ASOF JOIN`). The new files get a DuckDB dialect scope — via an inline
  `-- sqlfluff:dialect:duckdb` directive if sqlfluff honours it, otherwise a
  subdirectory with its own `.sqlfluff` — without changing the dialect for the
  97 existing PostgreSQL files in that directory.
- `read_sql` rejects names containing `/`. If the DuckDB SQL lands in a
  subdirectory, `read_sql` gains support for exactly one path segment, keeping
  the traversal guard.

- **Alternative rejected — a Parquet directory as the build output.** More files
  to keep consistent, no transactional rebuild, and slower for the repeated
  small point lookups retrieval does.
- **Alternative rejected — a path inside the repository.** The artifact belongs
  to the user's environment, not their checkout; a repo-local default invites
  committing a multi-gigabyte file.

### D4 — Three relations; windows are columns; exposure always kept

```
feat.player_form (
  player_id        BIGINT      NOT NULL,
  event_ts         TIMESTAMPTZ NOT NULL,  -- end of the last game included
  available_ts     TIMESTAMPTZ NOT NULL,  -- event_ts + a documented per-source lag
  created_ts       TIMESTAMPTZ NOT NULL,  -- when this build wrote the row
  visible_ts       TIMESTAMPTZ NOT NULL,  -- GREATEST(available_ts, created_ts) -- see D5
  feature_version  VARCHAR     NOT NULL,  -- 'v1'
  pa_7d,  pa_30d,  pa_std     INTEGER,    -- exposure, per window
  so_7d,  so_30d,  so_std     INTEGER,    -- numerators, per window
  woba_num_7d, woba_num_30d, woba_num_std  DOUBLE,
  k_rate_7d, k_rate_30d, k_rate_std       DOUBLE,
  woba_7d, woba_30d, woba_std             DOUBLE,
  ...
  PRIMARY KEY (player_id, event_ts, feature_version)
)
```

`feat.pitcher_form` mirrors it at pitcher grain (`bf_*` exposure, `k_minus_bb_*`,
a FIP-like rate). `feat.game` is a wide game-grain assembly (D7).

**Windows are columns, never rows.** There is no `window` key — not in the
primary key, not in an index, not as a value. One row per entity per timestamp
carries every window side by side. This is the single largest correction to the
previous cut of this design, whose primary key was
`(player_id, event_ts, feature_version, window)`.

Rationale: a `window` row key makes every consumer pivot before it can use two
windows together, multiplies row count by the window count, and makes
`get_historical_features` a pivot rather than a join. Columns make the retrieval
one ASOF join and make a feature reference (`"player_form:woba_30d"`) name
exactly one column.

**Every rate keeps its numerator and its exposure.** `woba_30d` ships with
`woba_num_30d` and `pa_30d`. A rate without its exposure is not a feature — a
20-PA and a 600-PA `k_rate` are different objects — and keeping the denominator
is what lets a user re-derive a PA-based or BF-based window themselves from
day-based windows we ship. A rate is `NULL` when its denominator is zero; a
missing measurement is never a zero.

**Append-only.** A formula change is a new `feature_version`; a historical row is
never `UPDATE`d. Rows are frozen at the artifact/release level, so a training set
built against a tag stays reproducible.

- **Alternative rejected — store only rates.** Loses exposure, loses
  re-derivability, and hides the small-sample cases.
- **Alternative rejected — mutate rows on a formula fix.** Silently invalidates
  every training set built before the fix.
- **Alternative rejected — PA/BF-based windows instead of day-based.** Day-based
  windows are what a decision time actually indexes, and shipping the exposure
  count makes the PA/BF variant derivable. Shipping both would double the column
  count for a transformation the user can do in one line.

### D5 — Four clocks, and one derived column that makes the ASOF join correct

The four clocks: `event_ts` (end of the last game included), `available_ts`
(`event_ts` + a documented per-source lag), `created_ts` (when the build wrote
the row), and the decision time `t` supplied by the caller at retrieval.

A row is legitimately visible at `t` iff `available_ts <= t` **AND**
`created_ts <= t`, which is exactly `GREATEST(available_ts, created_ts) <= t`.
The build stores that maximum as `visible_ts`.

Rationale: DuckDB's `ASOF JOIN` takes exactly one inequality plus any number of
equalities, so two independent inequalities cannot both live in the join
condition, and the second cannot be pushed into a `WHERE` because `t` varies per
input row. Folding them into one monotone key keeps retrieval a single ASOF join
(D6) with the same semantics. `visible_ts` is a derived column, not a fifth
clock: all four remain stored and queryable, and the leakage checks (D8) assert
against `available_ts` and `created_ts` directly, not against `visible_ts`.

The per-source availability lag is a documented assumption, not a measurement —
Retrosheet has no ingest timestamp. The default is conservative
(`event_ts + 1 day`), recorded per source in `docs/FEATURE_STORE.md` and in
`docs/RESEARCH.md`'s honest-limitations content. The leakage checks test the
mechanism, not the lag's numeric truth.

- **Alternative rejected — a correlated subquery per entity row.** Correct, but
  turns a single vectorized join into per-row work and gives up the operator
  that makes this a page of code.
- **Alternative rejected — drop `created_ts` and rely on `available_ts`.** That
  is precisely the leak a late data delivery causes: a record for a pre-`t` event
  that only arrived after `t` would silently enter a pre-`t` feature.

### D6 — Retrieval is one parameterized ASOF LEFT JOIN

```python
mlb_research.get_historical_features(
    entity_df,                                  # entity id + a decision-time column
    features=["player_form:woba_30d", "pitcher_form:k_minus_bb_30d"],
    timestamp_col="event_timestamp",
    db=None,                                    # defaults to the resolved build path
)  # -> DataFrame, one row per entity_df row, in input order
```

Feature refs are `"<relation>:<column>"`. The generated SQL is, per relation:

```sql
SELECT e.*, f.<col>, ...
FROM entities e
ASOF LEFT JOIN feat.<relation> f
  ON e.<entity_id> = f.<entity_id>
 AND e.<t> >= f.visible_ts
WHERE f.feature_version = ? OR f.feature_version IS NULL
```

`ASOF LEFT JOIN` gives the three guarantees for free: it only ever looks
backward (never a later snapshot), it emits exactly one row per left row, and a
left row with no qualifying right row yields `NULL`s rather than a forward fill.
Unknown feature refs raise before any query runs, naming the valid refs.

- **Alternative rejected — build a training set in Python with `merge_asof`.**
  Pandas-only, in-memory, and re-implements in Python what the engine already
  does; it also makes the "missing stays missing" rule a code path rather than a
  join semantic.
- **Alternative rejected — a `get_online_features` sibling.** Nothing serves
  online. Phase C at the earliest.

### D7 — `feat.game` is a curated assembly; `gold.game_feature` is untouched and never public

`feat.game` is one row per game at first pitch, ~30–40 columns: game context
(ids, teams, venue, `event_ts` = scheduled first pitch, the four clocks) plus
home/away pairs of the form features that matter, retrieved as of first pitch
from `feat.player_form` / `feat.pitcher_form`. It is the relation the first
notebook loads and the relation Elo v2 (slice 3) consumes.

**`gold.game_feature` is left alone and is never part of the public or DuckDB
surface. Re-parenting it onto `feat.*` is explicitly not this work.** It is a
~240-column PostgreSQL table carrying 178 registered Engine families, read
across the paused prediction pipeline, and named by `openspec/project.md` as a
**Phase B** triage target — SPECULATIVE, gated, "do not start Phase B work
because the ladder lists it." `feat.*` re-expresses a handful of *proven
formulas* (`team_offense_v1`'s rolling wOBA, `starter_prior_v1`'s FIP and
K/BB rates, `plate_discipline_v1`'s CSW%/whiff) at entity grain; it does not
touch those families' table, builder, or registry.

This is the "two products, one database" line drawn where it belongs: `feat.*`
is the public, minimal, reproducible toolkit surface; `gold.game_feature` plus
the 178 families is the internal Engine.

- **Alternative rejected — `feat.game` as a view over `gold.game_feature`.**
  Puts the Engine's 240 columns and its whole blast radius on the public
  surface, and inverts the boundary D2 exists to draw.
- **Alternative rejected — no `feat.game`, make every consumer assemble it.**
  The assembly is the interesting, easy-to-get-wrong part (as-of-first-pitch
  retrieval for both starters and both lineups). Shipping it once, correctly,
  is the point.

### D8 — Two leakage checks, both store-level, both model-free

`mlb_research.leakage_checks` ships exactly two:

1. **Visibility enforcement.** For a set of `(entity, t)` requests, assert every
   row that contributed has `available_ts <= t` and `created_ts <= t`. Fails when
   `visible_ts` is computed wrong, when a build backdates `created_ts`, or when
   retrieval drops a predicate.
2. **Doubleheader / same-day.** For a same-day doubleheader, assert the features
   retrieved as of game 2's first pitch do not reflect game 1's box score. This
   is the case where a date-grain join silently passes and a timestamp-grain join
   is required — and where `gold.game_feature`'s own ordering comment
   (`model/elo.py`, on `feature_cutoff_at` / `game_number` / `mlb_game_pk`) says
   the project has already been bitten.

Both run without fitting a model, so `mlb verify` can run them on a user's build
with no sklearn, no labels, and no training.

**The "label shuffle" and "inject the outcome as a feature" checks are removed
from the shipped battery.** Both need a model, a fit, and a score to say
anything; both diagnose the *model*, not the store; and a store-level battery
that silently requires a model is a battery most users cannot run. They become a
notebook recipe in slice 3, where a model exists.

- **Alternative rejected — keep all four in the shipped battery.** Drags the
  model dependency into a store check and gives a false impression that a green
  battery clears the model.
- **Alternative rejected — an embargo check.** With `visible_ts` enforced and
  windows computed from completed games only, an embargo is a modelling choice
  for the harness (slice 2), not a store invariant.

### D9 — Three commands, wrapping rather than replacing

- `mlb bootstrap` — sources → PostgreSQL `raw`. **Unchanged**; it already exists.
- `mlb build` — PostgreSQL `raw`/`core` → `gold` + the DuckDB file. **New.** It
  wraps the existing `migrate` → `conform` → `report` sequence and then runs the
  feature build.
- `mlb verify` — leakage checks + tie-out checks against the user's own build.
  **New.**

The three are the *documented* path for an outside user. Every existing command
(`migrate`, `conform`, `report`, `features`, `doctor`, `audit`, `preflight`, and
the other 160-odd) keeps working exactly as it does today: `build` and `verify`
are compositions, not replacements, and nothing is renamed or removed. Whether
`verify` should eventually subsume `doctor` is left open (`DESIGN_REVIEW.md`).

- **Alternative rejected — rename the existing commands.** 171 subcommands with
  scripts, crons (`scripts/mlb_daily_update.sh`, `mlb_api_update.sh`,
  `mlb_odds_update.sh`) and runbooks behind them. A three-command *front door* is
  the goal; a breaking rename is not.

### D10 — The `delivery` requirement is relaxed from an implementation to a guarantee

The live requirement mandates "append-only feature snapshot tables keyed by
entity and an availability timestamp, an as-of retrieval contract …, a
machine-readable feature registry …, and a leakage-test battery." That is a
table shape, a file format, and a framework — written before the shape was
known, and now specific enough that this slice's *better* implementation would
read as non-compliant (no registry YAML; two checks, not a battery).

The rewrite states what must be true: a point-in-time feature set; every value
derived only from records before its row's stated cutoff; missing stays missing;
published files immutable within a release tag; retrieval a documented join
demonstrated by a runnable example. Every existing scenario that tests the
guarantee is kept.

Two substantive corrections travel with it. The "reproducible **without a
PostgreSQL server**" clause is wrong under the framework-as-code framing — the
user *has* Postgres, because `bootstrap` gave them one — so it becomes
"reproducible **from the user's own build**", with a separate guarantee that
*retrieval* needs no server. And the reference-baseline requirement gains that
every input the baseline consumes must be reproducible from the analyst's own
build.

- **Alternative rejected — implement to the current wording.** Ships a registry
  YAML and two model-dependent checks nobody needs, to satisfy a sentence.
- **Alternative rejected — defer the relaxation to slice 3.** Slice 1 would ship
  a store that knowingly violates the live requirement, and a reviewer would have
  no way to tell that from a defect.

### D11 — Slice here, and why here

Slice 1 is the smallest thing that is independently useful and independently
falsifiable: a user can build the store, retrieve from it, and verify it — and
the guarantee it is judged against is settled in the same change. Nothing in it
needs a model to exist.

Slice 2 (harness) and slice 3 (Elo v2 + card) both consume slice 1 and neither
consumes the other's output for its own correctness, but slice 3's card is
produced *by* slice 2's harness, so the order is fixed.

The dependency direction (`mlb_baseball` → `mlb_research`) is established here,
not in slice 2, because `mlb verify` must call the same shipped retrieval API an
outside analyst calls — otherwise slice 1 ships two retrieval paths. Slice 2 then
only moves code across a direction that already exists.

## Risks / Trade-offs

- **Two stores means two places to look for a number.** → The boundary is one
  sentence (`core` and below is Postgres; `feat` and above is DuckDB), stated in
  the ADR, `openspec/project.md`, and `docs/FEATURE_STORE.md`. `mlb build` is
  the only thing that crosses it.
- **`duckdb` becomes a runtime dependency of `mlb_baseball`, and `mlb-research`
  becomes a hard dependency of it.** → `duckdb` is already adopted tooling and
  already a dependency of `mlb-research`. The `mlb-research` edge is real: a
  `pip install mlb-baseball` needs `mlb-research` resolvable from PyPI, not only
  from the `uv` workspace. Confirm the PyPI state before the dependency moves
  out of the `dev` extra; until then the workspace source keeps local installs
  working.
- **`available_ts` lag is an assumption, not a measurement.** → Documented per
  source, conservative by default, and named in the honest-limitations page. The
  leakage checks test that the mechanism is enforced, not that the lag is right.
- **`feat.game`'s ~30–40 columns are a judgement call.** → The curation rule is
  open (`DESIGN_REVIEW.md`); the relation is versioned, so widening it later is a
  new `feature_version`, not a migration.
- **DuckDB `ASOF JOIN` is doing load-bearing correctness work.** → The two
  leakage checks are the regression test for exactly that, and they run in CI
  against a fixture as well as on a user's build.
- **A stale DuckDB file silently serves old features.** → `created_ts` is on
  every row and `mlb verify` reports the build's `created_ts` range, so "my
  numbers are stale" is answerable without guessing.

## Migration Plan

Nothing to migrate: no PostgreSQL schema change, no data move, no existing
consumer re-pointed. `gold.game_feature` and every consumer of it keep working
untouched.

Rollback is deleting the DuckDB file and the two new subcommands; the warehouse
is unaffected. If the DuckDB direction is abandoned later, the feature build SQL
is the only thing to port, and D5's `visible_ts` is the only DuckDB-specific
construct in it.

## Open Questions

Four decisions are genuinely open and are tracked with their options and
recommendations in `DESIGN_REVIEW.md`: the DuckDB file location and resolver
precedence; whether `mlb build` wraps or eventually replaces
`report` / `conform` / `features` (and whether `mlb verify` subsumes `doctor`);
the day-based window sizes to ship; and the rule by which `feat.game` curates
its ~30–40 columns. None of them changes the specs, the approach, or the task
breakdown — each is answerable during implementation from the code and a
one-line owner confirmation.
