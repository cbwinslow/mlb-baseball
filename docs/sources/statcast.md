# Baseball Savant / Statcast

Source page for pitch tracking and season leaderboards. Same layout and ownership rules as [`mlb_api.md`](mlb_api.md): this page links to the owners of counts, contracts and rights instead of copying them.

| Question | Owner |
|---|---|
| Tables, rows, seasons, columns | [`RAW_INVENTORY.md`](../RAW_INVENTORY.md) (section `statcast`) |
| Offered vs. held vs. missing, with the fix command | `mlb coverage --source statcast` and `--source statcast_leaderboard` |
| Pitch connector contract (weekly chunks, scoped replace, resume, PIT) | [`statcast.py.dox.md`](../../mlb_baseball/connectors/statcast.py.dox.md) |
| Leaderboard connector contract | [`statcast_leaderboard.py.dox.md`](../../mlb_baseball/connectors/statcast_leaderboard.py.dox.md) |
| Column meanings | [`reference/statcast_glossary.md`](../reference/statcast_glossary.md) |
| Rights profile | [`SOURCE_RIGHTS.md`](../SOURCE_RIGHTS.md) (row "MLB Stats API and Baseball Savant/Statcast") |
| Why pitch tracking lives only here, not in the MLB API connector | ADR-017 in [`DECISIONS.md`](../DECISIONS.md) |

Facts checked 2026-10-06 (live response headers, `pybaseball` documentation, connector constants).

## Access

- **Host:** `baseballsavant.mlb.com`, the same MLB-owned family as the Stats API. The CSV search endpoint (`/statcast_search/csv`) answered 200 with `content-type: application/download` and `cache-control: public, max-age=1200, s-maxage=3600`.
- **Auth:** none. **Documentation:** Savant's own search page and CSV column glossary; no API contract is published.
- **Client:** `pybaseball` (`statcast()` for pitches, leaderboard functions for the season products), wrapped by project retry and timeout code.
- **Row limit per request:** `pybaseball` documents "30000 rows" per Savant query and itself splits any range longer than about 5 days into smaller requests, then joins them. Our 7-day weekly window is therefore several Savant requests inside one library call. A week holds more than 30,000 pitches, so correctness depends on that internal splitting. `mlb coverage` checks that every game date has pitch rows; it does not check that a day's count is complete, so a day truncated by the cap would pass. Open question for a later probe: compare per-day pitch counts with games played.
- **Rate limit:** none published by Savant. `pybaseball` (2.2.7) has no throttle and no retry for Savant; the only built-in throttle in the library is for Baseball-Reference. Politeness and retry are ours: shared retry/backoff around every call, plus a `CHUNK_PAUSE_SECONDS` (1.0 s) pause between weeks. Savant pitches and leaderboards hit the same host, so do not run both aggressively at once.
- **Format:** CSV, loaded source-faithfully as text.

## Rights

Same MLB Terms of Use as the Stats API (prohibits automated collection without permission), so `local_research` only. The record is `SOURCE_RIGHTS.md`; update it there.

## What the source offers

### Pitch level (`raw.statcast_pitch`)

One row per pitch. Two real measurement eras, preserved as they are:

| Era | Seasons | What exists |
|---|---|---|
| PITCHf/x | 2008-2014 | location, velocity, movement; most Statcast-only fields are genuinely NULL |
| Statcast | 2015 onward | adds spin, exit velocity, launch angle, hit distance, expected stats, win-probability estimates |
| Bat tracking | 2023 onward | swing speed and related bat fields appear only in later seasons |

The raw table is about 119 columns (ADR-017). Missing early-era fields are missing measurement, not zero.

### Season leaderboards (18 tables, `statcast_leaderboard`, from 2015)

| Kind | Tables |
|---|---|
| Inputs not present in pitch rows | sprint speed, pop time, catcher framing, outfielder jump, outs above average (+ by direction), catch probability, running splits, pitch spin direction |
| Official aggregates kept for cross-checking | batter and pitcher exit velocity, expected stats, percentile ranks, pitch arsenal (+ pitcher arsenal stats) |

Exact table names and row counts: `RAW_INVENTORY.md`. The list of fetchers is `SIMPLE_LEADERBOARDS` in the connector, which is also what `mlb coverage` reads, so a new leaderboard shows up there automatically.

## Coverage boundaries

| Product | First year | Unit `mlb coverage` checks | Resume rule |
|---|---|---|---|
| Pitches | 2008 (`FIRST_STATCAST_YEAR`) | game dates | past seasons skipped once loaded; current season refreshes |
| Leaderboards | 2015 (`FIRST_YEAR`) | seasons | one call per season per product |

Known limit to keep in mind: a partly loaded past season is skipped on rerun (`season_already_loaded`), so the idempotent ingest command cannot repair it. `mlb coverage` states this in the entry's caveat instead of printing a fix that would do nothing.

## Not saved before loading

Statcast and the leaderboards are fetched into memory and loaded directly; the response is not kept on disk, so a load cannot be replayed or independently proven (`SOURCE_COVERAGE_AUDIT.md`, "Download and ingestion machinery"). Task 0.11 of `full-source-ingestion` deliberately leaves this connector unchanged unless a measured problem appears.
