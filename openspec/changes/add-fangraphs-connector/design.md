## Context

See `proposal.md` — Why. FanGraphs is `pybaseball`-broken; `fungo` reaches it
through the `okhttp/4.12.0` Cloudflare exemption.

Constraints that shape the approach:

- **The FanGraphs access seam is fragile.** It rides one User-Agent exemption
  that "could be withdrawn at any time" (`fungo`'s own words). Whatever we
  build must fail loudly and specifically when that happens, and must not be
  something we have to re-reverse-engineer ourselves.
- **Existing connector infrastructure is mandatory** (`connectors/AGENTS.md`):
  `load_dataframe` (auto-creates the raw table from DataFrame columns — no
  migration, same as `bref.py`), `track_run`, `call_with_retry` / `net.py`,
  the `health.py` primitives, `source_profiles.require_sources`.
- **`fungo` returns `list[dict]`, not DataFrames.** Callers wrap
  (`pd.DataFrame(rows)`) themselves. FanGraphs values arrive as native JSON
  numbers; some string fields carry embedded HTML anchors (`Team`, `Season`).
- **`bref.py` is the closest existing analogue**: a season-scoped stats
  connector, one HTTP request per season, `bootstrap()` loops history with
  `season_already_loaded` skip, `update()` reloads the current season, WAR-
  style whole-table reloads for the no-season-parameter products, no cron of
  its own beyond `mlb update`.
- **`fungo`'s FanGraphs functions** (verified live 2026-09-10):
  `get_leaders(stats, start_season, end_season, **kwargs)` (`ind=1` → one row
  per player-season; `stats` ∈ `bat|pit|fld`), `get_guts_constants()` (full
  history, one call), `get_park_factors(season)` /
  `get_park_factors_by_handedness(season)`, `get_projections(system, stats)`
  (`PROJECTION_SYSTEMS` = 8 preseason, `ROS_PROJECTION_SYSTEMS` = 8 RoS;
  bare-list response), `get_prospect_board(season, ...)`, `get_depth_chart` /
  `get_roster_resource(page)`, `get_split_leaders(position, season, splits,
  ...)` (POST; 292-code `SPLIT_CODE_TABLE`, named shortcuts in `SPLIT_CODES`).

## Goals / Non-Goals

**Goals:**

- Land every FanGraphs bulk (league-wide / season-grain) product `fungo`
  exposes into source-faithful `raw.fangraphs_*` tables.
- Retain projection history: a projection is a moving series, so store dated
  snapshots, de-duplicated, append-only.
- Idempotent bootstrap/update; resumable bootstrap at the season grain.
- Rides `mlb update`; a dedicated sub-daily job captures projection movement.
- Rights, docs, ADR, sidecar, health surfaces updated in the same change.

**Non-Goals:**

- No `core`/`gold` conforming of FanGraphs IDs or metrics — raw only.
- No per-player-per-season endpoints (`get_player_stats`, `get_game_log`) and
  no full 292-code split enumeration — combinatorial cost out of proportion to
  value (ADR-020 / ADR-024 precedent). Documented, not silently skipped.
- No minor-league leaderboards (`league="minor"`).
- No vendoring of `fungo` source — depend on the published package.
- No change to `pybaseball`'s role for Baseball-Reference (`bref.py` stays).

## Decisions

### D1: Depend on `fungo`, do not vendor the FanGraphs code

`connectors/AGENTS.md`: *"Prefer the official maintained client/library when it
materially reduces fragile endpoint glue and a parity spike proves coverage."*
The FanGraphs access path is exactly the fragile glue that rule is about — a
Cloudflare-exempt UA, inverted `season`/`season1` params, POST-only splits, a
React-cache scrape for depth charts. `fungo` maintains all of it, is MIT
(AGPL-compatible), "Production/Stable", and the live parity check passed.

- **Alternative — vendor `fungo/fangraphs/` + `http.py` + `exceptions.py`:**
  rejected. We'd own the fragile seam and the re-reverse-engineering when
  Cloudflare shifts. The point of the library is that someone else does that.
- **Alternative — keep waiting for a fixed `pybaseball`:** rejected; broken
  since 2025 with no fix in sight, and `pybaseball`'s FanGraphs surface is
  narrower (no Guts!, no projection systems, no Stuff+/PitchingBot columns).
- **Cost 1 — `curl_cffi`:** `fungo`'s top-level `__init__` imports its `bbref`
  submodule, which imports `curl_cffi` — so `curl_cffi` becomes a hard
  dependency even though this connector never calls `fungo.bbref`. `curl_cffi`
  ships manylinux/macOS/Windows binary wheels; accept it. Import
  `fungo.fangraphs` submodules directly in the connector; if `curl_cffi`
  proves troublesome in CI, the fallback is a thin lazy-import shim, not
  vendoring. Resolved version at time of writing: `curl_cffi==0.16.3`.
- **Cost 2 — Python floor moves 3.11 → 3.12** (found during apply, not
  anticipated in the proposal). `fungo` requires `>=3.12` and genuinely uses
  3.12-only syntax (PEP 695 in `http.py`), so it cannot be back-fitted to
  3.11. Adding it forces `requires-python = ">=3.12"`, the four CI
  `python-version` pins, `pages.yml`, `.devcontainer/Dockerfile`, and
  `ruff target-version = "py312"`. Verified before committing: the project's
  dev venv is already 3.12.3; on 3.12 with `fungo` added, `ruff` (one new
  UP047 in `model/markov/core.py` — suppressed project-wide via
  `ignore = ["UP046","UP047"]`, PEP 695 restyle is not in scope), `mypy` (214
  files), `sqlfluff`/SQL-ownership, `mkdocs --strict`, 1205 unit tests, and a
  representative integration slice (bref/load/doctor/health/ingest/migrations,
  32 tests) all pass. Owner approved the bump conditional on "nothing breaks".
  ADR-288 records it.
- **Alternative — vendor `fungo/fangraphs/` (~1,900 lines) instead of the
  Python bump:** considered when the floor conflict surfaced. Rejected: we'd
  own the fragile Cloudflare seam (the thing D1 exists to avoid), and the
  3.12 bump is small, already true locally, and 3.12 is 2+ years old.
- Pin `fungo>=2.0,<3` in `pyproject.toml`; let `uv lock` resolve. A `fungo`
  major bump gets a deliberate review (the FanGraphs seam is where breakage
  lands).

### D2: Table layout and replace strategy per product

| Table | `fungo` call | Grain | Strategy |
|---|---|---|---|
| `raw.fangraphs_batting` / `_pitching` / `_fielding` | `get_leaders("bat"/"pit"/"fld", s, s, ind=1, qual=0)` | player-season | per-season scoped replace (`_season`) |
| `raw.fangraphs_guts` | `get_guts_constants()` | season | whole-table replace |
| `raw.fangraphs_park_factors` | `get_park_factors(s)` | team-season | per-season scoped replace |
| `raw.fangraphs_park_factors_handedness` | `get_park_factors_by_handedness(s)` | team-season-hand | per-season scoped replace |
| `raw.fangraphs_prospects` | `get_prospect_board(s)` | player-season | per-season scoped replace |
| `raw.fangraphs_depth_chart` | `get_depth_chart(page)` per team | team-player, dated | append snapshot (`_captured_date`), de-duped like D3 |
| `raw.fangraphs_split_batting` / `_split_pitching` | `get_split_leaders(pos, s, split)` for a curated split list | player-season-split | per-season scoped replace, `_split` in key |
| `raw.fangraphs_projection` | `get_projections(system, stats)` for all 16 systems | player-system-statgroup, dated | append snapshot, de-duped (D3) |

- Tables auto-create via `load_dataframe` from the DataFrame's columns (no
  migration), matching `bref.py`. Added bookkeeping columns are `_`-prefixed
  (`_season`, `_captured_date`, `_projection_system`, `_horizon`, `_split`) —
  same convention as `bref.py`'s `_season`.
- `qual=0` (everyone, not just qualified) so the raw layer isn't lossy;
  downstream can filter.
- `ind=1` (one row per player-season) not `ind=0` — `fungo` documents that
  server-side span aggregation fails for long ranges; we loop seasons anyway.
- Leaderboard history depth is discovered, not hard-coded: start at a
  conservative floor (FanGraphs standard boards go to 1871; advanced columns
  begin later and simply come back null for early seasons — preserved as
  genuine nulls), and let an empty response end the range. Record the observed
  first season per board in the sidecar once bootstrap has run for real.

### D3: Projections — append-only dated snapshots with change detection

Projections update several times a day; the owner wants the history. Storing a
full snapshot every run would bloat without bound, so follow the ADR-048
probable-pitcher pattern: before appending, compare each `(system, stat_group,
playerid)` row against that key's most recent stored snapshot (hash the
projected-value columns); append only changed or new keys. `append_dataframe`
with `identity_columns` is the existing primitive; the change-detection query
is a `DISTINCT ON (...) ... ORDER BY _captured_date DESC` read.

- `_captured_date` is a UTC date; if a key changes twice in one day the second
  change still appends (date + value hash both part of dedupe → a same-day
  second row is allowed when the value differs). Keep it date-grain, not
  timestamp — projection movement within a day is not research-material and
  timestamp-grain multiplies rows.
- Preseason vs RoS distinguished by `_horizon` ∈ `preseason|ros`, derived from
  which system list the slug came from.

### D4: Cron — ride `mlb update` plus a dedicated sub-daily job

- Register in `registry.py` → `fangraphs` is in `CONNECTORS` → `mlb update`
  (hence `scripts/mlb_daily_update.sh`) runs `update()` daily. No `cli.py`
  edit needed (it reads `CONNECTORS`).
- `bootstrap()` (full history) stays a deliberate one-off: `mlb ingest
  fangraphs --mode bootstrap`.
- New `scripts/fangraphs_update.sh`: flock + log, byte-for-byte the shape of
  `scripts/mlb_api_update.sh`, running `mlb ingest fangraphs --mode update` on
  a **6-hourly** cadence (4×/day — enough to catch projection movement,
  bounded request volume; same spirit as ADR-285's 2-hourly odds job). The
  daily leaderboard/park-factor/guts reload is cheap and harmless to also run
  4×/day (per-season scoped replace, idempotent), so `update()` does the whole
  set each time; there is no separate "projections-only" mode to maintain.
- `health_check()`: `check_table_has_rows` for each core table +
  `check_last_run("fangraphs")`. Add a freshness threshold (like
  `mlb_api.py`'s `FRESHNESS_THRESHOLD_MINUTES`) sized to the 6-hour cadence so
  `mlb doctor` catches a silently-dead cron.
- `_SAME_SERVER_GROUPS`: none — fangraphs.com is hit by no other connector.

### D5: Rights posture — `local_research`, fail-closed, same as Baseball-Reference

New `docs/SOURCE_RIGHTS.md` row: *"FanGraphs via fungo — No permission evidence
recorded for automated collection, predictive ML, or redistribution. local
research: yes, owner-risk. licensed full: no. public-safe: no."* Not added to
`source_profiles.PUBLIC_SAFE`. `require_sources` already blocks any connector
not in `PUBLIC_SAFE` under a non-local profile — the connector calls it (or
inherits the CLI's pre-request guard) exactly as the others do. No export
`RELATION` gets `profile="public_safe"` for these tables.

### D6: Error handling and retries

- All network calls go through `net.call_with_retry` (bounded exponential
  backoff, already used by `bref.py`) wrapping the `fungo` call.
- A `fungo` `FangraphsError` (the 403 / exemption-withdrawn signal) is caught
  at the connector's run boundary, logged with its message verbatim, recorded
  as a failed `track_run`, and **not** retried past `call_with_retry`'s bound
  — re-raising ends the run so `mlb doctor` shows red. It must never degrade
  to an infinite retry.
- Per-season failures inside `bootstrap()` are logged and skipped (that season
  only), matching `bref.py`; committed seasons survive.

## Risks / Trade-offs

- **The `okhttp/4.12.0` exemption is withdrawn** → connector starts failing
  with `FangraphsError`. Mitigation: fail loud and specific (D6), health check
  goes red, docs/sidecar say plainly this is a single load-bearing exemption
  and the fix is a `fungo` upgrade, not a local patch. This is an accepted,
  documented fragility — same class as `bref.py` depending on `pybaseball`'s
  HTML scrape.
- **`curl_cffi` as a transitive hard dependency** for code we don't call →
  build/CI weight, a binary wheel. Mitigation: it has broad wheel coverage;
  accept it; lazy-import shim as fallback (D1). Flag in the ADR.
- **FanGraphs quietly changes its JSON shape** (column added/renamed) →
  `load_dataframe`'s `schema_drift_policy="warn"` surfaces it without breaking
  the load; raw stays source-faithful. Downstream conform work (separate) is
  where drift would bite, and there is no downstream yet.
- **Projection snapshot growth** → 16 systems × ~1.5k players × changed-only
  rows × daily. Mitigation: change-detection dedupe (D3), date-grain not
  timestamp. Estimate and record real row growth after the first month;
  revisit retention (e.g. keep daily for the current season, weekly older) as
  a follow-up if it matters.
- **Rights** → FanGraphs data must never reach a public artifact. Mitigation:
  fail-closed profile (D5); the existing `public_safe` export guard already
  refuses any non-Retrosheet source.
- **`get_split_leaders` is POST and heavier** → curated list only (5–6
  splits), per-season; not the 292-code catalogue. Documented non-goal.

## Migration Plan

1. Add `fungo>=2.0,<3` to `pyproject.toml`; `uv lock`; `uv sync`.
2. Land `connectors/fangraphs.py` + sidecar + `registry.py` registration +
   tests. No DB migration (tables auto-create).
3. `docs/SOURCE_RIGHTS.md` row, `docs/DATA_SOURCES.md` move out of Deferred,
   new ADR in `docs/DECISIONS.md`, `scripts/check_dox.py` baseline.
4. One-off real bootstrap: `MLB_DATA_PROFILE=local_research mlb ingest
   fangraphs --mode bootstrap`. Record observed first-season-per-board and
   real row counts in the sidecar.
5. Install `scripts/fangraphs_update.sh` in cron (6-hourly). Confirm
   `mlb doctor` shows the source green.
- **Rollback:** remove `fangraphs` from `registry.py` and the cron line; the
  `raw.fangraphs_*` tables can be dropped independently (nothing downstream
  depends on them). Revert the `pyproject.toml` / lock change.

## Open Questions

- Exact projection retention policy long-term (keep-all vs thin older
  snapshots) — deferable: it does not change the schema, the connector
  approach, or the task list, only a later pruning job. Decide after a month
  of observed growth.
- Whether to also capture `get_depth_chart` at all in v1 or defer with the
  other roster-resource surface — leaning include (only ~30 calls), but it is
  the one endpoint with no API twin (React-cache scrape) so it is the most
  likely to break. Tasks cover it as a clearly separable sub-step that can be
  dropped without affecting the rest.
