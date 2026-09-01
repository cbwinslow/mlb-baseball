# Deep review — 2026-09-01

Prompted by an external repo overview (GitHub Copilot) that offered three
follow-up analyses:

1. Module-level code-quality review of the two largest modules,
   `mlb_baseball/cli.py` and `mlb_baseball/conform.py`.
2. A library-overlap review — where the code hand-rolls something a mature
   library already does, and whether a swap is warranted.
3. A feature comparison against [baseball.computer](https://baseball.computer).

This document is the result. It is a review and a record, not a new design
decision — anything that changes architecture still goes through
`docs/DECISIONS.md` and Sol gate review. It builds on, and does not replace,
the earlier reviews:

- `docs/PROJECT_REVIEW.md` (2026-08-04) — product/legal/model-lifecycle review.
- `docs/POLICY_REVIEW_2026-08.md` (2026-08-13) — "is this project reinventing
  things the wider world already solved?" Directly relevant to analysis 2.
- `docs/ECOSYSTEM_ASSESSMENT_2026-08.md` (2026-08-24) — tool/dependency
  admission queue.
- `docs/PACKAGE_VALIDATION_STATUS.md` — Plan 06 package tie-out status.

## Bottom line

- **`conform.py` is high-quality.** It is long, but the length is mostly
  evidence: nearly every branch carries a comment tracing it to real
  production data. The only cleanup worth doing is splitting the 1,929-line
  module into a small package, and only when someone is already working in it.
- **`cli.py` has one real problem.** `main()` is a single ~9,000-line
  function with a 171-branch `if/elif args.command == …` chain. About 120 of
  those branches are the Agy "Engine" display commands, each an inline
  ~40-line block of the same shape. This is a maintainability issue, not a
  correctness one, and it is a direct consequence of a decision the project
  already made and is already unwinding (ADR-266, ADR-271). A mechanical,
  behavior-preserving refactor is available.
- **The project is not broadly reinventing wheels.** `docs/POLICY_REVIEW_2026-08.md`
  already reached this conclusion with citations, and nothing here overturns
  it. The hand-rolled pieces (retry, migration runner, concurrency-group
  runner) are small, tested, and each has a recorded reason. The single most
  defensible swap — `tenacity` for `mlb_baseball/net.py` — is not worth doing
  until someone measures that `net.py` is actually costing maintenance time.
- **vs baseball.computer:** this project is a strict superset on data and the
  only project of the two that ships forecasts. baseball.computer does one
  thing this project does not yet do for an outside researcher: hand them a
  documented, queryable database with copy-paste recipes. That gap is already
  the subject of `docs/PRODUCT_DIRECTION.md` "Research database" and the
  research-database-v1 work.

---

## Part 1 — Code quality: `cli.py` and `conform.py`

### 1.1 `mlb_baseball/cli.py` (9,302 lines)

**Structure as it stands.** The module has a handful of small module-level
helpers (`_concurrency_groups`, `_run_group`, `_run_all`,
`_format_metrics_line`, `_run_experiment_command`) and then `main(argv)` —
which runs from line 264 to the end of the file. Inside `main()`:

- ~168 subcommands are declared (176 `.add_parser(...)` calls, a few of
  which are nested under `experiment`).
- Dispatch is a flat `if args.command == "migrate": … elif args.command ==
  "ingest": …` chain — **171 `elif args.command ==` branches** (some commands
  are matched in more than one place).
- Each branch contains the full handler body inline.

**The bulk of the file is the Engine commands.** Roughly 120 of the
subcommands are the Agy analysis engines (`wall-crash`, `arm-align`,
`dp-footwork`, `barrel-grid`, `spin-align`, `polar-compass`, …). Each branch
has the identical shape:

```python
elif args.command == "wall-crash":
    import json as json_lib
    from mlb_baseball.model.wall_crash import (
        OutfielderWallCrashEngine, OutfielderWallCrashMetrics,
    )
    wcr_eng = OutfielderWallCrashEngine()
    wcr_m = OutfielderWallCrashMetrics("f1", "Target Fielder",
        position=args.pos, wall_hazard_catch_pct=args.catch, ...)
    wcr_res = wcr_eng.evaluate_wall_crash(wcr_m)
    if args.json:
        print(json_lib.dumps({...}, indent=2))
    else:
        print(...)  # ~15 lines of formatted print()
```

Parse args → build a `*Metrics` dataclass → call `*Engine().evaluate_*()` →
print human-readable or `--json`. Per `docs/PACKAGE_VALIDATION_STATUS.md`,
these commands "only take hand-entered CLI arguments (no real data path exists
yet)."

**Why this matters.**

- `main()`'s cyclomatic complexity is enormous. `ruff` is configured for
  `E, F, I, UP, B` (`pyproject.toml`) — it does not flag function complexity
  (`C901`) or branch count, so this is invisible to CI.
- The `argparse` setup, the dispatch, and every handler body share one
  namespace and one function. A typo in one engine branch is a syntax error
  for the whole CLI.
- `CLAUDE.md` requires "A new CLI subcommand needs its own CLI-dispatch-level
  test (through `cli.main([...])` and real argparse …)". With ~168
  subcommands in one function it is hard to see at a glance which ones have
  that test and which do not.

**Why this is not a surprise.** It is the tail of a decision the project has
already reversed:

> **Freeze.** No new Engine packages, no `FEATURE_COLUMNS` expansion, no Plan
> 05 Astro, no more unpromoted SQLMesh models.
> — `docs/DECISIONS.md` ADR-271

> Agy Engine packages (ADR-089–258) are a wiring backlog, not trash and not
> 110 new GBM columns. Default is WIRE the raw components … Invented
> composites stay display-only until constants are cited or fit. Stop adding
> new Engine packages.
> — `docs/DECISIONS.md` ADR-266

And it runs against the standing preference recorded in memory: *don't add new
`mlb` subcommands/wrappers unless an outside user needs them; keep the surface
streamlined.*

**Cheapest fixes first (all behavior-preserving):**

1. **Dispatch table.** Replace the `if/elif` chain with
   `COMMANDS: dict[str, Callable[[argparse.Namespace, psycopg.Connection], None]]`
   and `COMMANDS[args.command](args, conn)`. Each handler body moves to a
   named function. `main()` shrinks to "build parser, parse, dispatch". This
   is mechanical and testable — and it makes the `CLAUDE.md` per-command
   dispatch test trivial to write for each handler.
2. **One generic handler for the Engine commands.** The ~120 engine branches
   differ only in: the `Engine`/`Metrics` classes, the mapping from `args.*`
   to `Metrics` fields, and the output field list. That is a small data
   table, not 120 code blocks. This is the case `CLAUDE.md` explicitly allows
   structure for — "a real, current need, not a hypothetical one … small
   composable pieces, clear interfaces". The engine subparsers can be built
   from the same table.
3. **Split the file.** Once handlers are functions, move them into a `cli/`
   subpackage (`cli/core.py`, `cli/engines.py`, `cli/research.py`) with the
   dispatch table assembled in `cli/__init__.py`.

**Bigger question, gated (not a code cleanup — a product call):** if the
Engine-wiring backlog (ADR-266 item 3) resolves toward "most of these stay
display-only indefinitely", it is worth asking whether ~120 top-level `mlb`
subcommands should exist at all, versus one `mlb engine <name> …` with a
registry. That is downstream of the freeze decision, not something to do
now.

**Before starting any of this:** confirm with the owner that refactoring
frozen code is in bounds. ADR-271's freeze language is strict; steps 1–3 add
no features and no engines, but they are still work on frozen surface area.

### 1.2 `mlb_baseball/conform.py` (1,929 lines)

**This module is in good shape.** Observations, strongest first:

- **The length is mostly evidence, and that is a feature.** Example: the
  `core.game` insert guards four different raw-text anomalies
  (`"12000.0"`, `"6500?"`, `"<1000"`, `"-1.0"`) and the comment names each
  one and says it was "confirmed" against real `raw.retrosheet_gameinfo`.
  The `game_type` letter→word mapping cites the specific dated game that
  proved each letter (`F` = 2025-09-30 Wild Card). This is exactly the
  "quote rules, don't paraphrase" / "separate observation from
  recommendation" discipline `CLAUDE.md` asks for, applied to data.
- **Honest NULLs throughout.** Pitcher FKs left NULL rather than
  string-matched; `game_pk` left NULL below the ~85% confirmed match rate;
  market `implied_probability` NULL when no pre-game snapshot exists (and the
  docstring explains that using the settled price would leak the outcome into
  a Phase 2 model). This is the project's research contract working as
  intended.
- **It has a `health_check()`** using the shared `check_*` helpers, per
  `CLAUDE.md` "Operational health checks".

**Minor cleanups (low urgency, no behavior risk):**

- **Module could be a package.** 1,929 lines / ~30 functions split cleanly by
  concern: identity (`_build_teams/_players/_team_aliases`), games +
  `game_pk` backfill family, plays/pitches, market
  (`_polymarket_*`/`_kalshi_*`/`_build_market`), standings/WAR. A `conform/`
  package with `run()` in `__init__.py` would make each concern independently
  readable. Worth doing **only when someone is already substantially editing
  the file** — not as a standalone change.
- **`run()` encodes step ordering in prose.** The orchestrator runs ~20
  ordered steps, and several ordering constraints ("must run before
  `_build_games`", "must run after both backfills above") live only in
  comments. A list of `(step_fn, depends_on)` that `run()` executes would
  make the ordering machine-checkable. This is an observation, not a
  recommendation — the comments are thorough and
  `tests/integration/test_conform*.py` covers the pipeline. Only worth it if
  the ordering ever actually causes a bug.
- **Inline SQL strings.** This is settled policy, not a finding:

  > current policy (`docs/SQL_OWNERSHIP.md`) is correct, not behind the
  > field. dbt, SQLMesh, and the `aiosql`/`yesql` line of Python libraries
  > all independently draw the same line this project already draws.
  > — `docs/POLICY_REVIEW_2026-08.md`

  `conform.py`'s Python-side Polymarket/Kalshi matching is likewise
  justified in the docstring (the source data is `repr()`'d dicts in text
  columns; `ast.literal_eval` in Python beats string-matching repr output in
  SQL).

---

## Part 2 — Library overlap

### The prior conclusion still holds

`docs/POLICY_REVIEW_2026-08.md` already ran "six independent research passes,
each with real citations" against exactly this question. Its verdict: the
project's conventions (SQL organization, hand-rolled small helpers) are in
line with outside practice, and the real gap it found was *missing
enforcement* (fixed by adding SQLFluff to CI), not misplaced effort.
`docs/ECOSYSTEM_ASSESSMENT_2026-08.md` separately decided **not** to add
dbt, Airflow, Dagster, a second warehouse, or a second transform runtime.

Nothing in this pass overturns either. Component by component:

| Area | Code | Mature library | Assessment |
| --- | --- | --- | --- |
| **Pipeline orchestration** | `cli.py::_run_all` / `_concurrency_groups` / `_run_group` (~150 lines, ADR-031), `pipeline.py` (328 lines) | Airflow, Dagster, Prefect | **Keep.** Already rejected (`ECOSYSTEM_ASSESSMENT`). There is no scheduler need — `cron` + `mlb daily`. The concurrency-group runner exists to avoid ADR-005's thread-deadlock and is that specific. No measured pain. |
| **Cross-source transforms** | `conform.py` + `mlb_baseball/sql/*.sql` (~85 files) | SQLMesh, dbt | **Already delegated, with a deliberate boundary.** SQLMesh is adopted for incremental gold (ADR-088, `transforms/`). Identity resolution, Elo, Markov sim, and training stay in Python by explicit decision: "SQLMesh still does not own identity, Elo, Markov simulation, or training" (ADR-271). Correct — baseball.computer can be 100% SQLMesh because it has no cross-source identity problem. |
| **HTTP retry** | `net.py` (`get_with_retry`, `call_with_retry`, 127 lines, ADR-007) | `tenacity`, `urllib3.util.Retry` | **The one genuine candidate — but not yet.** See below. |
| **Bulk load to Postgres** | `load.py::_copy_dataframe` uses psycopg 3 native `cur.copy()` | `pgcopy`, `pandas.to_sql` | **No action.** `cur.copy()` *is* the correct primitive. `to_sql` would be slower; `pgcopy` adds a dep for no gain. |
| **DataFrame → table DDL** | `load.py::_ensure_table_and_columns` (schema inferred from the DataFrame) | `pandera` (validation only), SQLAlchemy | **Keep.** Deliberate for the ~27 Lahman tables where hand-authoring migrations is impractical (documented in the module docstring and `ARCHITECTURE.md`). `pandera` validates, it does not emit DDL. |
| **Migration runner** | `migrate.py` (151 lines) — forward-only, advisory-locked, non-transactional-DDL aware; 90+ plain `.sql` files | Alembic, `yoyo-migrations`, Sqitch | **Keep for now.** Alembic is built around Python migration scripts (overkill for pure SQL DDL). `yoyo-migrations` is the closest fit for "a directory of `.sql` files". No measured pain; idempotency is tested (`tests/integration/test_migrations.py`). Revisit only if migration management becomes a real cost. |
| **Model metrics / calibration** | `model/` + `scripts/verify_markov_calibration.py` | scikit-learn | **Already delegated.** `scikit-learn` is a direct dependency and is used for `log_loss` / Brier / calibration. Good. |
| **Config** | `config.py` (190 lines) — TOML + env | `pydantic-settings`, `dynaconf` | **Minor.** 190 lines, works, tested. A swap is cosmetic. Not worth it. |

### `net.py` and `tenacity` — the honest version

`net.py` does have a real analogue: `tenacity` is the standard Python retry
library, and `net.py`'s core (exponential backoff, max attempts, retry on a
set of exceptions) maps onto `@retry(stop=stop_after_attempt, wait=wait_exponential, retry=retry_if_exception_type)`.

But `CLAUDE.md` is explicit:

> **Measure before you propose.** A timing, a profile, an `EXPLAIN`, a row
> count, a check of whether the code path has even run in production. … If
> you haven't measured, say "I'd need to measure X first" instead of putting
> the rewrite on the table.

> **A rewrite is the last option, not one of four.** List the cheap, local
> fixes first.

What I would need to measure before recommending the swap: is `net.py`
actually costing maintenance time? (Its git history, bug count, and how often
someone has to touch it.) Right now the evidence points the other way —
`net.py` is ~130 lines, has a focused test suite, and carries behavior that a
naive `tenacity` config would lose:

- non-transient 4xx is **never** retried regardless of `max_attempts` (ADR-007
  found this burned the full backoff budget on permanently-404ing games);
- a numeric `Retry-After` header is honored but only when bounded
  (`max_retry_after_seconds`);
- the retryable set is exactly `{408, 425, 429}` ∪ `5xx`.

All of that is reproducible in `tenacity` with a custom `wait` callable and
`retry_if_exception`, but it is not the default, so the swap is not "delete
130 lines" — it is "rewrite 130 lines against a new API and re-verify every
ADR-007 behavior". **Recommendation: leave it. Add `tenacity` only if a
future change to retry behavior is needed *and* someone confirms the
hand-rolled version is the thing making that change hard.**

---

## Part 3 — vs baseball.computer

### What baseball.computer is

An open **historical** baseball database. A Rust parser turns Retrosheet
files into ~45 parquet files; SQLMesh models build a DuckDB database
(`bc.db`); pre-1901 player stats come from Lahman. Users query it through a
browser query engine, or from Python/R with notebook examples, or directly
against the parquet/DuckDB files. Three documented model layers — box-score,
event, seasonal — with per-column documentation at `docs.baseball.computer`.
No predictions, no forecasts, no live data, no markets, no API beyond the
queryable database. Free; Retrosheet's required attribution plus a Creative
Commons ShareAlike term on the project's own content (check the current
license before reuse).

(baseball.computer recently moved from dbt to SQLMesh-native. That is a
useful reference for what a fully-SQLMesh gold layer looks like as this
project's own incremental SQLMesh adoption continues — not a reason to change
the `conform.py`/`.sql`/SQLMesh boundary set in ADR-266/271.)

### Side by side

| Dimension | baseball.computer | This project |
| --- | --- | --- |
| **Data sources** | Retrosheet + Lahman (pre-1901) | Retrosheet + **Statcast** + **live MLB StatsAPI** + BRef WAR + Lahman + Chadwick + **Kalshi + Polymarket** + RSS |
| **Coverage** | Retrosheet history | Retrosheet events 1910–2025, Statcast pitches 2008–2026, live 2026; ~227k conformed games / 16.5M events / 13.4M pitches (per `PROJECT_REVIEW.md`, 2026-08) |
| **Warehouse** | DuckDB (file) | PostgreSQL, `raw`/`core`/`gold`/`meta` layers, 90+ migrations |
| **Build stack** | Rust parser → parquet → SQLMesh → DuckDB | Python connectors → `raw` (COPY) → `conform.py` → `.sql` builders + SQLMesh spike |
| **Cross-source identity** | Not needed (single source) | `game_pk` backfill, team-alias crosswalk, Chadwick register — real, hard, and done |
| **Forecasts** | None | Elo, log5, Markov / Monte-Carlo game sim, GBM; calibration + evaluation; model-vs-market tracking |
| **Point-in-time discipline** | N/A | `gold.game_feature`, feature/data/model cutoffs on every prediction row |
| **Researcher access** | **Browser query engine, notebook recipes, per-table grain + column docs** | `mlb dump` + `RESEARCH_QUERY_RUNBOOK.md` **planned**; `gold.player_season`/`team_season` exist (ADR-057) but reporting/doctor wiring unfinished |
| **License / rights** | Retrosheet attribution + CC BY-SA, clean | AGPL-3.0 code; data rights gated by profile (`public_safe` / `licensed_full` / `local_research`); Statcast + BRef terms are real public-launch blockers (`PROJECT_REVIEW.md` finding 1) |

### Gaps and quick wins

The project already names these in `docs/PRODUCT_DIRECTION.md` ("Research
database (better than baseball.computer / baseballr)"). Ranked by
external value:

1. **Public query access.** baseball.computer's single biggest UX advantage
   is "open a browser, run SQL, or copy a notebook cell." This project's
   equivalent (`mlb dump` of the `public_safe` profile + 2–3 notebook
   recipes in `RESEARCH_QUERY_RUNBOOK.md`) is designed but unshipped.
   Highest-leverage item. *Do not dump Statcast in a `public_safe` profile*
   (`PRODUCT_DIRECTION.md`).
2. **Stable, documented per-table grain for outsiders.** `docs/TABLE_CONTRACTS.md`
   and `docs/DATA_DICTIONARY.md` exist; surface them the way
   `docs.baseball.computer` surfaces its column docs.
3. **Finish the public-safe marts.** `gold.player_season` / `team_season`
   exist but `mlb report` / doctor checks were unwired when ADR-057 landed
   (`PRODUCT_DIRECTION.md` item 1). Add Retrosheet-only RE24 / wOBA / FIP /
   wSB at player-season and player-game grain.

### Differentiators to lean into

Things baseball.computer will not have, by design: pitch-level Statcast, live
current-day data, prediction-market probabilities as a free market proxy, and
actual calibrated forecasts with a track record. `docs/NORTH_STAR.md` already
frames the project around these. There is no material feature baseball.computer
has that this project lacks *except* researcher-facing packaging — which is a
known, planned work item, not a design gap.

---

## Recommendations (evidence-gated, cheapest first)

| # | Action | Cost | Risk | Gate |
| --- | --- | --- | --- | --- |
| 1 | `cli.py`: replace the `if/elif` chain with a `COMMANDS` dispatch dict; move handler bodies to named functions | Low, mechanical | Low (behavior-preserving) | Confirm with owner that refactoring frozen surface is in bounds (ADR-271) |
| 2 | `cli.py`: collapse the ~120 Engine branches to one table-driven generic handler + table-driven subparsers | Low–medium | Low | Same as #1 |
| 3 | Add `C901` / branch-count lint (or a targeted check) so a 9,000-line function can't recur silently | Low | None | — |
| 4 | Finish research-DB packaging: `public_safe` dump + notebook recipes + surfaced per-table docs (`PRODUCT_DIRECTION.md`) | Medium | Low | Already planned; highest external value |
| 5 | `conform.py`: split into a `conform/` package by concern | Low | Low | Only when already editing the file substantially |
| 6 | Library swaps (`tenacity`, `yoyo`, `pydantic-settings`) | — | — | **None recommended now.** Revisit `tenacity` only if retry behavior needs to change *and* the hand-rolled version is measured to be what makes that hard |

Items 1–3 address the one real code-quality finding. Item 4 addresses the one
real competitive gap. Everything else is either already decided or not worth a
dedicated change.

---

*Method: read `cli.py`, `conform.py`, `net.py`, `load.py`, `migrate.py`,
`pyproject.toml`, the `mlb_baseball/sql/` and `migrations/` listings, and the
existing review docs; fetched baseball.computer's site, GitHub repo, and docs
site. No code was changed. Consistent with `docs/KNOWLEDGE_BASE.md`,
baseball.computer was treated as reference-only — its method and structure
informed this comparison; no data, SQL, or text from it was copied.*
