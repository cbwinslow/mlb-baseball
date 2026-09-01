# retrosheet.py DOX

## Purpose

Own Retrosheet's official annual pre-parsed CSV product. This is the fast,
source-published tabular Retrosheet path and is complementary to locally parsing
Retrosheet raw event files in `retrosheet_event.py`.

## Ownership

Source implementation: `retrosheet.py`.

Owned raw relations:

- `raw.retrosheet_allplayers`
- `raw.retrosheet_batting`
- `raw.retrosheet_fielding`
- `raw.retrosheet_gameinfo`
- `raw.retrosheet_pitching`
- `raw.retrosheet_plays`
- `raw.retrosheet_teamstats`

Registry source name: `retrosheet`.

Focused integration test: `tests/integration/test_retrosheet_load.py`.

## Source and Coverage Contracts

- Source is Retrosheet's own annual `{year}csvs.zip` product, not a mirror and
  not Chadwick's local parse output.
- Coverage begins in 1898 for this CSV product. Do not imply it reaches the full
  historical range of Retrosheet's other products.
- Each annual archive contains seven CSVs; `plays` is a broad published schema and
  may contain fewer columns in less-complete early seasons.
- Raw preserves legitimate historical schema sparsity. Missing early-era columns
  become null/absent source evidence; do not fabricate modern tracking/detail.

## Runtime Contracts

- Downloads are persisted through `manifest` before parsing so completed fetches
  survive interrupted bootstraps.
- Parser version is recorded as `retrosheet-csv-v1`.
- Each year is an independent `_season` replacement scope and commit boundary.
- `bootstrap()` proceeds sequentially from 1898 through current year and isolates
  failures per year.
- `update()` reloads only the current year.
- Schema drift uses the loader's warning/tolerant path intentionally because real
  Retrosheet historical CSV schemas differ by season; do not make legitimate
  early-season sparsity fatal.
- A failed year must not abort or roll back every previously successful year.

## Known Source Quirks

`raw.retrosheet_gameinfo.gametype` contains a known historical casing
inconsistency. Raw remains source-faithful. Conformance normalizes casing when
building canonical game type; the connector health check keeps the raw quirk
visible without treating the handled source fact as a failure.

Do not normalize source fields in raw merely to simplify downstream queries.

## Relationship to Other Retrosheet Connectors

- `retrosheet_event.py`: authoritative raw event files parsed locally via Chadwick;
  kept for independence/cross-validation and deeper event provenance.
- `retrosheet_gamelog.py`: classic one-row-per-game logs with broader historical
  coverage.
- `retrosheet_box.py`: box-score-only historical/Negro League gaps.
- reference/roster/schedule/transaction connectors own their separate products.

Overlapping data is intentional cross-source/product evidence; do not delete one
copy simply because fields appear redundant.

## Rights

Retrosheet-derived relations are central to the conservative `public_safe`
profile, but exact redistribution eligibility remains controlled by
`source_profiles.py`, export allow-lists, and `docs/SOURCE_RIGHTS.md`.

## Verification

Run:

```bash
uv run pytest tests/integration/test_retrosheet_load.py -q
uv run ruff check mlb_baseball/connectors/retrosheet.py tests/integration/test_retrosheet_load.py
```

Verify manifest/resume behavior, per-season replacement/idempotency, early-era
schema drift, and gametype health behavior when those areas change.
