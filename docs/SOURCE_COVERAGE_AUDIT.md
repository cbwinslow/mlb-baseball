# Source coverage audit — 2026-10-05

Owner goal: ingest every piece of historical and real-time data every lawful source offers, kept separate
per source in `raw`; overlap between sources is wanted, not avoided. This audit lists what `raw` holds and
what was left out, with the recorded reason. Counts are exact `count(*)` on production `mlb` (read-only,
2026-10-05); endpoint facts come from the connector code and live probes of `statsapi.mlb.com` by a
research agent (agent findings marked *probe*; not re-verified by a second pass). Decisions needed from the
owner are in the last section. This is evidence, not a roadmap: accepted gaps become an OpenSpec change.

## What `raw` holds today (exact row counts)

| Source | Tables / rows (largest) |
|---|---|
| Retrosheet | events 16.7M, plays 17.0M, batting 5.8M, fielding 5.3M, pitching 1.3M, game 211k, gamelog 234k, box_* 18k games, transactions 102k (frozen 2021) |
| Statcast | pitch 13.6M, plus 18 leaderboard tables (oaa, framing, sprint speed, arsenal, percentile, ...) |
| MLB Stats API | win_prob 12.6M, linescore 3.0M, transaction 833k, schedule 236k, playbyplay 185k (2026 only), roster 112k, draft 70k, boxscore ~169k lines (2026 only), game_context 164k, live_game 14k, plus 20 small reference tables (all populated) |
| FanGraphs | projection 468k, fielding 181k, split_batting 168k, split_pitching 135k, batting 109k, pitching 53k, prospects 19k, park factors, guts (local_research only) |
| Lahman | 27 tables, people 24k, batting 129k, fielding 174k, pitching 58k |
| Baseball-Reference | war_batting 127k, war_pitching 58k, season lines 2008+ (batting 16.6k, pitching 14.5k) |
| Chadwick Register | people 527k, links 27k |
| Markets | polymarket (event/market/outcome/snapshot ~1.1M), kalshi (~710k) |
| Other | news 8.7k |

No `raw.mlb_*` table is empty (planner estimates from `pg_stat_user_tables` read 0 for many of them and were wrong).

## MLB Stats API: what we leave out

The connector is **MLB-only (`sportId=1`) everywhere** and drops the rest on purpose or by default.

| Gap | Recorded reason | Cost to close (probe) | Notes |
|---|---|---|---|
| Per-pitch GUMBO feed (`game/{pk}/feed/live`: pitchData, hitData, playEvents, runners, credits, timestamps) | ADR-017 "Statcast does it better" | ~1 call/game, ~185k calls for 2008-2025 | Reason contradicts the owner goal; ADR-020 already reversed "skip if redundant" for endpoints but ADR-017 was not revisited. Pre-2008 pitch fields look like empty shells: check populated values before spending calls |
| Play-by-play, box score, umpires before 2026 | ADR-018/019 "duplicates Retrosheet" | ~75k box-score calls 1950-2025 | `FIRST_PLAYBYPLAY_YEAR = 2026` in `mlb_api.py` |
| Minor leagues (AAA, AA, High-A, A, Rookie, winter, independent, college) | none recorded | schedule ~20 calls/season; game feeds ~14k/season | Data starts about 2005 (probe); AAA carries full pitch/hit tracking |
| Schedule hydrates: weather, officials, broadcasts, decisions, seriesStatus | none recorded | ~125 calls (one per season) | Cheapest high-value gap |
| Stat groups fielding/catching/running; sabermetrics + statSplits stat types | none recorded | ~1 call per type/group/year | Only hitting+pitching, type `season` today |
| Stat leaders: only 10 hard-coded categories | ADR-020 "no documented enum" | small | |
| `highLow` | ADR-020 says broken | small | Probe got HTTP 200 on `/api/v1/highLow/player?sortStat=homeRuns&season=2024`: the recorded reason looks wrong (client path was malformed). `stats/streaks` still 404 |
| `meta` enum catalogs, `draft/prospects`, postseason series, milestones, minor-league transactions/teams/rosters | mostly "not stats" or none | small | |
| Live snapshot stores ~20 scalar fields, not the feed | design | | Source-faithful raw JSON of the feed is not kept |
| Raw JSON of the 1950+ analytics responses was never saved | n/a | | Why the ledger is empty (pipeline-recovery 9.5) |

## Other sources

- **fungo** (MIT, 1 maintainer, 3 stars, v2.0.0 2026-07-11): wraps Savant, MLB Stats API, FanGraphs, Baseball-Reference,
  Retrosheet, Lahman. We use it only for FanGraphs via the mobile-app JSON API (`okhttp/4.12.0`, the client Cloudflare
  does not block, ADR-288). Keep it pinned `<3`; single-maintainer dependency risk.
- **No free replacement for the MLB Stats API.** Paid providers (Sportradar, SportsData.io, Stats Perform, Genius) overlap
  heavily and need owner approval plus rights documentation.
- **Candidates:** minor leagues via the existing MLB connector (cheapest); Retrosheet/Chadwick completeness and attribution
  (`https://www.retrosheet.org/notice.txt`); Seamheads Negro Leagues (rights unverified); KBO/NPB (rights unverified).
- **Skills/plugins/MCP servers:** none worth adopting (thin wrappers over the same public endpoints, mostly unlicensed:
  etweisberg/mlb-mcp, alex-rimerman/statcast-mcp, machina-sports/sports-skills). `postgres-mlb` already covers querying.
- **Rights flag (unverified, from a search snippet):** MLB terms say "individual, non-commercial, non-bulk use" without
  written authorization. Keep Stats API / GUMBO / Savant under `local_research` and read the full terms before any
  public-facing use. See `docs/SOURCE_RIGHTS.md`.

## Owner rules recorded 2026-10-05

- No paid providers. Only free, lawful sources.
- The official MLB Stats API OpenAPI spec (190 paths, 490 schemas) exists in the older project at
  `~/workspace/mlb-baseball-ml/agents/mcp/baseball-mcp/mlb-statsapi-spec.json`; its origin/terms are
  unverified, so it is a checklist for planning, not yet a committed repo file.
- The 1950+ win-probability responses were never saved to disk (searched: `mlb` and every other
  database on the server, `downloads/`, `/mnt/storage`, the older project). The load (2026-07-28/29)
  predates the artifact staging commit (2026-08-09). A possible copy on the `cbwlap1` database
  (PostgreSQL 17, port 5433) is being checked.

## Owner decisions needed

1. Reopen ADR-017/018/019: ingest the full GUMBO feed and pre-2026 play-by-play/box scores as separate raw copies?
2. Add minor leagues (start with schedules, rosters, transactions, teams)?
3. Add the cheap hydrates, stat groups, `highLow`, `meta` first (small, ~hundreds of calls)?
4. Run the 1950+ analytics backfill (also saves raw JSON, closes ledger task 9.5)?
5. Rights check for Seamheads / KBO / NPB before any ingest.
