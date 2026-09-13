## Why

FanGraphs is the one major source `docs/DATA_SOURCES.md` marks **BROKEN /
Deferred**: `pybaseball`'s FanGraphs path returns a hard HTTP 403 because
fangraphs.com now sits behind Cloudflare. That leaves a real gap — FanGraphs'
WAR/wOBA framework, its Guts! constants, its park factors, and the major
public projection systems (Steamer, ATC, THE BAT, ZiPS, …) have no home in the
warehouse, and the projection systems in particular are a moving series with no
history retained anywhere.

The `fungo` library (MIT, actively maintained, "Production/Stable") reaches
FanGraphs through its mobile-app JSON API using the one Cloudflare-exempt
User-Agent (`okhttp/4.12.0`). A live test on 2026-09-10 confirmed the leaders,
Guts!, park-factor, and projection endpoints all return real data with no auth.
The owner approved reviving FanGraphs as a source on that basis and asked to
land all available bulk data, retain history, and refresh it on a cron.

## What Changes

- **New `fangraphs` connector** (`mlb_baseball/connectors/fangraphs.py`),
  registered in `mlb_baseball/registry.py`, exposing `bootstrap()`,
  `update()`, and `health_check()` like every other connector. It calls
  `fungo.fangraphs`, not `pybaseball`.
- **New `raw.fangraphs_*` tables**, source-faithful (FanGraphs' native JSON
  columns, including the ~540-column pitching board with the Stuff+ `sp_*` and
  PitchingBot `pb_*` families):
  - `raw.fangraphs_batting` / `_pitching` / `_fielding` — season leaderboards,
    one row per player-season, full available history, per-season
    scoped-replace.
  - `raw.fangraphs_guts` — the Guts! wOBA/FIP constant table, full history in
    one call, whole-table replace.
  - `raw.fangraphs_park_factors` / `_park_factors_handedness` — per season,
    scoped-replace.
  - `raw.fangraphs_prospects` — THE BOARD prospect rankings, per season,
    scoped-replace.
  - `raw.fangraphs_projection` — every preseason and rest-of-season projection
    system `fungo` exposes, stored **append-only as a dated snapshot** so the
    evolution of a projection over a season is retained. A run that finds an
    unchanged snapshot for a key does not append a duplicate row.
  - A curated set of the most-used split leaderboards (`vs LHP` / `vs RHP`,
    home / road, monthly) in `raw.fangraphs_split_batting` / `_split_pitching`,
    per season, scoped-replace.
- **New dependency:** `fungo>=2.0` in `pyproject.toml`. It pulls in
  `beautifulsoup4` (already transitive) and `curl_cffi` (new; a binary wheel,
  used only by `fungo`'s Baseball-Reference code, which this connector does not
  call, but imported at package load).
- **Cron refresh.** `fangraphs` joins `mlb update`, so the daily
  `scripts/mlb_daily_update.sh` already refreshes it. Projections update more
  than once a day, so a dedicated `scripts/fangraphs_update.sh` (flock + log,
  same shape as `scripts/mlb_api_update.sh`) runs `mlb ingest fangraphs --mode
  update` on a few-times-daily cadence to capture projection snapshots as they
  move — bounded, with duplicate-snapshot suppression.
- **Rights + docs, same change.** A new FanGraphs row in
  `docs/SOURCE_RIGHTS.md` (`local_research` only, fail-closed for
  `public_safe` — same posture as Baseball-Reference-via-pybaseball); move
  FanGraphs out of the Deferred section of `docs/DATA_SOURCES.md` into the
  main table; a `fangraphs.py.dox.md` connector sidecar; a new ADR in
  `docs/DECISIONS.md`; add the new raw tables to `mlb doctor` health/coverage
  surfaces; `scripts/check_dox.py` baseline updated for the sidecar.
- **Explicitly out of scope** (documented, same combinatorial rationale as
  ADR-020 / ADR-024 for `get_splits` and awards history): the per-player,
  per-season endpoints `get_player_stats` and `get_game_log`; the full
  292-code split-leaderboard enumeration; minor-league leaderboards.
  **RosterResource depth charts** are also deferred (found during apply):
  `get_depth_chart` needs a hand-verified 30-team URL-slug table (FanGraphs'
  own `fungo.constants.TEAMS` has no slug), it 500s on a wrong slug, and it
  returns a deeply nested React-cache payload (`dataRoster`, `dataLineups`,
  `dataBullpenUsage`, …) rather than a leaderboard — disproportionate schema
  work for v1, and MLB Stats API already covers rosters/probables. Each is a
  cheap follow-up if a downstream consumer needs it.

## Capabilities

### New Capabilities

- `fangraphs-ingestion`: acquiring FanGraphs' public bulk data (season
  batting/pitching/fielding leaderboards, Guts! constants, park factors,
  projection systems, prospect board, depth charts, common splits) into
  source-faithful `raw.fangraphs_*` tables via the `fungo` library, with
  defined bootstrap/update/snapshot semantics, idempotency, a rights profile,
  health checks, and a cron refresh.

### Modified Capabilities

- None. The statistic backbone, delivery, and downstream `core`/`gold`
  surfaces are unchanged by this proposal — it lands raw data only. Conforming
  FanGraphs identities/metrics into `core`/`gold` is deliberately separate
  follow-up work.

## Impact

- **New code:** `mlb_baseball/connectors/fangraphs.py`,
  `mlb_baseball/connectors/fangraphs.py.dox.md`, `scripts/fangraphs_update.sh`,
  tests under `tests/`.
- **Modified code:** `mlb_baseball/registry.py` (register the connector),
  `mlb_baseball/cli.py` (only if the CLI needs the new source name — it reads
  `CONNECTORS`, so likely no edit), `mlb_baseball/doctor.py` /
  `mlb_baseball/health.py` usage for the new tables, `pyproject.toml`,
  `uv.lock`, `scripts/check_dox.py`.
- **New dependency:** `fungo` (+ `curl_cffi`). No paid feed.
- **Database:** new `raw.fangraphs_*` tables, auto-created by `load_dataframe`
  from the source columns — no migration file needed (same as `bref`).
- **Data rights:** FanGraphs enters at `local_research`; the `public_safe`
  export path stays fail-closed for it. No public artifact may use these
  tables without the lineage review `docs/SOURCE_RIGHTS.md` already requires.
- **Runtime:** one HTTPS call per season per board on bootstrap (~1 request ×
  ~150 seasons × a handful of boards, sequential, retried); `update()` reloads
  the current season plus a projection snapshot. Rides `fungo`'s own
  retry/backoff. fangraphs.com is its own server — no `_SAME_SERVER_GROUPS`
  entry needed.
