# retrosheet_event.py DOX

## Purpose

Own local parsing of Retrosheet's source-of-record raw event files through the
Chadwick `cwevent` and `cwgame` tools. This connector preserves an independently
reproducible path from raw Retrosheet archives to play/game rows.

## Ownership

Source implementation: `retrosheet_event.py`.

Owned raw relations:

- `raw.retrosheet_event` — per-play/event output
- `raw.retrosheet_game` — per-game output

Registry source name: `retrosheet_event`.

Focused integration test: `tests/integration/test_retrosheet_event_load.py`.

## Source and Coverage Contracts

- Regular-season play-by-play archives cover the historical event-file range from
  1910 forward, including Retrosheet's documented deduced periods.
- Special archives add postseason, All-Star, and Negro League play-by-play.
- Box-score-only eras/games that do not have event files belong to
  `retrosheet_box.py`, not this connector.
- Downloaded archives are durable manifest artifacts; extraction is temporary.

## Chadwick Contract

- `cwevent` and `cwgame` are the canonical parsers for these event files.
- Multi-year archives must be split into per-year directories because Chadwick's
  `-y` behavior resolves year-specific team/roster files.
- Some event archives lack team files; for `cwevent`/`cwgame`, an empty
  `TEAM{year}` placeholder is sufficient for the affected source shape. Do not
  copy this assumption to `cwbox`, which has different requirements.
- Changes to Chadwick field selections/tool versions must be tied out against real
  fixtures before parser-version semantics change.

## Scope and Replacement Semantics

A season can appear in more than one Retrosheet archive group. `_season` alone is
therefore **not** a safe replacement key.

The canonical load scope is:

```text
_scope = <year>_<group>
```

Examples: `2024_pbp`, `2024_postseason`, `1943_allstar`.

This prevents later special-archive loads from deleting regular-season rows for
the same year. Never simplify replacement back to season-only without proving no
overlapping groups exist.

## Runtime Contracts

- Parser version: `retrosheet-event-cwevent-cwgame-v1`.
- `bootstrap()` iterates decade archives plus special archives.
- Failures are isolated both per year and per archive; one bad Chadwick parse must
  not lose successful years or abort the remaining corpus.
- Each archive's loaded state is tracked in the manifest so interrupted
  bootstraps can resume without re-parsing completed archives.
- `update()` force-refreshes the current decade plus postseason and All-Star
  archives because Retrosheet may update those in place.
- Commit/rollback boundaries must preserve already completed archive/year work.

## Downstream Context

These rows are important canonical event/game evidence for conformance and
Retrosheet-derived research marts. Keep original Retrosheet player/team/game IDs
and group/season provenance available for cross-source reconciliation.

## Verification

Run:

```bash
uv run pytest tests/integration/test_retrosheet_event_load.py -q
uv run ruff check mlb_baseball/connectors/retrosheet_event.py tests/integration/test_retrosheet_event_load.py
```

When changing parsing or scopes, explicitly test overlapping groups, one-year
failure isolation, manifest resume behavior, and Chadwick-tool health checks.
