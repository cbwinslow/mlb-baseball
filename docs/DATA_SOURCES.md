# Data Sources

All sources below are free or free-tier. No paid feeds without an explicit decision recorded here.

## Phase 1 — core ingestion (build first)

| Source | Provides | Cost | Access | Notes |
|---|---|---|---|---|
| **Retrosheet** | Play-by-play event files, box scores, 1901–present | Free | Bulk download (zip files per season) | License requires attribution; parse with Chadwick tools (`cwevent`, `cwgame`, open source) rather than reinventing a parser. |
| **Chadwick Bureau Register** | Canonical player ID crosswalk (Retrosheet/MLBAM/Baseball-Reference/FanGraphs IDs) | Free | CSV on GitHub (`chadwickbureau/register`) | Needed to join across every other source — build this early. |
| **Lahman Database** | Season-level batting/pitching/fielding/team stats, 1871–present | Free | CSV/SQLite download, CC BY-SA | Good backfill for pre-Statcast eras. |
| **MLB Stats API** (`statsapi.mlb.com`) | Schedules, live game state, boxscores, rosters, standings | Free, public, unauthenticated | JSON REST | Undocumented-but-stable public API; rate-limit politely, cache responses. |
| **Baseball Savant / Statcast** | Pitch-level tracking data (velo, spin, exit velo, location), 2015–present | Free | CSV export via Savant's search endpoint | High volume — this is the ingestion component most likely to need real engineering care (chunked pulls, retries). |

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
