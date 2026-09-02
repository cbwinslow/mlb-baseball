# Dependency audit — hand-rolled code vs. established libraries / PG extensions

Date: 2026-09-02
Scope: `mlb_baseball/`, `scripts/`, `migrations/`, `tests/conftest.py`.
Output is a **candidate list only** — no code changes proposed here.

---

## 0. Read this first: two prior reviews already cover most of the surface

This is not virgin ground. The repo has two thorough, source-cited assessments:

- **`docs/POLICY_REVIEW_2026-08.md`** (2026-08-13) — six research passes explicitly
  asking "is this project reinventing things the wider world has solved?" Covered
  SQL-in-strings, Postgres-vs-OLAP, migrations-vs-Alembic, PIT design,
  testing/data-quality frameworks (Great Expectations / Pandera / Soda), MLB prior art.
- **`docs/ECOSYSTEM_ASSESSMENT_2026-08.md`** (2026-08-24) — a candidate inventory with
  per-item adoption gates: Pandera, Polars, PyMC, MLflow, dbt, Airflow/Dagster/Prefect,
  and a PostgreSQL-extension table (pg_trgm, TimescaleDB, pgvector, pg_cron, PostGIS, pgTAP…).
- **`docs/DECISIONS.md` ADR-043** — direct evaluation of the ~70 cluster extensions.
- **`docs/ARCHITECTURE.md` "Extensions"** — the standing per-extension position.

Verbatim standing verdicts worth keeping in view:

- SQL organization: *"current policy (`docs/SQL_OWNERSHIP.md`) is correct, not behind the field."*
- Migrations: *"keep as-is … the same recognized pattern used by Flyway, golang-migrate, dbmate, and Rails."*
- Data-quality frameworks: *"`mlb_baseball/health.py` already hand-implements … every substantive category dbt tests/Great Expectations/Soda/Pandera are sold on … every one of those checks was demonstrably built in response to a real bug."*
- Testing: real disposable Postgres, no DB mocking — *"matches recognized good practice, no gap."*
- `pg_trgm`: *"Available for ad-hoc research; do not add to conformance."*
- TimescaleDB: *"Declined for now."* Revisit gate: *"Repeated representative time-range workload failures after normal partitions/indexes/materialized gold tables are optimized."*
- `pg_cron`: *"Declined."* Revisit gate: *"A demonstrated coordination requirement that cron + `flock` and advisory locks cannot meet."*
- `pgvector`: *"Defer. A named, rights-approved embedding feature and a similarity-search consumer."*

**So the value in this audit is the handful of areas those two reviews did *not* examine**,
plus one or two where a documented revisit gate may now be closer to met.

---

## Candidate table (ranked by value ÷ risk, best first)

| # | Area | What we do now | Candidate | Maint. health | Effort | Risk | Clear win? | Benchmark needed first? |
|---|------|----------------|-----------|---------------|--------|------|-----------|------------------------|
| 1 | Ingestion error visibility | `print()` everywhere (~1000 call sites); only ~12 modules use `logging`. Connector failures print to stdout (`bref.py:156`, `load.py`, `mlb_api.py`). | stdlib `logging` (no new dep); optionally `structlog` for JSON | `logging` = stdlib; `structlog` very healthy, ~monthly releases | M (mechanical, wide) | L | **yes** (stdlib logging); maybe (structlog) | No |
| 2 | HTTP connection reuse | Each connector calls bare `requests.get(..., timeout=30)` — no shared `Session`, no keep-alive/pooling. Only `mlb_api.py:1367` uses a thread-local `Session`. | `requests.Session` (already a dep) shared per connector | requests = stable/ubiquitous | S | L | maybe | Yes — measure round-trip savings on a real Retrosheet/Statcast bootstrap |
| 3 | HTTP retry / backoff | `mlb_baseball/net.py` (128 lines): `get_with_retry` + `call_with_retry`, Retry-After honoring, non-retryable-4xx skip, bounded backoff. Battle-tested (ADR-007). | `tenacity` or `stamina` (Hynek Schlawack, wraps tenacity with sane defaults); or `urllib3.util.Retry` on a `Session` | tenacity very healthy; stamina healthy/opinionated | S–M | M | **no** — working, tested, nuanced; swap is a maintainability call, not a fix | No, but a swap must re-prove the 4xx-skip and Retry-After behaviors under test |
| 4 | Mojibake repair | `bref.py:104 _repair_name_mojibake` — reverses pybaseball's `str(bytes)` repr bug via `latin1/unicode_escape` round-trip. ~9% of names/season. | `ftfy` (`ftfy.fix_text` / `ftfy.fixes.decode_escapes`) | ftfy very healthy, widely used | S | L–M | maybe | **Yes** — run ftfy against the real affected `raw.bref_batting`/`raw.bref_pitching` names and diff vs. the current 6-liner; ftfy's default pipeline may not target this exact repr artifact |
| 5 | Config loading | `mlb_baseball/config.py` (191 lines): TOML + `MLB_*` env overrides, per-field range validation, `ConfigError`. | `pydantic-settings` | very healthy (Pydantic org) | M | L–M | **no** — current code is explicit, tested, dependency-light; only worth it if config keeps growing | No |
| 6 | DataFrame schema/drift checks at raw boundary | `mlb_baseball/load.py`: `_check_schema_drift`, `SchemaDriftWarning/Error`, `_pg_column_name` sanitizing, added-column `ALTER TABLE`. | `pandera` (already flagged: *"Narrow evaluation … Trial one source"*) | healthy (Union.ai) | M | L | maybe (narrow) | Yes — the assessment already asks for a one-source trial with a failure/reporting comparison |
| 7 | SQL statement splitting in migrations | `migrate.py:_strip_sql_comments` + naive `sql.split(";")` (no string-literal awareness — documented limitation). | `sqlglot` (parse/split) or `sqlparse` | sqlglot very healthy; sqlparse stable/low-activity | S | L–M | maybe | No — but low value; current DDL never puts `;` in a string literal |
| 8 | Season partition management | `migrations/0011` hand-rolls 165 partitions in a `DO` loop (1871–2035); `0026` trims empty future ones. No ongoing automation. | `pg_partman` | healthy (Crunchy Data) | M | M | **no** — partitions are annual-cadence and pre-created to 2035; `DEFAULT` partition catches strays; pg_partman adds a bgworker + extension dependency for near-zero recurring work | No (operational-burden judgment, not perf) |
| 9 | Player similarity / nearest-neighbour | `model/cluster.py:96 find_pitcher_comps` — pure-Python weighted-Euclidean scan over a passed candidate list. | `pgvector` (hnsw/ivfflat index) — or `scikit-learn` `NearestNeighbors` (already a dep) | pgvector very healthy | M (pgvector) / S (sklearn) | M / L | maybe | **Yes** — measure the candidate-library size and call frequency; if it's a few hundred rows called rarely, neither is worth it. `pgvector` still gated by the ADR ("named, rights-approved consumer") |
| 10 | CLI structure | `mlb_baseball/cli.py` — **9302 lines, 176 `add_parser` calls**, roughly one subcommand per `model/` module. | Not a library swap. `click`/`typer` wouldn't shrink it. The real fix is a **registry/dispatch table** for the model subcommands. | n/a | L | M–H | **no** for a framework swap; maybe for internal decomposition | No — but see `mlb_baseball/CLAUDE.md` ("supported facades during staged decomposition; do not rewrite wholesale") and MEMORY "No one-off CLI commands" |
| 11 | HTTP response caching | `manifest.py` hand-rolls a sha256 content-cache for downloads + provenance/status ledger. | `requests-cache` | healthy | M | M | **no** — manifest does replay/provenance/resume, not just caching; requests-cache replaces only the smallest part | No |
| 12 | Progress bars | `progress_table.py` (545 lines) — already wraps `rich.progress` behind `Protocol`s. | already using `rich` | rich very healthy | — | — | **no gap** | — |
| 13 | Test DB lifecycle | `tests/conftest.py` — already on `pytest-postgresql` `postgresql_noproc`; `pytest-split` present. Custom bits (`_speed_up_test_database` UNLOGGED partitions, per-process high-entropy DB name) are genuinely project-specific. | already adopted | pytest-postgresql healthy | — | — | **no gap** | — |
| 14 | Date / season ranges | `config.py` season-bounds validation; `model/season.py` etc. use stdlib `date`/`datetime`. `dateutil` already transitively present (pandas). | stdlib is fine | — | — | — | **no gap** | — |

---

## PostgreSQL extensions — per-item, tied to a concrete problem in THIS repo

Cluster already has available (per ADR-043 / ARCHITECTURE.md): PostGIS, Apache AGE,
pgvector, TimescaleDB, pg_trgm, pg_cron, btree_gist. `pg_stat_statements` is enabled.
TimescaleDB was evaluated and declined.

| Extension | Concrete problem here | Position / recommendation |
|-----------|----------------------|---------------------------|
| **pg_partman** | `migrations/0011` DO-loop of 165 season partitions on `core.play`/`core.pitch`; future partitions and any retention are manual. | Low value. Annual cadence, pre-created to 2035, `DEFAULT` partition is the safety net. Adopt only if partition churn becomes real (e.g. switch to monthly/weekly grain). No benchmark needed — this is operational-burden judgment. |
| **pg_trgm** | `bref._repair_name_mojibake` residue + `mlb player-id` crosswalk is exact-match only; `conform.py` venue/team resolution is exact-name-join and *deliberately* leaves misses NULL (ADR-029). Research users can't do "players named like X". | Keep the standing verdict: **not in conformance**. A single GIN trigram index on `core.player(last_name)` for the `mlb player-id` / research path is a small, self-contained win if a user actually asks. Effort S, Risk L. Pairs with `unaccent`. |
| **unaccent** | Accented-name search/joins (José vs Jose) for research queries. | Only alongside a pg_trgm research index. Not for the pipeline. Effort S, Risk L, value L. |
| **pgvector** | `model/cluster.py` nearest-neighbour pitcher comps in pure Python; `model/neural.py`, cluster archetypes. | Gated by ADR: needs "a named, rights-approved embedding feature and a similarity-search consumer." `cluster.py` is a *candidate* consumer — measure its working-set size first (see row 9). Until then: defer. |
| **pg_duckdb / duckdb_fdw** | Prior review: *"if this project's own stated revisit gate ever fires, evaluate DuckDB attached directly to the existing Postgres instance … before ClickHouse."* Heavy `conform`/`report`/gold rebuilds; `db.py` already bumps `work_mem` to 1GB for batch jobs on spinning HDDs. | **Needs a benchmark and the gate is not met.** No measured Postgres analytical-performance problem exists (`docs/CLICKHOUSE_DECISION.md`: 13.4M rows, well below the degradation point). Flag: if `mlb conform`/`report` wall-time becomes a complaint, benchmark DuckDB's `postgres` scanner on the heaviest gold build before anything else. |
| **pg_cron** | CRON-01 daemon + two system crontab jobs (`mlb_api_update.sh` 5-min, `mlb_daily_update.sh` daily), guarded by `flock`. | **Declined** stands. The jobs run app-level Python, not SQL; cron + `flock` + advisory locks meet the need. Revisit only on "a demonstrated coordination requirement cron cannot meet." |
| **hll** (HyperLogLog) | `mlb inventory` approximate row counts. | Not needed — already uses `pg_class.reltuples` estimates; no high-cardinality distinct-count query in the codebase. |
| **tablefunc** (crosstab) | Any pivot in `serve.*`/gold views. | Low priority — existing pivots use `COUNT(*) FILTER (WHERE …)`, which is clearer and needs no extension. |
| **hypopg** | Future index-tuning work (`migrations/0086`, `0090`, `0092` are all index-tuning migrations from `pg_stat_statements` evidence). | Already the standing position: session-local DBA aid, install when doing a real index-tuning pass, no standing dependency. |
| **pgstattuple / pageinspect / pg_buffercache / amcheck** | Ad-hoc bloat/corruption/cache investigation. | Standing position holds: ad-hoc toolbox, not a dependency or health check. |
| **pgTAP** | Already adopted narrowly (`tests/pgtap/log5.pg`). | No change. |

---

## Which candidates need a measurement before adoption (per the repo's "measure first" rule)

Quoting `mlb_baseball/AGENTS.md`: *"Measure before performance rewrites. GPU/vectorization/JIT/parallelism must have a demonstrated workload and benchmark."*
And root `CLAUDE.md`: *"A rewrite … none of these reach the owner without evidence first."*

- **Row 2 (requests.Session)** — measure bootstrap wall-time with/without keep-alive.
- **Row 4 (ftfy)** — diff ftfy output vs. the current repair on real affected names.
- **Row 6 (Pandera)** — one-source trial with failure/reporting comparison (already the assessment's stated gate).
- **Row 9 / pgvector (cluster.py)** — measure candidate-library size and call frequency.
- **pg_duckdb** — benchmark the heaviest gold/`conform` build; gate not currently met.

Candidates that are **judgment calls, not measurements** (no benchmark needed, but also not slam-dunks):
- Row 1 (logging) — a CLAUDE.md-compliance argument ("failures … logged with enough context"), not a perf claim.
- Row 3 (tenacity), Row 5 (pydantic-settings), Row 7 (sqlglot), Row 8 (pg_partman) — maintainability/dependency trade-offs on working, tested code. The repo's bias ("Don't build abstractions for sources we don't have yet"; "prefer explicit, boring code") leans against all four.

---

## Bottom line

Nothing here is a clear, do-it-now win that also survives the repo's scope/measure rules.
The two existing reviews already declined or narrowly-gated most infra libraries with
sound reasoning that still holds. The three items most worth a closer look:

1. **stdlib `logging` for ingestion errors** (row 1) — the only candidate that's arguably
   a correctness/policy gap rather than a preference, and it needs no new dependency.
2. **`requests.Session` reuse** (row 2) — small, low-risk, but measure the payoff first.
3. **`ftfy`** for the bref mojibake repair (row 4) — only if a benchmark shows it matches
   the hand-rolled repair on real data.

Everything else (tenacity, pydantic-settings, pg_partman, pgvector, pg_duckdb, Pandera)
is "revisit when a specific trigger fires," and the triggers are documented.
