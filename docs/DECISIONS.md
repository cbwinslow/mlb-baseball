# Architecture Decisions

Short log of choices made and why, so we don't re-litigate them later. Newest first.

## ADR-011: `mlb doctor`/`mlb inventory` must never crash — even on a database that's never been migrated

**Decision:** Every check in `doctor.py`, and `inventory.last_runs()`, catches `UndefinedTable` on its own queries and reports a clean, actionable failed result (naming the fix — usually `mlb migrate`) instead of letting the exception propagate. `doctor.run()`'s core checks (schemas, migrations, downloads directory) are wrapped the same defensive way its per-connector loop already was.

**Context:** Found by deliberately testing `mlb doctor` and `mlb inventory` against a freshly-created, never-migrated database — exactly the state a brand-new clone's database is in before the first `mlb migrate`. Both crashed with a raw `psycopg.errors.UndefinedTable` traceback. That's the worst possible first impression for a tool whose entire purpose is diagnosing what's wrong: the diagnostic tool itself was the thing breaking, on the single most common fresh-start scenario there is.

**Rationale:**
- `mlb doctor`'s whole job is to be safe to run in *any* state the project might be in, not just the ones a developer happened to test by hand — "adapt to other users' environments" only means something if it includes the very first environment: nothing set up yet.
- Detail messages name the actual next command (`mlb migrate`, `mlb ingest <source> --mode bootstrap`) wherever there's an unambiguous one, not just "X is missing" — the point of these messages is that a person or an agent reading them can act immediately, not have to go figure out what's wrong first.
- Extended `mlb_baseball/manifest.py` with `check_downloads_directory()` (writable + free disk space, warned below 2GB) and wired it into `doctor` as a core check — the download-to-disk architecture (ADR-008) means every connector now shares this one dependency, so it's a `doctor` core check, not a per-connector one.
- Added `chadwick_tools.missing_tools()` (checks `cwevent`/`cwgame` on `PATH` via `shutil.which`) surfaced through `retrosheet_event.health_check()`, so a missing system dependency shows up in `mlb doctor` before a multi-hour bootstrap, not as a bare `FileNotFoundError` partway through one. Documented the actual install requirement in `README.md` and `docs/TOOLS.md`, which had gone stale (still described Retrosheet as needing no parsing tool, true before ADR-009, not after).
- Tests that exercise real `cwevent`/`cwgame` subprocess calls (not mocked, per this project's "mock the network, not the parsing" testing philosophy) now skip cleanly via `pytest.mark.skipif(chadwick_tools.missing_tools(), ...)` instead of failing outright, so `pytest` still passes end-to-end for a contributor who hasn't installed the Chadwick tools yet.

**Revisit if:** never expected to — like ADR-006 (missing index) and the `mlb doctor`/`health.py` fixes earlier this session, this is a correctness fix for tooling that's supposed to be trustworthy in every state, not a judgment call.

## ADR-010: `retrosheet_event`'s scoped replace keys on season+group, not season alone

**Decision:** `retrosheet_event.py` tags every row with `_scope` (season and archive group combined, e.g. `"2024_pbp"` vs `"2024_postseason"`) and uses that as `load_dataframe`'s `scope_column`, not `_season` alone.

**Context:** Found in production, the expensive way. `retrosheet_event.bootstrap()` loads the 12 regular-season decade archives first, then the post-season/all-star/Negro League archives — all of which independently cover overlapping seasons (a post-season game and a regular-season game from the same year both get `_season = "2024"`). The original version scoped the replace on `_season` alone, so loading the post-season archive for 2024 issued `DELETE FROM raw.retrosheet_event WHERE _season = '2024'` before inserting only its own (much smaller) post-season rows — silently deleting that year's already-loaded regular-season data. Across a full bootstrap this destroyed essentially all regular-season rows (~16 million), leaving only the last-processed group's data per season. Not caught by tests before the real run because every existing test used a single group per load.

**Rationale:**
- `_scope` (season+group) is the actual unit of independent, safely-replaceable data for this connector — `_season` alone was the wrong grain from the start, once more than one group could share a season.
- `_season` and `_group` stay as their own real columns (unaffected) for querying; `_scope` exists purely to drive the replace boundary, same pattern as any other connector's `scope_column`.
- Regression test added (`test_loading_a_different_group_for_the_same_season_does_not_wipe_the_first`) that loads two different groups for the same season and asserts both survive — this is the test that would have caught it, and does now.

**Cost:** this bug required re-running the full raw-event-file bootstrap (all 12 decades + special archives) a third time in the same session — first for the initial Negro-League-file crash (ADR unrelated to this one), second because an unrelated debugging mistake dropped the tables, third for this fix. Each full run took roughly 50 minutes.

**Revisit if:** never expected to — this is a correctness fix for a real data-loss bug, not a judgment call. Any future connector where multiple independent sources can land rows for the same natural-looking scope key (season, date, etc.) should scope on the actual independent unit, not just the most obvious column.

## ADR-009: Raw event files return as an additional Retrosheet product, parsed via `cwevent`/`cwgame`

**Decision:** `retrosheet_event.py` downloads Retrosheet's raw `.EVA`/`.EVN`/`.EVF`/`.EVR` (+ `.EDA`/`.EDN` deduced) event files and parses them locally with the already-installed `cwevent`/`cwgame` CLI tools into `raw.retrosheet_event` (per-play) and `raw.retrosheet_game` (per-game). This does not replace `retrosheet.py`'s CSV product (ADR-004) — both are kept.

**Context:** ADR-004 chose the CSV product over raw event files + `cwevent`, reasoning the CSV product was richer, simpler, and needed no CLI dependency. That tradeoff stands for *speed and ease of bootstrap*, but retrosheet.org's own site treats raw event files as the authoritative artifact and the CSV downloads as a derived convenience product ("all traditional data" and "CSV downloads" are offered as two separate, complementary top-line options). Re-parsing raw files locally means this platform isn't permanently downstream of retrosheet.org's own CSV-generation choices, and can re-derive structured data if parsing needs change later — the same reasoning ADR-004 itself cited as a reason to keep raw files around "if this product is ever discontinued."

**Rationale:**
- `pychadwick` (the pip package) still fails to build against modern CMake, same as when ADR-004 was written — but the `cwevent`/`cwgame` CLI binaries are already installed on this machine and were verified working end-to-end against real downloaded event files this session (both single-year and multi-year decade zips).
- Requests the full field set from `cwevent` (`-f 0-96 -x 0-66`), not a curated subset — this is a raw-layer table and should stay source-faithful and complete.
- Retrosheet bundles most of its history as decade-spanning zips with every year's files mixed together flat; `cwevent`/`cwgame` process one year at a time (the `-y` flag governs which `TEAM{year}`/`{team}{year}.ROS` files they resolve), so each archive is extracted to a temp directory and split into per-year subdirectories before parsing (`_split_by_year`). The temp extraction is cleaned up after each load; only the downloaded archive itself persists on disk.

**Known gap, not silently dropped:** box-score-only event files (pre-1910, plus the 1871/1872/1874 NA seasons, and Negro League box scores) use a different file format (`.EBA`/`.EBN`) and Retrosheet's `cwbox` tool, which has an incompatible CLI (no CSV/field-list output — only human-readable text or XML box scores). That's a genuinely separate parsing problem, not a quick extension of this connector, and wasn't built in this pass. Tracked here so it isn't forgotten, not hidden inside a "coverage complete" claim.

**Revisit if:** `cwbox`'s XML output (`-X`) is worth building a real parser for, to close the pre-1910/Negro-League-box-score gap.

## ADR-008: Downloads persist to disk with a JSON manifest before parsing

**Decision:** Every Retrosheet connector downloads its source files to `downloads/<source>/` first (via `mlb_baseball/manifest.py`'s `download()`), recording each file's URL, sha256, size, and status (`downloaded`/`loaded`) in a per-source `manifest.json`. Parsing reads from disk, not from an in-memory response body. A file already on disk whose hash matches the manifest is not re-fetched — `download(..., force=True)` bypasses that shortcut for archives Retrosheet updates in place (used by `update()` on the current season/decade).

**Context:** The original Retrosheet-family connectors (`retrosheet.py`, `retrosheet_gamelog.py`, `retrosheet_reference.py`) fetched entirely in memory — bytes in, DataFrame out, nothing written to disk. Real pain this session traced back to this design: repeated bootstrap attempts (bug fixes, a threading revert, a missing-index fix) each re-downloaded the full ~128-year history from scratch, no partial progress survived a crash, and it directly contributed to the `ConnectionError` failures ADR-007's retry logic had to work around. The project owner raised this directly mid-session as a design concern, not a preference.

**Rationale:**
- File-level state (what's downloaded, what's stale) belongs in a manifest scoped to *files*; run-level state (start/end/rows/error) stays in `meta.ingestion_run` via `mlb_baseball.ingest.track_run` — two different concerns, deliberately not merged into one system.
- Kept intentionally lightweight — a JSON file per source, not a Postgres control schema (`meta.source_file`, `meta.raw_payload_registry`, etc., as a heavier alternative design would have it). That's real machinery this project's shape (bare-metal, $0 budget, one maintainer, "boring code" per CLAUDE.md) doesn't need; the manifest solves the actual problem (avoid re-fetching what's already on disk and unchanged) without it.
- `force=True` exists because a same-name file already on disk doesn't guarantee Retrosheet's copy hasn't changed — the current season's CSV/event-file archives and game logs get corrected/appended in place, so `update()` must still hit the network for those even when the manifest looks "current."

**Revisit if:** a source needs finer-grained resumability than "the whole archive" (e.g. resuming a parse that died partway through a huge multi-year zip) — not needed yet; parsing has stayed fast enough that redoing it from an already-downloaded file is cheap.

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

## ADR-007: Retry-with-backoff for HTTP fetches (`mlb_baseball/net.py`)

**Decision:** `mlb_baseball.net.get_with_retry()` wraps `requests.get()` with retry-on-`ConnectionError` (default: 4 attempts, backoff growing 5s/10s/15s). Used by both Retrosheet per-year connectors in place of calling `requests.get()` directly.

**Context:** Not speculative — a real bootstrap run against retrosheet.org failed outright with `requests.exceptions.ConnectionError: Remote end closed connection without response`, after sustained repeated requests across several bootstrap attempts in one session (almost certainly the server pushing back under load, possibly rate-limiting). A ~128-request bootstrap has no business dying entirely over one transient failure partway through.

**Rationale:** A shared helper instead of a per-connector try/except, since any connector making many sequential requests to one host over a long-running bootstrap has the same exposure — this crosses the line from "premature abstraction" to "the same real problem, twice, at the point it was found."

**Revisit if:** a source's failures need different handling (e.g. respecting a `Retry-After` header, or backing off on 429/503 responses too, not just connection-level errors) — extend `get_with_retry`, don't hand-roll another one-off retry loop.
