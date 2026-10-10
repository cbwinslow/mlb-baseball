# Conform decomposition design (task 5.1) — DRAFT

Status: proposed, written 2026-10-09 from a read-only pass over `mlb_baseball/conform.py`
(2,154 lines) and `conform.py.dox.md`. Destinations below are proposals; each is confirmed
by reading the function body when its task (5.2) starts. Nothing here changes behavior.

## What conform does today

`conform.run()` truncates and fully rebuilds 11 `core` tables in one transaction, in a fixed
order that is part of its correctness (see the DOX sidecar): team, player, venue,
team_franchise, team_alias, game, then game_pk and team-id backfills, standings, play, pitch,
market, player_war. A full run took about 47 minutes on 2026-10-08.

Already named `.sql` files (via `read_sql`): the main inserts for team, venue, franchise and
player. Still inline SQL strings: games, spring games, all backfills, standings, plays,
pitches, win probability, player_war, aliases, and the market lookups.

## Direction (answers to the owner's questions)

- **Storage:** `raw` and `core` stay in PostgreSQL (decision 1, ADR-287): constraints,
  transactions and cross-source identity need it. DuckDB holds features and analysis. Whether
  *gold* statistics move to DuckDB is decision 4, settled by measurement, not here.
- **Breaking up the big SQL:** yes, as named `.sql` files run in the same order, one table at
  a time, each with a run-twice test and a parity check against the old writer. Use SQL
  functions (`IMMUTABLE`) only for pure reusable logic. Do not rewrite wholesale.
- **Expanding `core`:** only metrics-first (decision 10). `conform` reads 30 of 150 raw
  tables. The other 120 are not automatically gaps: some exist for tie-out comparison. A raw
  table is added to `core` only when a chosen metric needs a field from it.
- **SQLMesh:** decided by the spike (task 3.2), judged against the ADR-297 upsert and
  stable-id requirement. Until then the work above does not depend on it.

## Per-function destination (proposed)

| Function | Today | Proposed destination |
| --- | --- | --- |
| `_check_prerequisites` | Python | stay Python |
| `_build_teams`, `_build_venues`, `_build_team_franchises`, `_build_players` | `.sql` + Python | already named SQL; add run-twice tests if missing |
| `_build_team_aliases` | inline SQL + Python seed list | named SQL; seed list stays a reviewed data file |
| `_build_games` (192 lines) | two inline inserts: Retrosheet games, then MLB API games | two named SQL files (`conform_game_retrosheet.sql`, `conform_game_mlb.sql`); keep every data-quality comment, each records a real bug |
| `_build_completed_spring_games` | one inline insert, skips if table absent | named SQL; keep the skip-with-message behavior |
| `_backfill_game_pk*`, `_backfill_mlb_team_id`, `_backfill_team_ids_via_mlb_id` | inline SQL, ordered passes | named SQL per pass; order stays in Python (evidence order matters) |
| `_build_standings` | one inline insert | named SQL; keep the `-` handling (games-back `-` = 0, wildcard-rank `-` = NULL) |
| `_build_plays` | two inline inserts (Retrosheet events, MLB play-by-play), each skips if table absent | two named SQL files; keep the de-duplication of 1,872 Negro League games published twice |
| `_backfill_win_probability` | separate UPDATE (must stay separate: a LEFT JOIN would make the optional win-prob table mandatory) | named SQL |
| `_build_pitches` | one inline insert, LEFT JOIN game on purpose | named SQL; keep the LEFT JOIN (an inner join once dropped 18.9% of pitches) |
| `_build_player_war` | two inline inserts (batting, pitching) | two named SQL files; keep the LEFT JOIN so unmatched players stay as NULL |
| `_build_market` + Polymarket/Kalshi row builders | Python (parses repr-like text, PIT lookup) | stay Python; high PIT-leakage risk, needs dedicated tests |
| `_drop_bulk_indexes`, `_rebuild_bulk_indexes`, `_timed`, `run` | Python | stay Python; `_timed` reviewed under task 5.4 |

## Order of work

1. Confirm destinations by reading each body (this table becomes the checklist).
2. Extract one table at a time, simplest first (spring games, standings, player_war), then
   games and the backfills, then plays/pitches. Market last.
3. After each: run-twice test, row/value parity against the old writer on a disposable
   database, update `conform.py.dox.md`.
4. Tighten `scripts/lint_sql_ownership.py` as tables leave Python (task 5.3).

## Open points

- Which of the 99 raw tables with no reader outside ingest are needed by a chosen metric
  (task 0.5 produces this list).
- Whether per-step audit records (task 5.4) replace `_timed`.

## Findings from reading the bodies (2026-10-09)

- **Team matching is inconsistent.** The MLB-API half of `_build_games` matches teams by the
  string `city || ' ' || nickname`, while spring games and standings match by the numeric
  `mlb_team_id`. The later `_backfill_*` passes exist partly to repair that. Moving the
  numeric match earlier could remove passes, but only with parity proof (order is
  correctness-critical per the DOX sidecar).
- **Each builder skips quietly when its raw table is absent** (prints a message, returns 0).
  The named SQL steps must keep that, or a partial bootstrap will start failing.
- **The long comments are the specification.** Dozens record real data bugs (uncertain
  attendance, sentinel values, casing). They move with the SQL, verbatim.
- **The five backfills are one identity chain, not five independent fixes.** Each is a
  set-based `UPDATE` (pure SQL, no Python logic), but each feeds the next:
  1. `_backfill_game_pk`: match schedule rows to games by date, team name and game number;
     assign only when every terminal schedule row maps to exactly one game.
  2. `_backfill_mlb_team_id`: for games with a `game_pk`, take the majority vote of MLB team
     IDs per `core.team` (a 2004 hurricane relocation is outvoted noise, by design).
  3. `_backfill_game_pk_via_mlb_team_id`: repeat step 1 using the numeric IDs.
  4. `_backfill_game_pk_via_exact_final_score`: last resort for doubleheader numbering
     disagreements; requires date, both team IDs and both final scores to match one game.
  5. `_backfill_team_ids_via_mlb_id`: fill still-NULL team IDs (for example the Athletics'
     2025 move to a bare "Athletics" name) from the step 2 crosswalk.
  Destination: one named `.sql` file per pass, numbered in order, with the order kept in one
  Python list. Test: run the chain twice (second run changes nothing) and compare resulting
  `game_pk` and team-ID coverage with the old code on the same input.
- **`core` carries a thin slice of the biggest tables.** `core.pitch` has 19 columns from
  `raw.statcast_pitch` (122); `core.play` has 19 from `raw.retrosheet_event` (168) and
  `raw.mlb_playbyplay` (22); `core.game` has 26 from `raw.retrosheet_gameinfo` (45). Per
  decision 10 this is not automatically a gap: the decision for each missing column comes from
  the metric list (task 0.5), not from the column count. Spin axis, pitch location, base
  state, fielder and count fields are the likely early candidates.
- **Index handling is a measured optimization**, kept as is (DOX sidecar: do not reintroduce
  per-builder truncation).
- **Market prices ignore the new price history.** `_build_market` resolves each market's
  pre-game probability only from `raw.polymarket_snapshot` and `raw.kalshi_snapshot` (the
  15-minute captures that began recently). It never reads `raw.polymarket_price` (about 604M
  rows) or `raw.kalshi_candle` (about 213M rows), the full history the odds backfill just
  loaded. The code comment says the history "hasn't been owner-triggered yet"; it now has.
  So for older games `implied_probability` is NULL even though a pre-game price exists. Fixing
  this is a new feature, not a refactor: it needs its own change, the existing strict-before-
  game-start rule, and PIT/leakage tests. It also suggests moving the lookup into SQL
  (a `LATERAL` latest-before query), since the current Python loads every snapshot into memory.
- **Market stays Python for now**, for the reasons in the table, but this lookup is the
  first candidate to move once the PIT tests exist.
