# Architecture Decisions

Short log of choices made and why, so we don't re-litigate them later. Newest first.

## ADR-001: Storage engine — self-hosted Postgres

**Decision:** Use Postgres as the single database for the project. No multi-database abstraction layer.

**Context:** MLB history is tens of millions of rows at the pitch level (Statcast) — not a scale that needs ClickHouse-style OLAP infrastructure. The project also needs to eventually back a live website (Phase 3), which favors a real server-based database over an embedded one like DuckDB.

**Rationale:**
- Free, no hosting cost.
- Most mature dbt adapter of the options considered (Postgres, MySQL, ClickHouse, DuckDB).
- Can serve both the ingestion/analytics workload and the Phase 3 website backend — no second database needed.
- ClickHouse's SQL dialect diverges enough (no real transactions, different upsert/join semantics) that supporting it alongside Postgres would mean real, ongoing dialect-specific work for no current benefit — the kind of premature abstraction `CLAUDE.md` says to avoid.

**Revisit if:** ingestion volume or query patterns actually hit real OLAP-scale pain on Postgres. Until then, single-database is the rule.

## ADR-002: Bare-metal Postgres by default, no Docker requirement

**Decision:** The project assumes a bare-metal (natively installed) Postgres instance by default, addressed entirely through a `DATABASE_URL` connection string in `.env`. Docker is not required and nothing in the codebase assumes it.

**Context:** Preference is for bare-metal over containers. Not everyone runs Postgres the same way, though.

**Rationale:**
- All code talks to Postgres purely through the `DATABASE_URL` env var — it has no opinion on how that Postgres instance is hosted. Point it at a bare-metal install, a remote box, or a container; the pipeline can't tell the difference.
- A `docker-compose.yml` may be added later as an **opt-in convenience** for contributors who don't already have Postgres installed — it is not the default path and nothing depends on it existing.
- `.env.example` documents the `DATABASE_URL` format; `.env` (gitignored) holds the real value.

**Revisit if:** never, really — this is just "don't hardcode a hosting assumption."

## ADR-003: Code license — AGPL-3.0

**Decision:** The code in this repo is licensed AGPL-3.0.

**Context:** This is meant to be a public community resource, but also something the project owner may want to differentiate on (e.g. the modeling/website layer in later phases). Data licenses (Retrosheet's, Lahman's CC BY-SA, etc.) are separate and unaffected — they apply to the data itself regardless of what license the code carries.

**Rationale:** AGPL's network-use clause means anyone who runs a modified version of this as a public service (e.g. a competing site built on this pipeline) has to release their source too — unlike MIT/Apache, which would let someone fork the site commercially with no obligation to contribute back.

## ADR-004: Retrosheet source — official CSV downloads, not the raw event files

**Decision:** The Retrosheet connector fetches retrosheet.org's own pre-parsed "CSV downloads" product (`retrosheet.org/downloads/{year}/{year}csvs.zip`) rather than the raw per-team event files.

**Context:** The connector was originally built against the raw event files, fetched via a full git clone of `chadwickbureau/retrosheet` (a third-party mirror, ~1.4GB) and parsed with the Chadwick `cwevent` CLI tool — verified working end-to-end (real parsing, real data, tests passing) before this decision superseded it. Checking the official retrosheet.org site directly (prompted by the project owner, who asked specifically whether the GitHub mirror was actually the best option or whether the website should be used instead) surfaced a better official product neither of us had looked at yet.

**Rationale:**
- Official first-party source, not a third-party mirror.
- No parsing tool dependency — the CSVs are already parsed and properly headered; just `pandas.read_csv()`.
- Richer: the `plays` file has 177 columns vs. `cwevent`'s default 67.
- Smaller, incremental downloads (one small zip per year) instead of a 2.5GB full-history git clone.
- Bonus: bundles six additional per-game/per-player CSVs (`gameinfo`, `teamstats`, `batting`, `pitching`, `fielding`, `allplayers`) in the same zip, at no extra integration cost.

**Cost:** this product's coverage starts at 1898, not 1871 like the raw event files. A real, documented gap — not hidden.

**Revisit if:** never expected to, but if this product is ever discontinued, the raw-event-files + `cwevent` approach is proven to work (see git history) and could be revived.

## ADR-005: Retrosheet bootstrap fetches sequentially — concurrency tried and reverted

**Decision:** `retrosheet.bootstrap()` and `retrosheet_gamelog.bootstrap()` fetch years sequentially, one HTTP request at a time.

**Context:** Originally implemented with a bounded thread pool (`ThreadPoolExecutor(max_workers=4)`, `executor.map()` pipelining fetches while writes stayed sequential) to avoid ~128 sequential HTTP round-trips. It worked in testing. Against real production data it didn't: a live bootstrap run hung partway through (~year 2015-2017), twice, after progressing normally for over 100 years first. Diagnosis before reverting, not just a guess: `/proc/PID/io` showed both `rchar` and `wchar` completely frozen (no network reads, no DB writes) for sustained multi-minute windows, and every thread (44 of them — far more than the ~5 expected for one main thread + 4 pool workers) was blocked in the kernel's `futex_wait_queue`. That's consistent with a real deadlock or thread-accumulation bug, not "just a big year taking a while" (which was the first, wrong hypothesis — ruled out by watching `rchar` actually move during genuine slow-but-working periods). No profiler (`py-spy` or equivalent) was available in this environment to safely root-cause it further.

**Rationale:** `CLAUDE.md` already says it: "prefer explicit, boring code over cleverness... predictability matters more than elegance." A data pipeline that reliably takes longer beats one that's fast until it silently hangs. `retrosheet_gamelog.py`'s bootstrap (same pattern) hadn't shown the failure in its one completed run, but keeping both connectors on the same simple, now-proven-reliable path was judged safer than leaving one on an approach just shown capable of hanging.

**Revisit if:** concurrency is worth retrying once this environment (or a future one) has proper profiling available to root-cause the original hang with confidence, rather than reverting blind.

## ADR-006: `load_dataframe`'s scoped-replace path always indexes `scope_column`

**Decision:** When `load_dataframe()` is called with `scope_column`, it creates an index on that column (`CREATE INDEX IF NOT EXISTS`, once) immediately after the table, before ever executing a scoped `DELETE`.

**Context:** Found while investigating the hang above (before the real cause turned out to be the threading bug in ADR-005) — `raw.retrosheet_plays` had grown to 9GB with zero indexes. Every per-year `DELETE FROM raw.retrosheet_plays WHERE _season = %s` was a full sequential scan, getting slower as the table grew across the bootstrap run. This is a real, generic bug in the shared loader, not specific to Retrosheet — any connector using `scope_column` at meaningful scale would hit the same problem.

**Rationale:** The fix belongs in `load_dataframe` itself, not in each connector, since every current and future user of the scoped-replace pattern needs it. Creating the index on first call (when the table — and therefore the index — is empty) means it's essentially free and every subsequent scoped `DELETE` benefits from it, not just ones after someone notices the slowdown.

**Revisit if:** never expected to — this is a correctness-adjacent fix (a missing index doesn't produce wrong results, but production behavior that degrades silently as data grows is a real trap), not a judgment call.
