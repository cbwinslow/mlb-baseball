# Design review — how v1.1 got to this shape

Written 2026-09-09, after two reviews and an owner decision. This file exists so
the next reader does not re-open settled questions, and can see at a glance
which questions are actually still open.

## What the two prior reviews concluded

**Review 1 — the 2026-09-04 modeling / backtesting / feature-store / real-time
planning session** (`docs/research/2026-09-04-modeling-and-realtime-plan.md`,
filed as commit `c86b51e`; named in `openspec/project.md` as design input, "not
a contract"):

- Keep PostgreSQL as the canonical operational and integration database —
  identity resolution, normalized entities, ingestion state, provenance — but
  **do not distribute PostgreSQL**.
- The distribution layer is Parquet plus DuckDB: a researcher downloads only what
  they need, queries locally, and never bootstraps a multi-gigabyte server.
- The external product is a **research kit**, not a database dump: versioned,
  documented, research-ready marts with definitions, lineage, grain, assumptions
  and tests.
- Feature packages are strictly point-in-time and named per grain
  (`features_team_form_30d_v1` and the like). "Never let a feature table quietly
  blend postgame data with pregame information."
- Do not build a public API first. Parquet exports, then a DuckDB loader and
  Python package, then in-browser querying — an API only once you know what
  people ask for.
- Start with proven baselines; the target is a well-calibrated probability, not
  accuracy.

**Review 2 — the task-1.1 audit of the first cut** (commit `7faf584`, which
revised the original proposal in place):

- `gold.game_feature` is ~240 columns grown over ~242 `ALTER TABLE … ADD COLUMN`
  migrations, carrying **178** registered feature families
  (`docs/FEATURE_REGISTRY.md`) and read across `export.py`, `live.py`,
  `pipeline.py`, `conform.py`, `audit.py`, `rehearsal.py`, `field_census.py`,
  `research.py`, `cli.py`.
- It is explicitly the "~110 Engine composite packages" that `openspec/project.md`
  marks for **Phase B** triage — SPECULATIVE and gated.
- Therefore the owner-approved "rebuild `gold.game_feature` from `feat.*`" is a
  Phase-B-sized job with blast radius across the paused prediction pipeline, and
  was cut from the v1.1 slice. `feat.*` became a standalone public layer that
  reuses proven *formulas*, not tables.
- The walk-forward harness already exists and works (`model/experiment.py`:
  `folds()`, `_common_rows()`, `_calibration()`, `_metrics()`, Elo already wired
  as a baseline family). The gap was never "build a harness" — it was that none
  of it is packaged for an outside researcher, and there is no entity-grain
  feature layer, no Elo v2, and no model card.

## What the owner settled (2026-09-09)

These are decided. They are written up in `proposal.md` and `design.md`; this is
the index, not the argument.

1. **The product is a framework distributed as code** (`pybaseball` / `baseballr`
   shape, fuller). Users bootstrap the data into their own environment. We ship
   code, schema, and build logic.
2. **Redistribution rights therefore do not constrain the feature or model
   layer** — only the optional `mlb export` → Hugging Face snapshot, which keeps
   its existing per-table exclusions.
3. **No Feast.** Build Feast's signature and vocabulary
   (`get_historical_features`, `"view:feature"` refs, one row out per row in,
   missing stays missing) over a single DuckDB `ASOF JOIN`. Adoption trigger
   recorded: a real user asks; it is roughly a one-day add then, because the
   relations are already the right shape.
4. **Hybrid database, hard boundary at `core`.** PostgreSQL keeps `raw` and
   `core` unchanged; the feature and model layer is DuckDB-only, in one local
   file. Recorded as an ADR (`adr-features-in-duckdb.md`) because it scopes the
   root invariant.
5. **Three commands as the front door:** `mlb bootstrap`, `mlb build`,
   `mlb verify` — compositions over the existing commands, nothing renamed or
   removed.
6. **Windows are columns, never rows**, and every rate ships with its numerator
   and its exposure denominator so a user can re-derive PA/BF-based windows.
   (This reverses the first cut, whose primary key included `window`.)
7. **Four clocks:** `event_ts`, `available_ts`, `created_ts`, plus the decision
   time supplied at retrieval. Append-only; a formula change is a new
   `feature_version`.
8. **`gold.game_feature` is left alone and is never part of the public or DuckDB
   surface.** Re-parenting it is explicitly not this work.
9. **Two leakage checks ship, not four.** Keep the two that test the store and
   need no model (visibility enforcement; the doubleheader / same-day case). The
   label-shuffle and injected-outcome checks are model diagnostics and move to a
   notebook recipe.
10. **The `delivery` requirement is relaxed** from a mandated implementation to
    the guarantee it was trying to express, keeping every scenario that tests
    that guarantee.
11. **Invert the dependency direction:** `mlb_baseball` depends on
    `mlb_research`, never the reverse. One retrieval implementation, one harness
    (slice 2), both products.

Two refinements were made while writing this up, both flagged rather than
assumed:

- **The delivery-spec relaxation moved from slice 3 into slice 1.** Without it,
  slice 1 ships a store that knowingly violates the live requirement's mandated
  implementation (no registry YAML, two checks not a battery), and a reviewer
  cannot distinguish that from a defect.
- **The dependency inversion moved from slice 2 into slice 1.** `mlb verify`
  must call the same shipped retrieval API an outside analyst calls; otherwise
  slice 1 ships two retrieval paths. Slice 2 then only moves the harness across a
  direction that already exists.

## Still genuinely open

Four. Each is answerable during implementation from the code plus a one-line
owner confirmation; none changes the specs, the approach, or the task list.
Task 1.1 records the answers here before task 2.1 starts.

### 1. The DuckDB file location and its resolver

**Recommendation:** `--db <path>` beats `MLB_DUCKDB_PATH` beats
`~/.mlb/mlb.duckdb`, with the parent directory created on first build.

**Open:** whether the default should honour `XDG_DATA_HOME`
(`~/.local/share/mlb/mlb.duckdb`) instead of a dotdir; whether the env var
should be `MLB_DUCKDB_PATH` or fold into the existing `MLB_*` configuration
conventions in `mlb_baseball/config.py`; and whether one file per
`feature_version` is wanted or one file holding all versions (the append-only
rule works either way).

### 2. Does `mlb build` wrap or eventually replace `report` / `conform` / `features`?

**Recommendation for now:** wrap. `mlb build` composes
`migrate` → `conform` → `report` → feature build, and all four keep working
standalone. There are 171 top-level subcommands with crons
(`scripts/mlb_daily_update.sh`, `mlb_api_update.sh`, `mlb_odds_update.sh`) and
runbooks behind them.

**Open:** whether `report` and `features` should eventually become internal steps
with no public subcommand; and the same question for `mlb verify` versus
`mlb doctor` / `mlb audit` / `mlb preflight`, which overlap it. A deprecation
path is a later change either way — but the answer determines whether the docs
present `build` and `verify` as *the* interface or as *an* interface.

### 3. Which day-based window sizes ship

**Recommendation:** `7d`, `30d`, and season-to-date (`std`) — three windows, not
four, since `14d` is closely correlated with both neighbours and every extra
window is three more columns per rate (rate, numerator, exposure).

**Open:** whether `14d` earns its place; whether pitchers want a start-count
window (`last 3 starts`) rather than a day window, given that a starter's
30 days may contain four starts or one; and whether `std` should reset at the
season boundary only, or also carry a documented carry-over for early-season
rows where the denominator is tiny.

### 4. How `feat.game` curates its ~30–40 columns

**Recommendation:** curate by *what the reference baseline and the first notebook
actually consume*, not by re-ranking the 178 Engine families — home and away
team form (wOBA, K%, BB% at each window), both probable starters' form (K−BB%,
FIP-like rate, batters faced), plus game context (ids, teams, venue, first pitch,
the four clocks). Anything a consumer does not read does not ship.

**Open:** whether "what the baseline consumes" is too narrow a rule for a
relation meant to be a general starting point; whether the eight or so classical
families (`team_offense_v1`, `starter_prior_v1`, `plate_discipline_v1`,
`bullpen_v1`) should each contribute a fixed quota; and whether bullpen form
belongs in v1 of `feat.game` at all, given that it needs a third form relation
this slice does not build.
