# Data Sources

All sources below are free or free-tier. No paid feeds without an explicit decision recorded here.

## Phase 1 — core ingestion (build first)

| Source | Provides | Cost | Access | Notes |
|---|---|---|---|---|
| **Retrosheet** | Play-by-play (177 cols) + per-game/per-player batting, pitching, fielding, team stats, game info, rosters, 1898–present | Free | Direct per-year zip (`retrosheet.org/downloads/{year}/{year}csvs.zip`), fully scriptable | Official Retrosheet's own pre-parsed CSV product — seven properly-headered CSVs per year, no parsing tool needed. This is the fast/pre-parsed path; `retrosheet_event` below covers the raw event files as the source-of-record. Downloads land on disk first (`downloads/retrosheet/`, JSON manifest) before parsing — see `mlb_baseball/manifest.py`. Coverage starts at 1898 for this product specifically. |
| **Retrosheet raw event files** | Per-play records (via `cwevent`) and per-game records (via `cwgame`), parsed from Retrosheet's own raw `.EVA`/`.EVN`/`.EVF`/`.EVR` (+ `.EDA`/`.EDN` deduced) files. Full play-by-play 1910–2025, plus post-season (1903+), All-Star (1933+), and Negro League play-by-play (1935–1949 + notable pre-1937 games) | Free | Multi-year decade zips (`retrosheet.org/events/{decade}seve.zip`) + `allpost.zip`/`allas.zip`/`allevr.zip`, fully scriptable | The source-of-record product — raw event files are what Retrosheet itself treats as authoritative; re-parsing locally (via the already-installed `cwevent`/`cwgame` CLI tools, not the `pychadwick` pip package, which fails to build — see ADR-004) avoids permanent dependence on Retrosheet's own CSV-generation choices. Kept alongside the CSV product above, not instead of it. Box-score-only coverage (pre-1910, Negro League box scores) is `retrosheet_box` below, not this connector. |
| **Retrosheet box scores** | Per-game, per-player batting/fielding/pitching lines (via `cwbox`), for games that only ever exist as box scores: 1871/1872/1874 NA seasons, 1898–1909, and Negro League games not covered by `retrosheet_event`'s play-by-play (1903–1961) | Free | `1871box.zip`/`1872box.zip`/`1874box.zip` (self-contained) + `1890sbox.zip`/`1900sbox.zip`/`allebr.zip` (need team/roster files constructed — see ADR-012), fully scriptable | Closes the coverage gap `retrosheet_event` documents but doesn't fill. `cwbox` needs a real (not empty) `TEAM{year}` file to resolve team codes/names, unlike `cwevent`/`cwgame` — constructed from Retrosheet's own `TEAMABR.TXT`/`biodata.zip` team registries, with real roster files pulled from `rosters.zip`, per Retrosheet's own documented requirement (retrosheet.org/datause.html). Not covered: player handedness detail and the supplementary doubles/triples/stolen-base/double-play lists `cwbox` also emits — see ADR-012. |
| **Retrosheet game logs** | One row per game, 161 fields (scores, umpires, managers, starting lineups), 1871–present | Free | Direct per-year zip (`retrosheet.org/gamelogs/gl{year}.zip`), fully scriptable | Older, wider-coverage Retrosheet product (back to 1871, vs. the main CSV product's 1898). Headerless — field layout is fixed and documented at `retrosheet.org/gamelogs/glfields.txt`, hardcoded in `retrosheet_gamelog.py` after verifying against real downloaded data, not just the doc. |
| **Retrosheet reference files** | Ballpark codes, team ID history, player/manager/coach/umpire biographical data, family relations | Free | Static whole-file downloads (`parkcode.txt`, `TEAMABR.TXT`, `biofile.zip`, `biodata.zip`), fully scriptable | Not per-year — bootstrap and update are the same full reload, like the Chadwick register. `TEAMABR.TXT` is headerless; layout confirmed against `retrosheet.org/TeamIDs.htm`. `biodata.zip` is a newer bundle Retrosheet also distributes — compared byte-for-byte against `biofile.zip`: `biofile0.csv`/`relatives.csv` are identical in both (loaded once), but `biodata.zip` adds `managers0.csv`/`umpires0.csv` (new tables) and `teams0.csv`/`coaches0.csv` (different column layout than the existing tables, landed separately rather than merged). |
| **Retrosheet rosters** | One row per player-team-season, 1871–2025 | Free | Whole-file download (`retrosheet.org/rosters.zip`, ~4,100 per-team-season files inside), fully scriptable | Team and season aren't repeated inside each file — parsed from the filename. Does not load the zip's bundled `UMPIRES{year}.txt` files (redundant with `biodata.zip`'s umpire biographical data). |
| **Retrosheet schedules** | Planned schedule, one row per scheduled game, 1877–2026, including postponement reason and makeup date | Free | Whole-file download (`retrosheet.org/schedule/schedule.zip`, one headered CSV per year inside), fully scriptable | |
| **Retrosheet transactions** | Trades, sales, releases, waivers, free agency, DL/IL, draft picks | Free | Whole-file download (`retrosheet.org/transactions/tranDB.zip`) | **Frozen by Retrosheet as of November 26, 2021** — ongoing maintenance moved to Baseball-Reference. `update()` re-runs the same full load (harmless/idempotent) rather than pretending this source stays current; nothing after the freeze date without a future Baseball-Reference or MLB Stats API connector. |
| **Chadwick Bureau Register** | Canonical player ID crosswalk (Retrosheet/MLBAM/Baseball-Reference/FanGraphs IDs) | Free | CSV on GitHub (`chadwickbureau/register`) | Needed to join across every other source — build this early. |
| **Lahman Database** | Season-level batting/pitching/fielding/team/awards/salary/HOF stats, 1871–present | Free | Manual download (see below), CC BY-SA | Good backfill for pre-Statcast eras. Current release isn't scriptable — see the manual step. |
| **MLB Stats API** (`statsapi.mlb.com`) | Current-season schedule (incl. live game status) and standings | Free, public, unauthenticated | `statsapi` Python package (`MLB-StatsAPI` on PyPI, `toddrob99/MLB-StatsAPI` — 830+ stars, actively maintained, GPL-3.0) | Scoped to the current season only, not a historical backfill — Retrosheet already covers full history for schedules and completed-game results; this source's real value is the *current*, still-in-progress season and live status (Scheduled/Postponed/Cancelled) that Retrosheet's completed-game-only products don't have. Boxscores/rosters/full live game state deferred — see ADR-014 and `docs/ROADMAP.md`. |
| **Baseball Savant / Statcast** | Pitch-level tracking data (velo, spin, exit velo, location), 2015–present | Free | CSV export via Savant's search endpoint | High volume — this is the ingestion component most likely to need real engineering care (chunked pulls, retries). |

## Manual step required: Lahman Database

SABR distributes the current Lahman release only through a Box.com folder with no stable, scriptable download URL (confirmed: Box's API returns 401 without an app-registered OAuth token; anonymous downloads only work through the interactive web UI). This is a real constraint, not a shortcut — to bootstrap or refresh current-season Lahman data:

1. Open the current release folder: <https://sabr.box.com/s/y1prhc795jk8zvmelfd3jq7tl389y6cd> (linked from <https://sabr.org/lahman-database/>).
2. Download the whole folder as a zip (top-right download icon), or download it as directed on the page.
3. Save the zip into `downloads/` at the repo root, e.g. `downloads/lahman_1871-2025_csv.zip`. The connector globs `downloads/lahman*.zip` and picks the most recently modified match, so the exact filename doesn't matter.
4. Run `mlb ingest lahman --mode bootstrap` (or `update`) — it loads directly from the zip, no extraction needed.

If no local zip is present, the connector automatically falls back to a network source frozen at the 2021 season (a preserved fork of the since-deleted `chadwickbureau/baseballdatabank`, see `docs/DECISIONS.md`) and prints a clear warning — so a fresh clone still bootstraps with zero setup, just with stale data until someone does the manual step above.

`downloads/` is gitignored — never commit the zip itself, only the instructions for getting it.

## Phase 1b / stretch — prediction markets (once core pipeline pattern is proven)

| Source | Provides | Cost | Access | Notes |
|---|---|---|---|---|
| **Polymarket** | Market-implied probabilities for MLB game/event outcomes | Free | Public REST/GraphQL (Gamma/CLOB API), no auth needed for read | Structurally simple — a straightforward periodic API pull, good second connector to build once the ingestion pattern exists. |
| **Kalshi** | Market-implied probabilities for sports event contracts | Free tier | REST API, requires free account signup for API key | Read-only market data access; no trading integration planned. |

This pairing is a deliberate differentiator: it gives the project a free proxy for "the market's opinion" without a paid odds feed — comparable in spirit to what oddstrader shows, without oddstrader's licensing costs.

## Deferred — not in scope yet

- **Traditional sportsbook odds APIs** (e.g. The Odds API) — paid beyond a very limited free tier; revisit only if Polymarket/Kalshi coverage proves insufficient for the website.
- **FanGraphs** — some free leaderboards exist but scraping is ToS-sensitive; skip until there's a specific, justified need.

## Adding a new source

Before adding any connector: add a row to the appropriate table above (cost, access method, license/ToS note) in the same change that adds the code. `DATA_SOURCES.md` is the single source of truth for what the pipeline is allowed to pull from.
