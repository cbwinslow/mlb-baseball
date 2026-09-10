# ADR draft — features live in DuckDB; PostgreSQL is the system of record for raw source data

> **Draft.** Fold into `docs/DECISIONS.md` at implement time (task 1.2) as the
> next ADR number — currently **ADR-287**, but that file is newest-first and
> other changes may land first, so re-check the maximum before inserting.
> Written in that file's existing shape (`## ADR-NNN: <title>`, then
> `**Decision:**` / `**Context:**` / `**Rationale:**` / `**Revisit if:**`).

---

## ADR-287: features and models live in DuckDB; PostgreSQL is the system of record for raw source data

**Decision:** PostgreSQL remains authoritative for `raw` and `core`. The derived
feature layer and everything that reads it does **not** live in PostgreSQL.
`mlb build` reads PostgreSQL `core` / `gold` and writes the `feat.*` relations
into a single local DuckDB database file (default `~/.mlb/mlb.duckdb`,
overridable by `--db` or `MLB_DUCKDB_PATH`). Features are built there; models
read only from there. There is **no `feat` schema in PostgreSQL**, no migration
creating one, and no PostgreSQL-side as-of retrieval function. The boundary is
at `core`: at or below it is PostgreSQL, above it is DuckDB, and `mlb build` is
the only thing that crosses.

**Context:** The product is a framework distributed as code — the `pybaseball` /
`baseballr` shape, but fuller. A user `pip install`s it, runs `mlb bootstrap`,
and it fetches MLB data from the original sources into *their own* environment.
We ship code, schema, and build logic; the published Hugging Face snapshot is a
convenience, not the product.

That framing separates two layers that had been treated as one:

- `raw` / `core` is a **system of record**. `conform.py` reconciles identities
  across Retrosheet, Lahman, the Chadwick register, the MLB Stats API,
  Polymarket, and Kalshi — cross-source joins, fuzzy team and venue matching, a
  `game_pk` backfill that lands at an ~85% match rate with the remainder held
  `NULL` rather than guessed. That needs constraints, transactions, and a real
  relational engine, and it is not moving.
- `feat.*` is a **derived, reproducible artifact**. It is write-once, read-heavy,
  columnar, single-writer, append-only, and thrown away and rebuilt whenever a
  formula changes. Nothing about it needs what PostgreSQL is good at, and
  everything about it wants what DuckDB is good at.

The root `AGENTS.md` invariant reads "PostgreSQL is the authoritative system of
record" and "preserve the `raw` / `core` / `gold` / `meta` layering unless a
recorded architecture decision changes it." This is that recorded decision.

**Reconciliation with the root invariant — this scopes it, it does not
contradict it.** The invariant exists to stop source data drifting into
unconstrained, unversioned, hand-edited stores where provenance is lost. That
concern applies to *source* data and is fully preserved: every raw record, every
identity resolution, and every provenance and rights annotation still lives in
PostgreSQL under the same rules. A `feat.*` row is not source data — it is a
pure function of `core` plus a versioned formula, carrying its own `created_ts`,
and reproducible from PostgreSQL at any time by re-running `mlb build`. If the
DuckDB file is deleted, nothing is lost. If a `raw` table is deleted, everything
is. That asymmetry is the line the invariant is actually drawing, and this
decision draws it explicitly rather than leaving it implicit. The
`raw` / `core` / `gold` / `meta` layering in PostgreSQL is unchanged; `feat` is a
new layer *outside* it, not a re-arrangement of it.

**Rationale:**

- **The analyst's path becomes real.** The previous plan required the feature
  build to run on both PostgreSQL and DuckDB from a common SQL subset, with a
  parity test forever and every future feature constrained to constructs both
  engines share. One engine, one implementation, no parity test — and DuckDB
  operators that make the point-in-time join a page of code (`ASOF JOIN`) become
  usable instead of forbidden.
- **Redistribution rights stop constraining this layer.** The user fetched the
  source data themselves under their own terms; the features are derived on their
  machine. Rights enforcement stays exactly where it belongs — `export.py`'s
  gate on the optional Hugging Face snapshot, with its existing per-table
  exclusions (`docs/SOURCE_RIGHTS.md`).
- **`gold.game_feature` stays where it is.** It is a ~240-column PostgreSQL table
  carrying 178 registered Engine feature families and feeding the paused
  prediction pipeline; `openspec/project.md` names it a **Phase B** triage
  target. This decision does not re-parent, mirror, or export it. `feat.*` is a
  new, small, public layer that re-expresses a handful of proven *formulas* at
  entity grain — not those families' tables.
- **DuckDB is already adopted tooling** (`openspec/project.md`, "Tooling —
  Adopted") and already a dependency of `packages/mlb-research`. This is not a
  new adoption; it is using an adopted tool for the job it was adopted for.
- **The cost is one more place to look for a number.** Accepted, and bounded by
  a one-sentence boundary rule stated in `openspec/project.md`,
  `docs/FEATURE_STORE.md`, and this ADR.

**Consequences:**

- `duckdb` becomes a runtime dependency of `mlb-baseball`, and `mlb-research`
  becomes a runtime dependency of it rather than a `dev`-extra workspace member
  (the dependency direction is `mlb_baseball` → `mlb_research`, never the
  reverse, so the shipped retrieval API has one implementation).
- Feature build logic is versioned `.sql` in DuckDB dialect, needing a
  dialect-scoped sqlfluff configuration alongside the 97 existing PostgreSQL
  files in `mlb_baseball/sql/`.
- A user can have a stale DuckDB file. Mitigated by `created_ts` on every row and
  by `mlb verify` reporting the build's `created_ts` range.
- Any future work that wants features inside a PostgreSQL query must either join
  across engines or re-derive — deliberately, so that "just add it to
  `gold.game_feature`" stops being the path of least resistance.

**Revisit if:** a concrete requirement appears that genuinely needs features
inside a PostgreSQL transaction (a live serving path writing predictions
transactionally alongside features would be the real case — that is Phase C);
or a feature build outgrows a single machine's memory, at which point the
question is a different engine, not a different layering; or the two-store
boundary is measurably confusing users, evidenced by actual questions rather
than anticipated ones.
