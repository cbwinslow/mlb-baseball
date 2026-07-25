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

## ADR-005: Concurrent fetch, sequential write, for the Retrosheet bootstrap

**Decision:** `retrosheet.bootstrap()` fetches each year's zip over a bounded thread pool (`MAX_WORKERS = 4`), but still writes to Postgres sequentially, one year at a time, committing after each.

**Context:** A ~128-year bootstrap is 128 sequential HTTP round-trips if done naively — network latency, not CPU or the database, is the actual bottleneck. Parallelizing needed to not come at the cost of the existing partial-progress guarantee (a failure partway through shouldn't lose already-loaded years) or blow up memory by holding all ~128 zips at once.

**Rationale:**
- `ThreadPoolExecutor.map()` pipelines cleanly: it keeps `MAX_WORKERS` fetches in flight and yields results in order as they're consumed, so only a handful of years' zips are ever in memory at once — not fetch-everything-then-process.
- Postgres writes stay single-connection, sequential, one commit per year — same idempotent-per-year design as before, unaffected by the fetch-side change.
- `MAX_WORKERS = 4` is deliberately modest. retrosheet.org is a small, volunteer-run site, not a CDN-backed commercial API — this should be noticeably faster for us without behaving like a scraper hammering their server.

**Revisit if:** a source with a rate limit or an explicit concurrency policy needs a different number, or a future connector's bottleneck is actually CPU/parsing rather than network — that would call for a different parallelism strategy (e.g. multiprocessing), not this one.
