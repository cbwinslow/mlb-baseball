# `fangraphs.py` DOX

## Purpose

Own FanGraphs' public **bulk** data — season batting/pitching/fielding
leaderboards, Guts! constants, park factors, THE BOARD prospect rankings, a
curated set of league-wide split leaderboards, and every preseason /
rest-of-season projection system — landed source-faithful into `raw.fangraphs_*`.
Both a research source and an independent cross-validation source (its WAR/wOBA
framework is computed differently from Baseball-Reference's). It does not own
canonical identities, formulas, or model features.

Reached through **`fungo`** (`fungo.fangraphs`), not `pybaseball` — see ADR-288.

## Ownership

Implementation: `fangraphs.py`.

Primary outputs:

- `raw.fangraphs_batting` / `raw.fangraphs_pitching` / `raw.fangraphs_fielding`
- `raw.fangraphs_guts`
- `raw.fangraphs_park_factors` / `raw.fangraphs_park_factors_handedness`
- `raw.fangraphs_prospects`
- `raw.fangraphs_split_batting` / `raw.fangraphs_split_pitching`
- `raw.fangraphs_projection`

Public connector capabilities: `bootstrap()`, `update()`, `health_check()`.

## Source / Library Contract

- Transport/parser: `fungo>=2.0,<3` (MIT). `fungo.fangraphs` calls FanGraphs'
  mobile-app JSON API (`https://www.fangraphs.com/api/...`).
- **The `okhttp/4.12.0` exemption is load-bearing.** Cloudflare
  TLS-fingerprint-blocks every generic HTTP client on fangraphs.com; the one
  exemption `fungo` rides is the FanGraphs mobile app's client
  (`User-Agent: okhttp/4.12.0`). If it is withdrawn, `fungo` raises
  `FangraphsError` naming the condition on the 403. The connector re-raises
  it (never retries again) so `mlb doctor` goes red. **The fix is a `fungo`
  upgrade, not a local patch** — do not "fix" it by retrying.
- `fungo` does its own bounded exponential-backoff retry (stdlib `urllib`, 3
  attempts, `2**attempt` sleeps) on 5xx/network/timeout and raises immediately
  on 4xx. `net.call_with_retry` only catches `requests` exceptions and is
  **not** used here.
- Param traps handled inside `fungo` (documented here so a maintainer reading
  raw responses is not surprised): `get_leaders`' `season` is the END year and
  `season1` the START (inverted); `month` is a split code, not a calendar
  month; `ind=1` gives one row per player-season, `ind=0` aggregates a span
  (server-side aggregation of long spans has historically failed — the
  connector always uses `ind=1` and loops seasons).
- `get_leaders` is called with `ind=1, qual=0` (everyone, not just qualified —
  the raw layer must not be lossy).
- `pybaseball`'s FanGraphs path stays permanently 403 and is never substituted
  here (ADR-288, `docs/DATA_SOURCES.md`).
- Repository source-rights/profile metadata is authoritative: FanGraphs is
  `local_research` only (`docs/SOURCE_RIGHTS.md`), and `source_profiles`
  blocks this connector under any other profile before a request is made.

## Grain / Table Contract

### Season leaderboards

- `raw.fangraphs_batting` / `_pitching` / `_fielding` — one row per
  player-season (`ind=1`), fetched one season at a time.
- `_season` is added and is the scoped-replace key.
- `bootstrap()` loops `LEADERBOARD_FIRST_YEAR` → current, skipping past seasons
  already loaded (`season_already_loaded`); `update()` reloads the current
  season only.
- Full available history. Advanced columns come back **null** for early
  seasons (before FanGraphs computes them) — preserved as genuine nulls,
  never zero-filled. The real observed earliest season per board is recorded
  in the "Observed coverage" section below after a real bootstrap.
- The pitching board is ~540 columns and includes the Stuff+ (`sp_*`) and
  PitchingBot (`pb_*`) families — none of it membership-gated. Kept in full.

### Reference boards

- `raw.fangraphs_guts` — `get_guts_constants()` returns all seasons in one
  call; **whole-table replace** every run. All-string values (`fungo` scrapes
  `guts.aspx` with stdlib `html.parser`).
- `raw.fangraphs_park_factors` / `_park_factors_handedness` — per season,
  `_season` scoped-replace.
- `raw.fangraphs_prospects` — THE BOARD, per season, `_season` scoped-replace.

### Curated splits

- `raw.fangraphs_split_batting` / `_split_pitching` — a **curated** set of
  league-wide splits (`CURATED_SPLITS`: vs LHP/RHP, home, road, six calendar
  buckets). `fungo` position is `"B"` / `"P"`.
- Replace key is a compound `_scope` = `"{season}|{split}"`; `_season` and
  `_split` are kept as convenience columns.
- The full 292-code `SPLIT_CODE_TABLE` and any per-player-only FanGraphs
  endpoint are **out of scope** (ADR-020 / ADR-024 combinatorial rationale).

### Projection snapshot history

- `raw.fangraphs_projection` — every system in `fungo.PROJECTION_SYSTEMS`
  (preseason) and `ROS_PROJECTION_SYSTEMS` (rest-of-season), for `bat` and
  `pit`.
- **Append-only.** Bookkeeping columns: `_projection_system`, `_stat_group`,
  `_horizon` (`preseason` / `ros`), `_captured_date` (UTC date), `_row_hash`
  (md5 of every non-`_` column).
- **Change detection:** `_load_projections` reads each
  `(_projection_system, _stat_group, playerid)` key's most recent stored
  `_row_hash` and appends a new snapshot only for keys whose hash moved. An
  unchanged projection does not accumulate duplicate rows. This is the
  ADR-048 probable-pitcher pattern, applied so the history of a
  constantly-moving projection is retained without unbounded growth.
- Append identity: `(_projection_system, _stat_group, playerid, _captured_date)`.
  Rows with a null/blank `playerid` are dropped (cannot track history); a
  stray duplicate `playerid` inside one system keeps the first.

## Runtime / Failure Contract

- Roughly one HTTPS request per season per board on `bootstrap()`; `update()`
  is the current season for every board + one projection snapshot pass
  (~60 requests).
- `_run_unit` isolates each load: commit on success, roll back + log + skip on
  failure — one board/season/split's network hiccup does not discard the
  run's committed progress (same shape as `bref._load_season`).
- `_load_projections` isolates per `(system, stat_group)`.
- Not a high-frequency source. `health_check()` uses `check_table_has_rows` on
  the core tables + `check_last_run` + `check_recent_run(SOURCE,
  FRESHNESS_THRESHOLD_MINUTES, mode="update")`, where
  `FRESHNESS_THRESHOLD_MINUTES = DAILY_FRESHNESS_THRESHOLD_MINUTES` (28h) —
  the daily `mlb update` is the freshness guarantee; the 6-hourly
  `scripts/fangraphs_update.sh` is projection-capture resolution, not
  freshness-gating.

## Point-in-Time / Research Semantics

- Season leaderboards are final/season-to-date source aggregates: valid as
  descriptive or validation data, **not** valid for an earlier game in the
  same season unless a true as-of reconstruction exists.
- FanGraphs WAR/wOBA is a source-defined metric computed differently from
  Baseball-Reference's. Preserve source values distinctly; disagreement with
  a project formula is evidence to investigate, not permission to overwrite.
- `raw.fangraphs_projection` is genuinely point-in-time by construction —
  `_captured_date` is the availability stamp. A projection row is only valid
  as a pre-event input for games on or after its `_captured_date`.

## Dependencies

- `fungo` (+ `curl_cffi`, transitive — `fungo.bbref` imports it at package
  load; this connector never calls `fungo.bbref`).
- pandas / psycopg through project loaders.
- `load_dataframe` (scoped + whole-table replace), `append_dataframe`,
  `season_already_loaded`.
- `track_run`, `get_connection` / `fetch_one`, `health` helpers.
- **Python ≥3.12** — `fungo` requires it; ADR-288 moved the project floor.

## Downstream Consumers

- None yet. Conforming FanGraphs IDs (`playerid` / `xMLBAMID`) or metrics into
  `core` / `gold` is deliberately separate follow-up work.

## Known Quirks / Decisions

- ADR-288: revived via `fungo` (not pybaseball, permanently 403); Python floor
  3.11 → 3.12; `curl_cffi` accepted as a transitive dep; projections stored as
  de-duplicated dated snapshots; `local_research` rights.
- The `okhttp/4.12.0` exemption is a single point of failure — accepted,
  documented, fails loud.
- `raw.*` columns are all `text` (schema derived from the DataFrame, no type
  inference — same as `raw.bref_*`). Downstream casts.
- Deliberately NOT built: `get_player_stats` / `get_game_log` (per player per
  season), the full 292-code split catalogue, minor-league leaderboards,
  RosterResource depth charts (`get_depth_chart` needs a hand-verified 30-team
  URL-slug table — `fungo.constants.TEAMS` has none, a wrong slug 500s — and
  returns a nested React-cache payload, not a leaderboard; MLB Stats API
  already covers rosters/probables).

## Observed coverage

First production bootstrap: **2026-09-10**, `mlb ingest fangraphs --mode
bootstrap` against `mlb`, `local_research` profile, ~28 min wall.

| Table | rows | span | notes |
| --- | ---: | --- | --- |
| `raw.fangraphs_batting` | 108,923 | 1871–2026 | `qual=0`; `wpa` / `wpa_pos` / `wpa_neg` distinct |
| `raw.fangraphs_pitching` | 52,973 | 1871–2026 | `k_bb` / `k_minus_bb_pct` / `k_per_bb_plus` distinct |
| `raw.fangraphs_fielding` | 180,956 | 1871–2026 | |
| `raw.fangraphs_guts` | 156 | all seasons | whole history in one call |
| `raw.fangraphs_park_factors` | 2,752 | 1901–2026 | basic board; deeper history than handedness |
| `raw.fangraphs_park_factors_handedness` | 750 | 2002–2026 | FanGraphs raises `FangraphsError` ("No Guts table found") for years it doesn't cover (pre-2002); the basic board is loaded independently so it isn't rolled back with the failed year |
| `raw.fangraphs_prospects` | 19,153 | 2010–2026 | THE BOARD; season-varying columns (`schema_drift_policy="ignore"`) |
| `raw.fangraphs_split_batting` | 167,835 | 2002–2026 | 10 curated splits |
| `raw.fangraphs_split_pitching` | 134,827 | 2002–2026 | 10 curated splits |
| `raw.fangraphs_projection` | 50,511 | snapshot | 8 preseason systems (27,303) + 8 RoS (23,208), `_captured_date` 2026-09-10 |

Advanced columns are null for early seasons — preserved as genuine nulls,
never zero-filled. Full-history bootstrap is one request per season per board
through `fungo`'s retry — a documented one-off, same shape as `statcast` /
`mlb_api`. The dominant cost is the split boards (25 seasons × 10 splits × 2).

## Work Guidance

- Before adding another `fungo.fangraphs` endpoint, check its shape (bulk /
  league-wide vs per-player), bulk cost, coverage, and overlap with existing
  sources.
- Keep source-defined FanGraphs WAR/wOBA separate from project-owned formulas.
- Preserve the curated-splits scope; do not enumerate all 292 codes without a
  demonstrated downstream need.
- If `fungo` is replaced or forked, parity-test columns, the Cloudflare access
  path, coverage, request volume, and the projection response shape first.

## Verification

For changes, verify:

- `tests/unit/test_fangraphs_transform.py` — `_fg_call` error boundary,
  `_projection_value_hash` stability, `_changed_projection_rows` filtering,
  `_projection_rows` id-skip/dedup/horizon tagging, curated-split constants;
- `tests/integration/test_fangraphs_load.py` — per-season scoped replace +
  idempotency for every board, guts whole-table replace, split compound-scope
  no-cross-delete, projection seed / unchanged-rerun-appends-nothing /
  moved-key-appends-one / horizon tagging, `bootstrap` multi-season + failure
  isolation, `update` current-season-only + idempotent, `health_check`;
- the profile guard rejects `mlb ingest fangraphs --profile public_safe`
  before any request;
- `ruff` + `mypy` on the connector and tests.

Use a real network call only for a deliberate bootstrap/parity/smoke check.

## Child DOX Index

No child DOX files. This is a leaf connector contract.
