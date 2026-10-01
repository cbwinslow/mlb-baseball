# Results: real read-only run, 1871-2014

Task 4.2. Read-only against production `mlb`. Code under test: commit `1ed8ff7`
(register in `passmarks.md` section 2 at the same commit). Full output:
`results-history-raw.log`.

```
set -a && . ./.env && set +a
uv run python scripts/verify_retrosheet_tie_out.py --expect-db mlb --from 1871 --to 2014 \
    --levels season,game,player_game --statement-timeout-minutes 25
```

**Run 8 (2026-10-01): exit 0, PASSED, 1440.4 s.** No unexplained difference, no stale
register entry, and every event batter and pitcher id 1871-2014 resolves to a roster or
all-players row (0 unresolved).

| Level | Pair | Seasons: match / explained / unexplained / not comparable |
| --- | --- | --- |
| season, game, player | event vs CSV plays | 104 / 1 / 0 / 9 |
| season, game, player | event vs CSV batting | 67 / 38 / 0 / 12 |
| season, game | event vs game info | 64 / 41 / 0 / 12 |
| season, game | event vs game log | 0 / 101 / 0 / 15 |
| season, game | game info vs game log | 2 / 107 / 0 / 11 |
| game, player | event vs box (sample) | 89 / 16 / 0 / 1 (game); 82 / 23 / 0 / 1 (player) |
| game | game info vs box (sample) | 113 / 4 / 0 / 1 |

## How the first runs failed and what each was

Runs 1 and 2 were not data problems. Every cause below is a register entry (evidence in
`passmarks.md` section 2), a gate fix, or a stale load; raw data was never edited.

- **Gate fixes:** a blank source value is "not recorded" (kept as `None`, never zero); a
  game-log `-1` is the same; box scores are a sample (compared only on games they hold);
  a season total is explained when it equals the sum of explained games.
- **Games with a scorecard but no play-by-play (E4)**, **games the game logs are not
  meant to hold (E5, includes the 1900 forfeit `BRO190009190`)**, **box-score-only games
  (E6)**, **games the box lists under two seasons (E7)**, **one 1947 unknown-batter play
  that Chadwick counts and the CSV does not (E8)**; E1 no longer predicts a difference for
  a blank season total.
- **Stale load (not an entry):** the 2000s event archive in `mlb` predated Retrosheet's
  own corrections. Reloaded 2026-10-01 through the connector: 105 of 1,936,585 event rows
  changed (for example `TBA200205030`, where `OA/G6.2-H...` became `OA.2-H...` and the run
  now scores), none added or removed. The other decade archives were not compared or
  reloaded; the gate passes against them as loaded.
- **Slow run (runs 3-5):** the E5 rule rebuilt a set over every game for each difference,
  so a run took over an hour. Cached in `Series`; run 8 took 24 minutes.

## Known limits

- E8 and E7 are specific to the games named in the register. They fail if the data
  changes, by design.
- Retrosheet's published notes were not found online in this run; the register cites our
  own checks of the raw files, not their documentation. E8 especially is "not yet checked
  against Retrosheet's published notes".
- No GitHub issue was filed: all three suspected issues turned out to be an upstream
  correction already fixed (2002), a Retrosheet product difference (1947) and a forfeit
  (1900).
- Not run: the full test suite. Run: the two tie-out test files (79 pass), ruff, mypy on
  the two tie-out modules, `scripts/check_dox.py`.

## Re-run of 2015-2025 on the same code (run 9, 2026-10-01)

Same command with `--from 2015 --to 2025`, code commit `1ed8ff7`. **Exit 1, 215.3 s.**
The only difference is the one already recorded in `results-2015-2025.md`: 2025 runs,
`BOS202509030` (event 8 vs 9 in CSV plays, CSV batting, game info and game log), filed as
[GitHub issue #267](https://github.com/cbwinslow/mlb-baseball/issues/267) (a `cwevent`
parsing gap on an obstruction play). Nothing new appeared with the register changes above.
So 2015-2025 is "every difference explained or filed" with one open issue, not a clean
exit 0; the 1871-2014 history is a clean exit 0.

## Finish-line checklist (`proposal.md`)

- [x] **Gate exists and is tested** (a planted mismatch fails, a matching fixture
  passes): `tests/unit/test_tieout.py` (53) and `tests/integration/test_tieout_run.py`
  (26) pass, 79 total, at commit `1ed8ff7`.
- [x] **Run read-only against production for every season where two sources overlap**:
  2015-2025 (runs 1 and 9) and 1871-2014 (run 8); seasons only one source covers are
  reported "not comparable" in the log, never as a pass.
- [x] **Every difference is in the register with a reason or has an issue**: E1-E8 in
  `passmarks.md` section 2; one open issue (#267). No difference was excused without
  evidence.
- [x] **Ingestion-test audit recorded, gaps closed or listed**: `audit.md` (tasks 1.1,
  3.1, 3.2).
- `openspec validate raw-source-tieout`: valid. `scripts/check_dox.py`: passes.

## Run 10 — after 2026-10-01 refresh of all Retrosheet raw tables

Event, roster, reference, schedule, box, gamelog and CSV products reloaded from current
files. Unexplained differences fell from about 5,400 (event new vs CSV stale) to 24 in
1935 game `PRG193512012` plus 2 in 1934 game `NNS193410230` (event vs box). Both are
Retrosheet products disagreeing with each other; filed as an issue, not excused. The gate
stays red for these until they are registered or Retrosheet corrects them.
