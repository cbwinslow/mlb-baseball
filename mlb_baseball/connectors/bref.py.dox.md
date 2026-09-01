# bref.py DOX

## Purpose

Own Baseball-Reference season statistics and Baseball-Reference WAR acquisition
through the project's existing `pybaseball` dependency.

## Ownership

Source implementation: `bref.py`.

Owned raw relations:

- `raw.bref_batting`
- `raw.bref_pitching`
- `raw.bref_war_batting`
- `raw.bref_war_pitching`

Registry source name: `bref`.

Focused integration test: `tests/integration/test_bref_load.py`.

## Source and Coverage Contracts

- `batting_stats_bref()` and `pitching_stats_bref()` support 2008-present in
  the installed pybaseball implementation; `FIRST_YEAR = 2008` reflects that
  upstream hard limit, not a project preference.
- `bwar_bat()` and `bwar_pitch()` return full-history Baseball-Reference WAR
  tables in one call and extend back to 1871.
- The FanGraphs pybaseball paths are intentionally not substitutes here; live
  tests found their scraper blocked by HTTP 403.
- Broken/low-value pybaseball surfaces (team BRef helpers, prospects, per-player
  split explosion) are deliberately excluded rather than presented as supported
  coverage.

## Runtime Contracts

- `bootstrap()` loads season batting/pitching from 2008 through current year,
  skipping completed past seasons already landed, then full-reloads both WAR
  relations.
- `update()` reloads only the current season batting/pitching and full-reloads WAR.
- Season tables use `_season` scoped replacement and are idempotent.
- WAR tables are whole-table replacement because the upstream functions expose no
  season argument.
- A pybaseball-specific escaped-byte mojibake bug is repaired only for `Name` on
  the season batting/pitching paths. Do not apply that repair generically to WAR
  or unrelated sources.
- Failures are isolated per table/season with rollback before continuing.

## Known Source Quirks

The installed pybaseball BRef HTML parser may return literal `\\xHH` byte escapes
in accented names because of an upstream bytes-to-string bug. `_repair_name_mojibake`
reverses exactly that transformation and leaves already-correct names untouched.

Do not lower `FIRST_YEAR` without verifying a new upstream implementation supports
it. Earlier MLB history belongs to other sources unless BRef support changes.

## Downstream Context

These tables are cross-validation/season-reference inputs. They are not canonical
player identity by themselves; conformance should use stable cross-source IDs and
retain source evidence.

Baseball-Reference source rights/profile rules still apply. Local ingestion does
not automatically make these relations `public_safe`.

## Verification

Run:

```bash
uv run pytest tests/integration/test_bref_load.py -q
uv run ruff check mlb_baseball/connectors/bref.py tests/integration/test_bref_load.py
```

Verify health checks still cover all four raw relations plus last-run state.
