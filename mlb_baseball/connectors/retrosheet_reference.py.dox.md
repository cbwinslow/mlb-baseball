# `retrosheet_reference.py` DOX

## Purpose

Own Retrosheet's static/whole-file reference and dimension products: parks, team-history identifiers, biographies, coaches/relatives, and newer biodata manager/team/umpire/ballpark tables. This connector lands source reference products as-is so identity/conformance can use them without losing distinctions between Retrosheet's parallel schemas.

## Ownership

Implementation: `retrosheet_reference.py`.

Primary outputs include:

- `raw.retrosheet_park`
- `raw.retrosheet_team`
- `raw.retrosheet_biofile`
- `raw.retrosheet_biofile0`
- `raw.retrosheet_coach`
- `raw.retrosheet_relative`
- `raw.retrosheet_ballpark`
- `raw.retrosheet_coach0`
- `raw.retrosheet_manager`
- `raw.retrosheet_team0`
- `raw.retrosheet_umpire`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

Current source files/bundles include:

- `parkcode.txt` — headered park codes.
- `TEAMABR.TXT` — headerless six-field team-history registry.
- `biofile.zip` — `biofile.csv`, `biofile0.csv`, coaches, relatives.
- `downloads/biodata.zip` — newer parallel reference files such as ballparks0, coaches0, managers0, teams0, umpires0.

These are static whole-file products; bootstrap and update both perform full replacement.

Repository source-rights/profile metadata remains authoritative for permitted use/redistribution.

## Raw / Parallel-Schema Contract

Retrosheet sometimes distributes two products representing related concepts with different schemas rather than one strict superset.

Examples:

- `biofile.csv` and `biofile0.csv` are distinct source schemas and both remain raw.
- older team/coach products and newer `teams0`/`coaches0` products have materially different column/time representations.

Do **not** silently merge these raw tables merely because the concepts look similar. Canonical identity/conformance should reconcile them with explicit rules/evidence.

If two archive members are byte-identical/duplicated across bundles, avoid landing a redundant second copy when one source artifact already preserves the exact data.

## Team-History Contract

- `TEAMABR.TXT` layout is `(team_id, league, city, nickname, first_year, last_year)`.
- The published file can contain a shared historical maximum year for current franchises that reflects source publication state, not necessarily franchise closure.
- Raw preserves the source's actual last-year value.
- Core/conformance may interpret a source-wide shared maximum as open-ended when supported by evidence; do not rewrite the raw value to a guessed current year.

## Runtime / Idempotency Contract

- Downloads are persisted through `manifest.download_required()` before parsing.
- Whole-file outputs use full replacement; no per-season scope is necessary for these compact dimension products.
- One connector run commits the coherent reference refresh.
- `bootstrap()` and `update()` currently share the same `_run()` because source size/shape makes full refresh cheap and deterministic.

## Identity / Research Semantics

- These reference tables are evidence inputs for canonical player/team/venue/umpire/manager identity; they are not themselves the canonical project identity tables.
- Preserve Retrosheet IDs/names/time ranges exactly enough for downstream cross-source reconciliation.
- Similar names or overlapping schemas do not justify fuzzy identity guesses in the connector.

## Dependencies

- `manifest`
- pandas / zipfile / psycopg
- generic full-replace loader
- run tracking, DB, health helpers

## Downstream Consumers

- `conform.py` hard-prerequisite team identity (`raw.retrosheet_team`) and venue/player/team reference enrichment.
- `retrosheet_box.py` uses official team/biodata registries when constructing support files required by `cwbox`.
- Research joins and source crosswalks for parks, teams, people, coaches/managers/umpires.

## Known Quirks / Decisions

- Retrosheet's own parallel `*0` products are preserved rather than forcibly collapsed.
- Raw team-history end years reflect source publication semantics and require downstream interpretation.
- Reference bundles contain genuinely new and duplicated members; the connector deliberately avoids duplicate landing when byte-identical source data is already represented.

## Work Guidance

- Before merging related raw tables, prove semantic equivalence and move that reconciliation downstream rather than altering source landing.
- Verify source file/member layouts directly when Retrosheet changes a bundle.
- Keep consumers such as conformance and `retrosheet_box.py` in mind before renaming/removing reference tables/columns.
- Do not turn source publication timestamps/ranges into canonical franchise facts inside raw ingestion.

## Verification

For changes, verify:

- exact TEAMABR six-field parsing;
- park-code and ZIP member parsing;
- expected biofile/biodata members and separate table mappings;
- duplicate-member avoidance when applicable;
- full-reload idempotency;
- downstream team/player/venue identity/conformance tests;
- `retrosheet_box` support-file construction if team/biodata behavior changes;
- health still covers representative critical reference tables.

## Child DOX Index

No child DOX files. This is a leaf connector contract.