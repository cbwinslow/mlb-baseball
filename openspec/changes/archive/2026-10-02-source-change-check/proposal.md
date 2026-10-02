## Why

Retrosheet regenerated every published file on 2026-08-09 (event, game-log, box-score,
roster, schedule and biography archives all carry a newer `Last-Modified` than our July
load), and nothing in the project noticed. A bootstrap skips archives marked loaded and the
download cache trusts a file whose hash matches its own manifest, so the production `raw`
layer slowly drifted from what a fresh install now gets. The `raw-source-tieout` gate found
it only by accident. The project already stores a fingerprint of every download; it just has
no command that asks the publisher whether the file changed, and `--refresh` (commit
`d50b9c0`) has no spec yet.

## What Changes

- Add `mlb source-check`: for each source with a download manifest, compare every recorded
  archive with the live file using a HEAD request (no download) and report changed /
  unchanged / unknown per source, with the exact `mlb ingest <source> --refresh` to run.
  `--hash` optionally downloads each archive to a temporary file and compares SHA-256.
  Read-only: no database access, no change to `downloads/`.
- Specify the existing `mlb ingest <source> --refresh` (added in `d50b9c0`): set a source's
  cached downloads aside, then fetch and reload everything.
- Make ingestion output state both numbers: rows loaded this run and the table's total, so a
  scoped reload (for example a skipped year keeping its old rows) is not misread.
- Not changing: connector load logic, the tie-out gate, the daily update job.

## Capabilities

### New Capabilities
- `source-refresh`: detect that a publisher changed an archive we already downloaded, reload a
  source on request, and report load results as both rows loaded and table totals.

### Modified Capabilities
<!-- none: no existing spec covers ingestion downloads or reloads -->

## Impact

- New `mlb_baseball/source_check.py` (pure comparison + a thin HTTP reader), new `source-check`
  subcommand in `mlb_baseball/cli.py`, small change to the `ingest` output path in `cli.py`.
- Tests under `tests/unit/` (comparison logic, CLI dispatch, output); no database needed.
- Docs: `mlb_baseball/cli.py.dox.md`, `scripts/AGENTS.md` if a script wrapper is added.
- Correction to an earlier note: the CSV connector (`retrosheet.py`) already records its zips
  in the manifest; on this machine the manifest is simply empty because the zips were never
  kept. The check reports such a source as "no download record", not as a missing feature.
