# `retrosheet.py` DOX

## Purpose

Own the Retrosheet **official pre-parsed yearly CSV product** ingestion path. This connector is intentionally distinct from the raw Retrosheet event-file connectors: it provides a faster, simpler, source-authored CSV bootstrap/cross-validation path while preserving raw event files as a separate source product.

## Ownership

Implementation: `retrosheet.py`.

Primary raw outputs:

- `raw.retrosheet_allplayers`
- `raw.retrosheet_batting`
- `raw.retrosheet_fielding`
- `raw.retrosheet_gameinfo`
- `raw.retrosheet_pitching`
- `raw.retrosheet_plays`
- `raw.retrosheet_teamstats`

Public connector entry points:

- `bootstrap()` — historical yearly ingestion.
- `update()` — current-year refresh.
- `health_check()` — raw data/run/freshness/source-quirk visibility.

## Source Contract

- Source: Retrosheet's own CSV downloads at `retrosheet.org/downloads/{year}/{year}csvs.zip`.
- First supported CSV year: `1898`.
- Product coverage differs from raw event-file coverage; do not claim these CSVs cover all Retrosheet event history.
- Each yearly ZIP contains seven named CSV products: `plays`, `gameinfo`, `teamstats`, `batting`, `pitching`, `fielding`, `allplayers`.
- Rights/redistribution behavior must remain consistent with repository source-rights/profile documentation; this sidecar does not supersede `docs/SOURCE_RIGHTS.md` / source metadata.

## Runtime Contracts

### Download and replay

- Download through `mlb_baseball.manifest.download()` into the repository's Retrosheet download cache before parsing.
- Do not replace this with an in-memory-only fetch path: the persisted artifact/manifest is part of replay/resume/provenance behavior.
- Parser version is currently `retrosheet-csv-v1`; change it when parsing semantics materially change.

### Historical bootstrap

- Iterate years sequentially from 1898 through the current year.
- Sequential behavior is deliberate. Previous bounded-thread ingestion caused a real production hang and was reverted; do not reintroduce concurrency without profiling/reproduction evidence and a targeted test/benchmark.
- Each year is its own resumable/committable unit. Successful years are committed before proceeding.
- A failure in one year is rolled back/logged/skipped rather than aborting every remaining historical year.

### Scoped/idempotent loading

- `_season` is added to every extracted DataFrame.
- `load_dataframe(..., scope_column="_season", scope_value=str(year))` replaces that year's scope, so rerunning a year is idempotent at the intended scope.
- Do not change this to full-table replacement; full-history reload cost/resume behavior is a key reason this connector is season-scoped.

### Schema drift

- Use the shared loader's current non-fatal/warn behavior for genuine historical column sparsity.
- Retrosheet CSV schemas are not perfectly uniform across early seasons. Missing historical columns represent genuine source detail gaps and should land as NULL where appropriate rather than being treated as zero or fabricated values.
- Do not promote strict schema equality across all seasons unless real source evidence shows the historical sparsity no longer exists.

## Data Contracts and Known Quirks

- Raw remains source-faithful.
- `gameinfo.gametype` contains a verified historical casing inconsistency (`Regular` vs `regular`). Do not "fix" raw data. `conform.py` normalizes casing when constructing canonical game data.
- The health check intentionally reports that casing quirk as handled/visible rather than treating the known historical source row as an ongoing ingestion failure.
- Coverage/nonmeasurement gaps must remain distinguishable from zero values.

## Dependencies

- `manifest.download` / `manifest.mark_status`
- `load_dataframe`
- `track_run`
- `get_connection`
- shared health helpers
- pandas / zipfile / psycopg

## Downstream Consumers

- `conform.py` consumes Retrosheet raw game/player/team/play information for canonical identities/facts.
- Research grains and cross-source validation depend on this product as an independent historical source.
- Retrosheet raw event/box/gamelog connectors complement this connector; they are not interchangeable implementations of the same source grain.

## Work Guidance

- Preserve the separation between official CSV ingestion and raw-event ingestion.
- When source columns change, inspect conformance/tests before changing normalization.
- Favor honest nulls over synthetic defaults for historically unavailable columns.
- Any change to download URL/product layout, coverage start, parser version, season scoping, or commit boundaries requires this sidecar and source docs/ADRs to be reviewed together.

## Verification

Read and run the relevant current tests before editing. Expected verification areas include:

- Retrosheet load/integration tests (search `tests/integration/` for Retrosheet load coverage).
- `tests/integration/test_conform.py` for downstream Retrosheet conformance behavior.
- connector health checks / `mlb doctor` coverage where applicable.
- idempotency: load the same season twice and assert stable scoped row results.
- archive/fixture parsing without live network access in routine CI.

For changes to the verified casing/sparsity quirks, use real-source evidence or a captured representative fixture; do not remove the behavior based only on a cleaner modern-season sample.

## Child DOX Index

No child DOX files. This is a leaf implementation contract.
