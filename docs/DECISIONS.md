# Architecture Decisions

Short log of choices made and why, so we don't re-litigate them later. Newest first.

## ADR-015: MLB Stats API goes full-history, plus append-only live-game capture — supersedes ADR-014's current-season-only scoping

**Decision:** `mlb_api.py`'s schedule and standings now load full history (schedule from 1901, standings from 1969 — the divisional era) rather than the current season only. A new capability, `capture_live()`, appends point-in-time snapshots (score, inning, balls/strikes/outs, current batter/pitcher) for any game the API itself reports as `Live` right now into a new append-only table, `raw.mlb_live_game`, via a new loading primitive (`append_dataframe`, alongside `load_dataframe` in `load.py`).

**Context:** ADR-014 deliberately scoped this connector to the current season only, reasoning that a full historical pull would be pure duplication of Retrosheet's already-complete schedule/gamelog history with zero new information. Revisited on direct instruction: storage is cheap, and a second, independently-sourced copy of the same history is a genuine cross-validation asset, not wasted effort — worth having even where it overlaps what Retrosheet already provides. Also raised in the same conversation: the project's stated goal of real-time odds on the eventual website requires actual in-progress game state, which nothing in this pipeline had captured before (every other source here is completed-game-only, including the schedule/standings this connector already had).

**Rationale:**
- **Historical range confirmed by testing, not assumed.** `statsapi.schedule(season=1900)` returns 0 games, `season=1901` returns 1,110 — matches MLB's modern-era (`sportId=1`) start. `statsapi.standings_data()` raises `KeyError('division')` for every season checked before 1969 and works cleanly from 1969 on — real MLB history (divisions were introduced in 1969), not a library bug to work around. Not a gap in this project's overall coverage either way: pre-1969 win-loss records are already fully available via `raw.lahman_teams` and `raw.retrosheet_gamelog`.
- **Per-season resilience added because the failure mode changed.** A single-season fetch (ADR-014's original scope) has low odds of hitting a transient issue; 125+ sequential seasons over one bootstrap run raises those odds enough to matter. `bootstrap()` catches, logs, and skips a failing season rather than aborting the whole run — the same resilience pattern `retrosheet.py` already uses for "year not published yet," applied here for a different but related reason (transient failure, not absent data).
- **Retry-with-backoff added the same day, after — not before — a real failure**, exactly as ADR-007 anticipated: the very first full historical bootstrap hit `requests.exceptions.HTTPError: 503 Server Error: first byte timeout` from `statsapi.mlb.com` on 5 of 126 seasons (2019, 2021-2024), silently skipped by the per-season try/except before retry existed — confirmed by checking `raw.mlb_schedule`'s per-season row counts against the log, not assumed from the log alone. Added `net.call_with_retry()` (generalizes `net.get_with_retry()`, ADR-007, for library calls that make their own internal HTTP requests rather than a URL this project fetches directly — same transient-failure shape, different call shape) and wrapped every `statsapi` call in it. Re-ran the full bootstrap afterward specifically to confirm the fix closed the gap, not just that the code looked right.
- **Live capture needed a genuinely new loading primitive, not a misuse of an existing one.** Every existing pattern in `load.py` replaces some "chunk" (the whole table, or rows matching a scope value) before inserting. Live snapshots have no such chunk — every past snapshot stays meaningful, and the goal is a time series, not a latest-value overwrite. `append_dataframe()` factors out the table-creation/schema-drift logic (`_ensure_table_and_columns`, shared with `load_dataframe`) but never truncates or deletes. This is also the shape Statcast (`docs/ROADMAP.md` step 7, still unstarted) will need — not a one-off abstraction for a single caller.
- **`raw.mlb_live_game` genuinely healthy at 0 rows.** Existing `check_table_has_rows` would wrongly flag this table as broken any time nothing happens to be live — added `check_table_exists` (health.py) for tables where presence, not row count, is the health signal.
- **Scheduling stays explicitly out of scope.** `capture_live()` only does anything useful if `update()` is actually invoked repeatedly — that's still `docs/ARCHITECTURE.md`'s "Explicitly not designed yet: orchestration/scheduling" item. This change builds the capability; deciding cron vs. systemd timer vs. something else is a separate call.
- **Boxscores and rosters remain deferred**, same reasoning as ADR-014: each is a large enough endpoint surface to warrant its own connector, the same way `retrosheet_box.py` was split from `retrosheet_event.py`.

**Revisit if:** a real scheduling mechanism gets decided (wire `capture_live()`/`update()` into it then, not before), or boxscores/rosters turn out to be needed (give them their own connector, matching `retrosheet_box.py`'s precedent).

## ADR-014: MLB Stats API connector — current season only, via the `statsapi` package, no external skills/agents

**Decision:** `mlb_baseball/connectors/mlb_api.py` lands the *current* season's schedule (`raw.mlb_schedule`) and standings (`raw.mlb_standing`) via the `statsapi` Python package (PyPI `MLB-StatsAPI`, `toddrob99/MLB-StatsAPI` on GitHub). Bootstrap and update are the same full-reload operation — no per-season accumulation, since only one season is ever held. Boxscores, rosters, and full live game state (also listed under this source in `docs/DATA_SOURCES.md`) are deferred, not built in this change.

**Context:** Two real questions came up before writing any code, both worth recording since they'll come up again for future connectors:

1. **Library vs. hand-rolled HTTP.** `MLB-StatsAPI` was already pinned in `pyproject.toml` (added during scaffolding, never wired up) — checked independently against the field before using it, not just trusted because it was already there: 830+ stars, created 2019, pushed as recently as this month, GPL-3.0 (compatible with this project's AGPL-3.0 per ADR-003), vs. a much smaller (99-star) alternative (`zero-sum-seattle/python-mlb-statsapi`). Confirms rather than contradicts the existing pin. Matches this project's existing precedent of using a wrapper library where it's actually the right fit (`pybaseball` for Lahman's network fallback) rather than a blanket "always hand-roll" rule.
2. **Whether to import external Claude Code skills/subagents for "data ingestion procedures."** Evaluated concretely rather than dismissed on sight: `anthropics/skills` (official, 164k stars) turned out to have nothing data-engineering-relevant — document-processing skills (PDF/DOCX/PPTX/XLSX) and a skill-authoring template, not applicable here. `VoltAgent/awesome-claude-code-subagents` (23.7k stars, actively maintained, MIT — genuinely well-supported by the numbers) was pulled and read directly: its `postgres-pro` subagent is generic enterprise-DBA material (replication setup, backup strategies, 99.95%-uptime targets) — the wrong shape for a solo, bare-metal, single-Postgres-instance project (ADR-002), and with no awareness of this repo's actual conventions (the connector contract, idempotency tests, `mlb doctor`). Larger skill collections (`alirezarezvani/claude-skills`, 345 skills / 644 scripts) trade a bigger unreviewed-script surface for no specific relevance to this project. None imported.

**Rationale:**
- **Current season only, not full historical backfill.** Retrosheet already covers full history for both planned schedules (`retrosheet_schedule.py`, 1877–2026) and completed-game results (`retrosheet_gamelog.py`, 1871–present) — re-pulling that same history from MLB's API would be pure duplication, at real added cost (a season-by-season API pull back to 1901+), for zero new information. What this source uniquely adds is the *current*, still-in-progress season before Retrosheet has published it, plus live game states (Scheduled/Postponed/Cancelled/Completed Early) that don't exist in Retrosheet's completed-game-only products at all.
- **Real data quirk found and fixed, not silently swallowed:** a live full-season pull (2,946 games, 2026 season) crashed `CREATE TABLE` with `DuplicateColumn` — `statsapi`'s own `schedule()` emits `losing_Team` (capital T) instead of `losing_team` specifically for tied Spring Training/Exhibition games (confirmed: 22/2,946 games, all ties, `game_type` S/E, never both keys on the same game). `load.py`'s column-name sanitizing lowercases both to the same Postgres column, which is exactly the collision. Coalesced explicitly in `_schedule_df()` before the DataFrame is built, with the real numbers behind it recorded in a comment — not a defensive try/except, since the actual cause was root-caused first.
- **No retry-with-backoff added speculatively.** Unlike `mlb_baseball/net.py` (ADR-007), which was added only after a real, observed transient-failure pattern against retrosheet.org, nothing like that has been observed against `statsapi.mlb.com` yet. `track_run()` already surfaces any failure as a logged, non-zero-exit failed run — that satisfies CLAUDE.md's "errors ... handled explicitly, not silently swallowed" bar without adding retry logic ahead of a demonstrated need.

**Verified against real production data**: `mlb ingest mlb_api --mode bootstrap` lands 2,946 games and 30 teams' standings for the 2026 season; re-running (`--mode update`) produces identical counts (idempotent); `mlb doctor` reports both tables and the last run cleanly.

**Revisit if:** boxscores, rosters, or full live game state turn out to be needed — each is a large enough endpoint surface (per-game boxscore calls at 2,400+ games/season) to warrant its own connector file, the same way `retrosheet_box.py` was split out from `retrosheet_event.py` rather than folded in.

## ADR-013: A `core` schema for dimensional data, built by `conform.py`; `gold` created but left empty

**Decision:** Renamed the `conformed` schema to `core` (one word, per CLAUDE.md's naming convention) and added an empty `gold` schema alongside it. `core` now holds `core.player`/`core.team`/`core.game` — real relational tables with surrogate primary keys, foreign keys, and indices — built by a new, non-network transform module (`mlb_baseball/conform.py`, run via `mlb conform`) that joins already-ingested `raw.*` data. `raw` stays exactly as it was: untyped `text` columns, no constraints, source-faithful. `gold` has no tables yet — it's scaffolding for Phase 2/3 (ML features, website-serving tables), not something to design ahead of need.

**Context:** Prompted by the project owner disliking `conformed` as a table-name-length outlier and asking whether a 3-layer (raw/normalized/gold) medallion architecture made sense, given the project's three eventual consumers (ingestion pipeline, ML modeling, the oddstrader.com website). Rather than default to either "stick with 2 tiers" or "build all 3 now," this was checked against real precedent on both axes:
- **Industry standard:** the medallion pattern (bronze/raw → silver/conformed → gold/feature) is genuinely standard for exactly this shape of problem — multiple raw sources landing at different grains, needing a canonical join layer before any ML-feature or serving layer sits on top. Kimball's dimensional-modeling vocabulary ("conformed dimensions") is where the schema's original name came from — `player`/`team`/`game` here are exactly that: shared dimensions every downstream fact table (event-level pitch data, game logs, features) will eventually key off of.
- **This project's own prior art:** the old project (`cbwinslow/mlb-baseball-ml`, explicitly ideas-reference-only per `docs/NORTH_STAR.md`) turned out to have its *documented* schema plan (7 zones: control/bronze/silver/gold/feature/serving/agent) diverge from what its actual committed SQL migrations built — found via a second, separate old repo (`cbwinslow/mlb.git`, checked out locally at `/mnt/storage/data-lake/baseball/mlb/`) that has the real, applied schema list: `api, auth, core, mart, meta, ml, ops, raw_bref, raw_chadwick, raw_espn, raw_fangraphs, raw_lahman, raw_mlbapi, raw_odds, raw_retrosheet, raw_statcast, ref, stg, util`. The schema name `core` was already independently in real use there — direct validation of the name landed on here, not just a preference match.

**Rationale:**
- **2 schemas built now, 3 created now** is the middle path between "stick with 2 tiers" and "build all 3 immediately": `gold` exists (so the eventual migration is additive, not a rename-under-load later) but holds nothing, honoring `docs/NORTH_STAR.md`'s Phase 1 scope discipline — no ML/website tables designed before Phase 2/3 actually need them.
- **`raw` stays untyped on purpose, `core` is where constraints get enforced** — this split was the one place the owner asked to see the actual industry standard rather than a stated preference: raw's job is tolerating schema drift from sources that change shape without warning (see `load_dataframe`'s `ALTER TABLE ADD COLUMN` behavior, needed for `cwbox`'s variable attribute sets); `core`'s job is being safe to build on top of, which is exactly what PK/FK/index enforcement is for. Mirrors the raw/conformed split in both the medallion literature and the old project's real schema list.
- **One row per team-era, not per franchise**, on `core.team` — `(retro_team_id, first_year, last_year)` is the real natural key, not `retro_team_id` alone, since Retrosheet reuses a team_id across non-contiguous eras (confirmed twice in real data: HOU 1962-2012 vs 2013-2021, MIL 1970-1997 vs 1998-2021 — both league changes). No franchise-continuity table yet linking e.g. Boston/Milwaukee/Atlanta Braves — a known, deliberate gap until something needs it.
- **Pitcher FKs on `core.game` are nullable by design**, not an oversight: 239 real games' winning-pitcher ID doesn't resolve to any `core.player` row, and roughly 2,000 games record no winning pitcher at all — losing that one reference must not lose the rest of the game's row, so `conform.py`'s builds are `LEFT JOIN`, never `INNER JOIN`.
- **`conform.py` is a transform, not a connector** — no `bootstrap()`/`update()` split (it doesn't distinguish; every run is a full truncate-and-rebuild, cheap at this row count and simplest-correct per CLAUDE.md's "boring code" guidance), and it isn't in the `CONNECTORS` registry `mlb ingest` dispatches through — it's its own `mlb conform` subcommand, checked in `doctor.py` directly instead of through the per-connector health-check loop.
- **`_check_prerequisites()` checks the actual raw tables it depends on before running**, not just letting a bad join fail confusingly, and (like every other fresh-DB-safe check added this session) treats "table doesn't exist yet" the same as "table is empty" — both mean "this hasn't been bootstrapped," and both get an actionable `mlb ingest ... --mode bootstrap` message instead of a raw `UndefinedTable` traceback.
- **Real data quality issues found while building this, fixed with explicit, documented casts rather than silently swallowed:** `raw.retrosheet_gameinfo`'s `number`/`attendance`/`timeofgame` columns have text like `"12000.0"` (pandas coerces an int column with any missing values to float on CSV read), plus two genuinely non-numeric attendance values Retrosheet's own data carries (`"6500?"`, `"<1000"` — uncertain-attendance annotations) and 188 rows of `"-1.0"` (Retrosheet's own sentinel for unknown game duration). `conform.py` only converts a value matching a plain non-negative numeric pattern; anything else becomes `NULL` rather than guessing a number the source itself flagged as uncertain or unknown.

**Verified against real production data**, not just against test fixtures: `mlb conform` run for real yields `core.team` 152 rows, `core.player` 25,543 rows, `core.game` 224,877 rows; re-running produces the identical counts (idempotent); and the Don Larsen 1956 World Series perfect game (already tied out at the raw layer, see the Larsen test suite) reconciles correctly through `core.game` — `NYA195610080`, BRO 0 – NYA 2, `game_type` worldseries, winning pitcher `larsd102` (Larsen), losing pitcher `magls101` (Maglie).

**Revisit if:** a real consumer (ML feature pipeline, or the website) needs `gold` tables — at that point design them against that consumer's actual query shape, not speculatively now.

## ADR-012: `retrosheet_box.py` — box-score-only games via `cwbox`, with constructed team/roster files where Retrosheet doesn't bundle them

**Decision:** A new connector (`retrosheet_box.py`) parses Retrosheet's box-score-only files (pre-1910 seasons, the 1871/1872/1874 NA seasons, and Negro League games that only ever exist as box scores) via the Chadwick `cwbox` CLI tool, landing `raw.retrosheet_box_game/batting/fielding/pitching`. This closes the coverage gap `retrosheet_event.py`'s docstring already flagged as a known, undone limitation.

**Context:** Several of Retrosheet's box-score archives (`1890sbox.zip`, `1900sbox.zip`, `allebr.zip`) don't bundle `TEAM{year}`/roster files the way the regular-season decade zips do. Before writing any code, researched the actual documented requirement rather than guessing: Retrosheet's own BEVENT documentation (retrosheet.org/datause.html) states "you must have the 'team' and the appropriate roster files in the same directory" — and confirmed empirically that, unlike `cwevent`/`cwgame` (whose team-code fields come from the event file's own `info` records regardless of team-file content), `cwbox` genuinely needs a *real* team file: an empty placeholder produces blank `visitor`/`home` team codes and names in its output, tested both ways against real 1900 data.

**Rationale:**
- Rather than treat the missing team/roster files as a dead end, they're constructed from Retrosheet's own official registries — `TEAMABR.TXT` for MLB seasons, `biodata.zip`'s `teams0.csv` for Negro League seasons (both already used elsewhere in this project) — filtered to whichever teams were active in the year being processed, written in the exact format confirmed against a real bundled `TEAM{year}` file (`team_id,league,city,nickname`). Real roster files are copied in from Retrosheet's own `rosters.zip` (already used by `retrosheet_roster.py`). This is following Retrosheet's documented procedure with data from Retrosheet's own official sources, not inventing a workaround.
- `chadwick_tools.split_by_year`/`year_of` were extracted out of `retrosheet_event.py` (previously private to it) into shared functions, since this connector needs the identical "split a flat multi-year archive into per-year directories" logic — two real, concrete uses justified sharing it, per CLAUDE.md's guidance on when abstraction is warranted.
- Scopes replaces on `_scope` (season+group combined), the same fix as ADR-010, for the same reason: `era` (1898-1909) and `negro_league` (1903-1961) box archives both have rows for overlapping seasons (e.g. 1903), which would collide and delete each other's data if scoped on season alone.
- `cwbox`'s XML output isn't well-formed for two real reasons found while testing against the full corpus, not anticipated in advance: (1) it emits bare unescaped `&` in attribute values for names that contain one (e.g. team "WPS", "Western Pipe & Steel", 1943) instead of `&amp;` — sanitized before parsing; (2) a handful of games in Retrosheet's own historical data reference a player in a defensive-line summary who isn't otherwise registered for that game (confirmed genuinely rare: 1 game out of 46 years of Negro League box files), which makes `cwbox` abort *all* output for the files it was given. Rather than lose an entire year's good games over one bad record, the specific game named in `cwbox`'s own error message is stripped from the source file and the year is retried once — logged clearly when it happens, not silently dropped.

**Cost:** still doesn't cover box-score files needing player handedness/positional detail beyond what `cwbox`'s box-score XML exposes (it doesn't carry bats/throws — that's `retrosheet_reference.py`'s biofile data instead), and doesn't parse the `<doubles>`/`<triples>`/`<stolenbases>`/`<doubleplays>` supplementary lists `cwbox` also emits — scoped out as a possible future enhancement, not required to close the game-level coverage gap this was built for.

**Revisit if:** the supplementary event-detail lists turn out to be worth the added table surface, or if `cwbox` surfaces further data-integrity errors beyond the one class handled here (the strip-and-retry logic handles exactly the "cannot find entry for player... in dline" error signature; a different error class would need its own handling, not a silent catch-all).

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
