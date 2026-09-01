# retrosheet_box.py DOX

## Purpose

Own Retrosheet box-score-only archives parsed through Chadwick `cwbox`, filling
historical games that do not have full event-file play-by-play.

## Ownership

Source implementation: `retrosheet_box.py`.

Owned raw relations:

- `raw.retrosheet_box_game`
- `raw.retrosheet_box_batting`
- `raw.retrosheet_box_fielding`
- `raw.retrosheet_box_pitching`
- `raw.retrosheet_box_double`
- `raw.retrosheet_box_triple`
- `raw.retrosheet_box_homerun`
- `raw.retrosheet_box_stolenbase`
- `raw.retrosheet_box_doubleplay`
- `raw.retrosheet_box_tripleplay`
- `raw.retrosheet_box_sacbunt`

Registry source name: `retrosheet_box`.

Focused integration test: `tests/integration/test_retrosheet_box_load.py`.
Cross-product tie-out: `tests/integration/test_larsen_perfect_game.py`.

## Source and Coverage Contracts

This connector closes gaps left by event-file PBP, including pre-1910 box-score
archives and Negro League box-score products. Archive groups are intentionally
kept distinct from regular event-file data.

The seven supplementary event lists produced by `cwbox -X` are first-class raw
relations, even when a year legitimately has zero rows for a particular event
type.

## Chadwick and Reference-File Contracts

`cwbox` differs materially from `cwevent`/`cwgame`: an empty team placeholder is
not sufficient. It resolves team information from real team files.

For archives missing bundled references, this connector constructs the required
`TEAM{year}` and roster context from Retrosheet's own official reference products:

- MLB eras: `TEAMABR.TXT`;
- Negro League eras: `biodata.zip` team data;
- player rosters: `rosters.zip`.

Do not replace those with guessed mappings or borrow the empty-placeholder logic
from `retrosheet_event.py`.

## Scope and Runtime Contracts

- Parser version: `retrosheet-box-cwbox-v1`.
- Composite `_scope = <year>_<group>` isolates overlapping source groups.
- Whole archives are manifest-tracked and replayable.
- `bootstrap()` processes all historical box archive groups.
- `update()` force-reloads those historical archives so upstream corrections can
  be picked up; the source is not expected to gain modern games.
- A published archive/year with no actual box records can be a legitimate empty
  slice and must not automatically be treated as a parser failure.
- A known class of malformed official Negro League records can make `cwbox`
  produce unsafe output around `NA` integer values. The connector skips only the
  affected source slice rather than guessing which rows to delete or coercing
  bad source values.

## Downstream Context

Box-only rows supplement, rather than overwrite, event/CSV/gamelog evidence.
Conformance and research tie-outs must preserve which Retrosheet product supplied
a fact.

## Verification

Run:

```bash
uv run pytest tests/integration/test_retrosheet_box_load.py -q
uv run pytest tests/integration/test_larsen_perfect_game.py -q
uv run ruff check mlb_baseball/connectors/retrosheet_box.py tests/integration/test_retrosheet_box_load.py
```

When changing team/roster preparation or scopes, test both self-contained and
reference-dependent archives plus a sparse supplementary table case.
