# Data Sources

All sources below are free or free-tier. No paid feeds without an explicit decision recorded here.

## Phase 1 — core ingestion (build first)

| Source | Provides | Cost | Access | Notes |
|---|---|---|---|---|
| **Retrosheet** | Play-by-play (177 cols) + per-game/per-player batting, pitching, fielding, team stats, game info, rosters, 1898–present | Free | Direct per-year zip (`retrosheet.org/downloads/{year}/{year}csvs.zip`), fully scriptable | Official Retrosheet's own pre-parsed CSV product — seven properly-headered CSVs per year, no parsing tool needed. Superseded an earlier version of this connector that cloned the raw event files (`chadwickbureau/retrosheet`, a third-party mirror) and shelled out to the Chadwick `cwevent` CLI tool to parse them; abandoned once this richer, simpler, more authoritative source was found — see `docs/DECISIONS.md`. Coverage starts at 1898 for this product specifically (the raw event files go back to 1871, but this pre-parsed CSV product doesn't). |
| **Retrosheet game logs** | One row per game, 161 fields (scores, umpires, managers, starting lineups), 1871–present | Free | Direct per-year zip (`retrosheet.org/gamelogs/gl{year}.zip`), fully scriptable | Older, wider-coverage Retrosheet product (back to 1871, vs. the main CSV product's 1898). Headerless — field layout is fixed and documented at `retrosheet.org/gamelogs/glfields.txt`, hardcoded in `retrosheet_gamelog.py` after verifying against real downloaded data, not just the doc. |
| **Retrosheet reference files** | Ballpark codes, team ID history, player/manager/coach biographical data, family relations | Free | Static whole-file downloads (`parkcode.txt`, `TEAMABR.TXT`, `biofile.zip`), fully scriptable | Not per-year — bootstrap and update are the same full reload, like the Chadwick register. `TEAMABR.TXT` is headerless; layout confirmed against `retrosheet.org/TeamIDs.htm` and verified against the real file. |
| **Chadwick Bureau Register** | Canonical player ID crosswalk (Retrosheet/MLBAM/Baseball-Reference/FanGraphs IDs) | Free | CSV on GitHub (`chadwickbureau/register`) | Needed to join across every other source — build this early. |
| **Lahman Database** | Season-level batting/pitching/fielding/team/awards/salary/HOF stats, 1871–present | Free | Manual download (see below), CC BY-SA | Good backfill for pre-Statcast eras. Current release isn't scriptable — see the manual step. |
| **MLB Stats API** (`statsapi.mlb.com`) | Schedules, live game state, boxscores, rosters, standings | Free, public, unauthenticated | JSON REST | Undocumented-but-stable public API; rate-limit politely, cache responses. |
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
