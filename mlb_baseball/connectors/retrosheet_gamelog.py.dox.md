# retrosheet_gamelog.py DOX

## Purpose

Own Retrosheet's classic one-row-per-game game-log product, including regular
season annual files and separate whole-history postseason game-log archives.

## Ownership

Source implementation: `retrosheet_gamelog.py`.

Owned raw relations:

- `raw.retrosheet_gamelog` — regular-season annual logs
- `raw.retrosheet_gamelog_post` — postseason/All-Star whole-history files

Registry source name: `retrosheet_gamelog`.

Focused integration test: `tests/integration/test_retrosheet_gamelog_load.py`.
Cross-product tie-out: `tests/integration/test_larsen_perfect_game.py`.

## Source and Coverage Contracts

- Regular-season source: `retrosheet.org/gamelogs/gl{year}.zip`, 1871-present.
- Source files are headerless with a fixed 161-field layout. `GAMELOG_FIELDS` is
  the explicit source schema and its length assertion is a load-bearing guard.
- Postseason/All-Star game logs are not contained in the annual files. They come
  from separate `glws.zip`, `glas.zip`, `glwc.zip`, `gldv.zip`, and `gllc.zip`
  archives and therefore have a separate raw relation.

Do not merge postseason rows into the regular relation without a deliberate
schema/scope migration; the current split mirrors independent source products and
replacement units.

## Runtime Contracts

- Annual regular-season files use `_season` scoped replacement.
- Postseason/All-Star whole-history files use `_type` scoped replacement.
- Downloads are persisted through `manifest` before parsing.
- `bootstrap()` loads every annual file from 1871 through current year and then
  every postseason archive.
- `update()` reloads the current annual file and each postseason archive.
- Commit boundaries are per annual/source archive so completed history survives a
  later failure.
- Source schema changes must not silently shift the 161-column alignment.

## Downstream Context

This relation is useful for broad historical game-level coverage and independent
tie-out against Retrosheet event/CSV products. Preserve the product distinction
rather than treating any one Retrosheet table as universally authoritative for
every grain.

## Verification

Run:

```bash
uv run pytest tests/integration/test_retrosheet_gamelog_load.py -q
uv run pytest tests/integration/test_larsen_perfect_game.py -q
uv run ruff check mlb_baseball/connectors/retrosheet_gamelog.py tests/integration/test_retrosheet_gamelog_load.py
```

When editing the field layout, test a real fixture with exactly 161 columns and a
postseason scope so column shifts cannot pass unnoticed.
