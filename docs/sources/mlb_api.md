# MLB Stats API (`statsapi.mlb.com`)

Source page: what the source offers, how to reach it, what we hold, and what we leave out. This page does **not** copy data that already has an owner; it links to it.

| Question | Owner |
|---|---|
| Which tables, how many rows, which seasons, which columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (generated; section `mlb`) |
| Offered vs. held vs. missing, with the fix command | `mlb coverage --source mlb_api` |
| Connector behaviour, timeouts, update/append rules | [`mlb_api.py.dox.md`](../../mlb_baseball/connectors/mlb_api.py.dox.md) |
| Rights profile | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) |
| Why gaps were left, decisions needed | [`SOURCE_COVERAGE_AUDIT.md`](../SOURCE_COVERAGE_AUDIT.md), ADR-017/018/019/020 in [`DECISIONS.md`](../DECISIONS.md) |
| Plan to close the gaps | `openspec/changes/full-source-ingestion/` |

Facts below were checked 2026-10-06 against live responses of the API, MLB's Terms of Use, and the community spec described under "Endpoint families".

## Access

- **Base URL:** `https://statsapi.mlb.com/api/v1/` (a few resources use `v1.1`, e.g. the live game feed). The community spec also lists `beta-statsapi.mlb.com` and `qa-statsapi.mlb.com`; we use only production.
- **Auth:** none. No API key, no sign-up.
- **Documentation:** MLB publishes none. Community references: the `statsapi` package wiki (`toddrob99/MLB-StatsAPI`) and a community OpenAPI file (see below).
- **Rate limit:** none published and none seen in response headers (no `X-RateLimit*` or `Retry-After` on a normal response). Our connector limits itself: finite timeouts, retry/backoff through shared networking code, bounded workers. Treat the real limit as unknown and stay polite.
- **Caching:** responses carry `cache-control: max-age=900, public, stale-while-revalidate=30, stale-if-error=86400` behind a CDN, so a repeated request within 15 minutes may return the same data. Live-game polling must account for that.
- **Format:** JSON. Every response has a `copyright` field.
- **Client:** the `statsapi` PyPI package (GPL-3.0) wrapped by project code. Its object model is not our schema.

## Rights

MLB's Terms of Use (last updated 2025-03-11) prohibit users from "us[ing] automated scripts to collect information from or otherwise interact with the MLB Digital Properties" and require written permission for most uses beyond personal, non-commercial use. We therefore hold this source under the `local_research` profile only: never `public_safe`, never in published datasets, never a public-product input. The row in `SOURCE_RIGHTS.md` is the enforced record; update it there, not here. Task 0.4 of `full-source-ingestion` records the full wording and the owner's sign-off.

## What the source offers

### Levels (`sportId`)

Confirmed live from `/api/v1/sports`:

| sportId | Level | | sportId | Level |
|---:|---|---|---:|---|
| 1 | MLB | | 22 | College |
| 11 | Triple-A | | 31 | NPB (Japan) |
| 12 | Double-A | | 32 | KBO (Korea) |
| 13 | High-A | | 51 | International |
| 14 | Single-A | | 52 | Olympic |
| 16 | Rookie | | 61 | Negro Leagues |
| 17 | Winter leagues | | 586 | High school |
| 23 | Independent | | 576 | Women's professional softball |

Also listed: 21 (Minor League Baseball umbrella), 509/510/6005 (international amateur). **The connector uses `sportId=1` only.** Whether the other levels carry data, and from which year, is unprobed for most (task 5.1).

### Endpoint families

The community OpenAPI file (version 2.0.0, 190 paths, 490 schemas) groups them as below. We hold a copy outside this repo; its origin and licence are unverified (task 0.3), so it is a planning checklist, not a committed file.

| Family | Paths (examples) | Used today? |
|---|---|---|
| Schedule | `/schedule` (+ `postseason`, `postseason/series`, `games/tied`, `trackingEvents`) | `/schedule` yes, no hydrates; others no |
| Game | `/game/{pk}/feed/live` (GUMBO), `playByPlay`, `linescore`, `boxscore`, `winProbability`, `contextMetrics`, `content`, `feed/color` (22 paths) | playByPlay, boxscore, winProbability, linescore, contextMetrics yes; GUMBO no |
| Teams / people / venues | `/teams`, `/teams/{id}` (+ `roster`, `alumni`, `personnel`, `stats`, `leaders`), `/people`, `/people/{id}/stats`, `/venues` | yes (reference tables) |
| Standings / stats | `/standings`, `/stats` (+ `search`, `metrics`), `/stats/leaders`, `streaks`, `highLow` | standings and a few stat calls yes; rest no |
| Draft / awards / transactions | `/draft/{year}`, `/draft/prospects`, `/awards/{id}/recipients`, `/transactions` | draft, transactions yes; prospects, recipients no |
| Tracking | `/batTracking/game/{pk}/{playId}`, `/hitTrajectories`, `trackingVendors`/`Versions` | no |
| Other | weather, broadcasts, uniforms, milestones, home run derby, all-star ballots, props, video/review | no |
| Reference enums | `gameTypes`, `pitchTypes`, `pitchCodes`, `positions`, `statTypes`, `statGroups`, `leagueLeaderTypes`, `eventTypes`, `transactionTypes`, `rosterTypes`, ~40 more (`meta`) | no (task 1.1) |

Do not read "no" as "worthless": each family needs a use case, rights check, coverage probe and request-cost estimate before ingest (see the connector sidecar's work guidance).

### Hydrations

`hydrate=` expands related objects in one response. Verified: `/schedule?sportId=1&date=2024-07-04&hydrate=weather,officials,decisions,broadcasts` adds `weather`, `officials`, `decisions` and `broadcasts` to each game. This is the cheapest high-value gap: about one call per season instead of one per game.

## Coverage by product (what the connector holds)

Source of truth for the numbers is `mlb coverage --source mlb_api`; the table below records the boundaries and why.

| Product | Table(s) | Starts | Scope in connector | Note |
|---|---|---|---|---|
| Schedule | `raw.mlb_schedule` | 1901 | per season | historical rows may lack team names; filled from the season teams catalog |
| Standings | `raw.mlb_standing` | 1969 | per season | |
| Rosters | `raw.mlb_roster` | 1901 | per season | |
| Transactions | `raw.mlb_transaction` | about 2000 | per season | needs `force=True` in the client |
| Draft | `raw.mlb_draft` | 1965 | per year | |
| Win probability | `raw.mlb_win_prob` | 1950 | per game | raw responses not saved before 2026-08-09 |
| Linescore, game context | `raw.mlb_linescore`, `raw.mlb_game_context` | 1950 | per game | ledger tracks source gaps (`unavailable`) |
| Play-by-play, box score, umpires | `raw.mlb_playbyplay`, `raw.mlb_boxscore_*`, `raw.mlb_umpire` | 2026 (`FIRST_PLAYBYPLAY_YEAR`) | per game | earlier years skipped as "duplicates Retrosheet" (ADR-018/019), under review |
| Live game | `raw.mlb_live_game` | n/a | append-only snapshots | about 20 scalar fields, not the feed |
| Probable pitchers | `raw.mlb_probable` | n/a | append on change | forward-looking only |
| Reference | about 20 small tables (`sport`, `league`, `division`, `season`, `person`, `venue`, `team_history`, `award`, ...) | n/a | whole catalog | no countable total, so `mlb coverage` reports "no expectation" |

Identity: `game_pk` is MLB's game id. It is not our canonical game key; reconcile in conform.

## Verified 2026-10-07 (live probes and read-only queries)

- **Season reference and stat endpoints** (player pool, coaches, alumni, game pace, player and team stats, leaders): data is served for 2006, 2016, 2019, 2024, 2025 and 2026. The coverage report expects them from 2000 (`FIRST_REFERENCE_YEAR`; free agents 2001). Older years are sparse and unprobed. We are missing 2006 and 2017-2025 (task 2.8 of `data-completeness`).
- **Play-by-play and box scores before 2026** are deliberately not loaded: Retrosheet's event data covers 1900-2025 (208,693 games held) and 2026 is not in Retrosheet yet. Not byte-identical (MLB adds pitch-level fields; Statcast covers 2008 on), but the same plays. Retrosheet publishes box scores directly only to 1961; later ones derive from its events.
- **Ids:** the loader stores some ids as `17.0` in one table and `17` in another; coverage compares them without the `.0`.
- **Schedule team ids** with no row in `raw.mlb_team_history` are not clubs (All-Star sides, postseason seed placeholders, exhibition opponents, five Negro League clubs).

## Known gaps and open questions

The gap list, costs and recorded reasons live in `SOURCE_COVERAGE_AUDIT.md` ("MLB Stats API: what we leave out"); do not restate them here. The first-valid-year questions this page cannot yet answer belong to `full-source-ingestion` task 1.1 and, once probed, go into the Coverage table above and into `mlb_baseball/coverage/registry.py` so `mlb coverage` can compare them:

- first valid year per season-scoped reference endpoint (`attendance`, `coach`, `alumni`, `free_agent`, `game_pace`, `player_pool`, `player_stat`);
- which years populate pitch, hit and play-event fields in the GUMBO feed;
- first valid year per minor-league level.

## Live check result: schedule versus the API (2026-10-06)

`mlb coverage --table mlb_schedule --probe` asked the API for each season's game count (regular season and postseason, `sportId=1`) and compared it with `raw.mlb_schedule`: **108 of 126 seasons match exactly**. The 18 that differ are all 1920 to 1947 and are Negro League games, which the API now lists under the MLB level (team ids 14xx and 15xx). Examples: 1924 holds 1,238 games against 1,760 at the source (the 1,238 is exactly the American and National League count); 1930 matches. So the table holds some Negro League games in some years and none in others. That is a scope question for `openspec/changes/negro-league-scope` and the owner, not a loader fault to fix blindly.

Method note: the `statsapi` library returned one game more than the API for 1950, so the probe uses plain HTTP; the connector's own request path is not the reference for what the source offers.
