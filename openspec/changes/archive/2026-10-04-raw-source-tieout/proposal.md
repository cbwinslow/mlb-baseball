## Why

We load Retrosheet from several independent files (Chadwick-parsed event files,
Retrosheet's own CSV play-by-play, its per-player batting CSVs, game logs, box
scores, rosters), but no standing check proves they agree with each other, or
that `core` is populated correctly from them. One-off queries on 2026-09-27
showed the modern seasons do agree exactly; that evidence is not repeatable and
covers only a few columns. The owner needs a written pass mark for "the
ingested data is correct" before more is built on it, and a check that
catches an ingestion or `core` bug before it reaches a model.

## What Changes

- Add a **read-only tie-out gate** that compares the redundant Retrosheet
  sources with each other and with `core`, and fails loudly on any unexplained
  difference. It never writes to `raw`, `core` or `gold`.
- Compare at three levels: season totals, per game, and per player-game, for the
  counts every source can supply (plate appearances, strikeouts, walks, home
  runs, runs, games).
- Check that `core.play` and `core.game` are complete and correct against the
  raw tables they are built from (nothing dropped, nothing invented).
- Check that raw column names still match the source contract (the Chadwick
  field list and the CSV headers), so a silent field shift fails a test.
- Check identities: every batter and pitcher in the events exists in the
  Retrosheet rosters.
- Keep an explicit **explained-differences register** (for example: game logs are
  regular season only). A difference not in the register is a failure.
- Audit the existing ingestion tests against that list, record what they do and
  do not prove, and add tests for the gaps that matter.
- Run the gate against production `mlb` (read-only), record the result, and
  open an issue for every real difference. Fixing a difference in the raw
  layer is out of scope.

## Capabilities

### New Capabilities

- `retrosheet-tie-out`: what the tie-out gate must check, its pass mark, the
  explained-differences register, and the ingestion-test evidence required.

### Modified Capabilities

<!-- None. Existing specs are consumed, not changed. -->

## Impact

- New script `scripts/verify_retrosheet_tie_out.py`, following the pattern of
  `scripts/verify_mlb_boxscore_tie_out.py`, plus tests and a results record in
  this change.
- New or extended tests under `tests/`; possibly small additions to the
  Retrosheet connector DOX sidecars if a contract is clarified.
- No schema change, no data change, no new source, no new dependency.
- Gives the pending `pure-python-retrosheet` change a ready parity yardstick.
- Does not block the `play-engine` change, but its first dataset build (task
  2.3) should wait for a passing result on 2015–2025.

## Finish line

Done when: the gate exists and is tested (a planted mismatch fails, a matching
fixture passes); it has been run read-only against production for every season
where at least two sources overlap; every difference is either in the register
with a stated reason or has an issue; and the ingestion-test audit is recorded
with its gaps closed or listed.

## Stop rule

Anything not on the finish line goes to a later list. Explicitly later: fixing
data differences found, scheduling the gate in the daily job, a pure-Python
parser, and tie-outs for non-Retrosheet sources.
