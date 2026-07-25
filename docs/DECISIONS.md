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
