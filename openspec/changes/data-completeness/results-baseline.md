# Baseline results (2026-10-07, after PRs #347-#350, coverage run on main)

Report: `mlb coverage --missing-only`. 17 gaps at the first baseline; the wrong
expectations are fixed, the rest are classified below.

| Gap | Size | Class | Owner / fix |
|---|---|---|---|
| FanGraphs park factors | 1871-1900 (30 seasons) | repair (source serves them) | task 2.3, narrow loader needed |
| FanGraphs fielding | 2019 | repair | task 2.3, `mlb ingest fangraphs` |
| MLB linescores | 85 games, 2000-2024 | repair | task 2.1 |
| mlb_person, roster ids | 147 | repair | task 2.2 |
| mlb_person, box score / draft / transactions ids | ~144k | scope | `full-source-ingestion` 0.14 |
| mlb_team_history / mlb_venue ids | 1,798 teams / 351 venues | mostly scope (minor-league clubs); venues need a look | task 2.6 |
| Kalshi candles | 1,492 markets (2026) | repair (backfill) | task 2.5 |
| Polymarket price windows | 5,750 (2026) | repair (backfill) | task 2.5 |
| Statcast | 2 games, 2026 | repair, heals with nightly | task 2.4 |
| Register people | 43 ids | scope (Negro League 29, exhibition, umpires) | `negro-league-scope` |
| retrosheet_box manifest | 3 files show "downloaded" | self-heals at next retrosheet_box run | none |
| 46 raw tables with no expectation | written reasons exist | explained; 10 mlb_api season tables need a first-year probe | task 1.2 |

Open questions for the owner: Negro League scope; widening mlb_person beyond rosters.
Known limit: a game with only some of its pitches counts as held (54 games under 120 pitches).
