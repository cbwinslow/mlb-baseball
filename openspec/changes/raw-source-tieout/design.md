## Context

See `proposal.md` for motivation. Facts observed read-only on 2026-09-27:

- Retrosheet is loaded four ways into `raw`: Chadwick-parsed events
  (`retrosheet_event`, `retrosheet_game`), Retrosheet's own CSVs
  (`retrosheet_plays`, `retrosheet_gameinfo`, `retrosheet_batting`,
  `retrosheet_pitching`, `retrosheet_fielding`, `retrosheet_teamstats`), game logs
  (`retrosheet_gamelog`, `retrosheet_gamelog_post`), and Chadwick-parsed box
  scores (`retrosheet_box_*`). Rosters are `retrosheet_roster` and
  `retrosheet_allplayers`.
- Coverage differs: events 1900–2025, CSV plays 1898–2025, CSV batting
  1898–2025, game logs 1871–2025, box scores 1871–1961 only (box scores exist
  only where no event file does). Modern seasons therefore compare events against
  the CSVs and game logs, not box scores.
- For 2015–2025, events and CSV batting agree exactly on plate appearances,
  strikeouts and home runs. Game logs are regular season only and run lower on home
  runs by exactly the postseason total in `retrosheet_gamelog_post`.
- `core.play` and `core.game` are built by `conform.py` from these raw tables.
  `core.play` Retrosheet rows have null outs, counts and scores; that is a known
  property, not a defect for this change.
- Existing loader tests (`tests/integration/test_retrosheet_*_load.py`) prove that
  rows land, that a reload replaces only its own scope, and that missing input is
  handled. There is no integration test of `retrosheet_event` loading, and none
  compares two sources. `scripts/verify_mlb_boxscore_tie_out.py` and
  `scripts/verify_baseball_reference_tie_out.py` are the pattern for a read-only
  gate; `tests/unit/test_boxscore_tie_out.py` tests the boxscore one.
- `scripts/AGENTS.md`: reusable logic belongs in the package with tests; scripts
  stay narrow; DB targets are explicit.

## Goals / Non-Goals

**Goals:**

- A repeatable, read-only, loud gate with a written pass mark.
- Independent sources checked against each other, not against themselves.
- `core` checked against the raw tables it is built from.

**Non-Goals:**

- Changing, repairing or reloading any data, or any connector or `conform` code.
- Scheduling the gate in the daily job, or adding it to `mlb doctor`.
- Comparing non-Retrosheet sources (MLB API, Baseball-Reference, Statcast); those
  have their own gates.
- A pure-Python parser (`pure-python-retrosheet`); this gate is its future yardstick.

## Decisions

**D1. Logic in the package, thin script.** Comparison logic and the register live
in a small module `mlb_baseball/tieout.py`; `scripts/verify_retrosheet_tie_out.py`
parses arguments and prints the report. This follows `scripts/AGENTS.md`. *Alternative:*
everything in the script, as the two older gates do, is faster but leaves the logic
harder to test and reuse.

**D2. Three comparison levels, cheapest first.** Season totals first (a handful of
grouped queries), then per-game counts, then per player-game, each only where the
level above found nothing to explain or where asked. Per-game and per-player-game
queries are restricted to the season range requested, because `retrosheet_plays`
scans are slow (a season-filtered count timed out at 30 seconds in restricted
mode); the script sets its own longer timeout and reports elapsed time.

**D3. Exact match is the default pass mark.** Counts from two sources of the same
game are the same fact, so the tolerance is zero. Any allowed difference is an
explicit register entry: `id`, sources, fact, seasons, cause, evidence, and a
rule that reproduces it (for example "game-log minus event home runs equals
postseason game-log home runs, per season"). A register entry that stops
matching its rule fails the gate, so a stale excuse cannot hide a new problem.
Tolerances are committed to this change before the full-history run (task 2.1).
*Alternative:* a percentage tolerance would let real losses hide inside it.

**D4. Season range.** The full run covers every season where at least two sources
overlap. The 2015–2025 range runs first because the play-engine depends on it;
older eras run after and their differences are triaged, not blocked on.

**D5. Core check compares to raw, not to a third opinion.** `core.play`
plate-appearance rows per season equal the event rows with the batter-event flag
(plus the documented event-code set), `core.game` counts equal the distinct games in
raw for the same scope, duplicates are counted with `GROUP BY ... HAVING`, and a
sampled set of attributes is compared value-for-value. The check states which
raw table each `core` table is built from, taken from `conform.py`, and cites the
line.

**D6. Column contract is a test, not a script.** The pinned field lists (Chadwick
`cwevent` field spec used by the connector; CSV headers) become test constants
checked against `information_schema` in the disposable database and against the
connector's configured field list. Production is not needed for that check.
*Alternative:* checking production column names at gate time adds nothing the
test does not, and couples the gate to whichever migration is applied.

**D7. Audit before new tests.** Task 1.1 writes a per-table matrix of what
existing tests prove; only gaps that could hide incorrect data get new tests
(task 3.x). Everything else is listed with an issue. This bounds the work.

**D8. Safety.** The script opens a read-only transaction
(`SET TRANSACTION READ ONLY` or a read-only connection), takes the database name
explicitly, prints it before running, and refuses an unset target. It never
uses the disposable-test-database helpers against production.

## Risks / Trade-offs

- [The gate finds real differences in old eras (1910s–1940s)] → Expected; they are
  triaged into the register or an issue. The finish line requires explanation,
  not zero differences.
- [Slow queries on 16M-row CSV tables] → Season-filtered queries, explicit
  timeout, and progress output; run in the background if needed. A missing index
  is reported as a finding, not fixed here.
- [Two sources sharing an upstream error look like agreement] → Stated limit:
  the gate proves the ingested copies match each other, not that Retrosheet
  is right. Independent published figures (Baseball-Reference) stay with the
  existing gate.
- [Register grows into a dumping ground] → Every entry needs a reproducible
  rule and evidence; entries are re-checked on each run.
- [Scope creep into fixes] → Stop rule in the proposal.

## Migration Plan

No production changes. The script and tests merge as one small pull request per
stage; rollback is reverting it. The production run is read-only.
