# `retrosheet_transaction.py` DOX

## Purpose

Own Retrosheet's historical transaction database, landing trades, releases, waivers, free agency, injured-list transactions, call-ups, draft transactions, and related historical records into `raw.retrosheet_transaction`.

## Ownership

Implementation: `retrosheet_transaction.py`.

Primary output:

- `raw.retrosheet_transaction`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

- Source archive: `https://www.retrosheet.org/transactions/tranDB.zip`.
- `tran.txt` is headerless with the 16-field layout defined in the archive's own readme and verified against the downloaded data.
- Retrosheet froze this transaction database on **November 26, 2021** and transferred ongoing maintenance elsewhere.
- Therefore this source is historical coverage only; do not present it as a current transaction feed.
- Current/post-2021 transaction research must use an appropriate maintained source such as the project's MLB Stats API transaction product or another explicitly supported source.
- Rights/profile behavior remains owned by repository source-rights metadata/docs.

## Field Contract

`TRANSACTION_FIELDS` defines the source layout, including:

- primary/secondary dates and approximation flags;
- source transaction/player IDs;
- transaction type;
- from/to team and league;
- draft metadata;
- free-form info.

Approximation fields are meaningful source evidence. Do not coerce an approximate historical date into falsely exact event-time semantics downstream without preserving the uncertainty.

## Runtime / Idempotency Contract

- The archive is a compact whole-history source and loads with full replacement.
- `bootstrap()` downloads/parses/replaces the table and commits.
- Despite older prose sometimes describing update as a no-op, the **current implementation** intentionally re-runs the same full idempotent load on `update()` so an in-place Retrosheet archive correction can still be picked up.
- This does not make the dataset current beyond the 2021 freeze date.
- Download/replay is persisted through the manifest before parsing.

## Point-in-Time / Research Semantics

- Historical transactions can be useful for roster/team-affiliation/context features only when the transaction date/availability precedes the target event.
- Approximate dates require explicit conservative handling if used for strict PIT features.
- The source freeze means absence after November 2021 is **coverage absence**, not "no transactions occurred."
- Do not interpret post-freeze missing rows as zero activity.

## Dependencies

- `manifest`
- pandas / zipfile / psycopg
- generic full-replace loader
- run tracking, DB, health helpers

## Downstream Consumers

- Historical player/team affiliation and roster-context research.
- Cross-validation against other transaction sources in overlapping years.
- Future feature construction only with explicit date/PIT and coverage rules.

## Known Quirks / Decisions

- Source is permanently frozen as a maintained current feed.
- Update re-loads the frozen archive for possible in-place corrections rather than pretending to fetch new post-2021 transactions.
- Date approximation flags are part of the source contract.

## Work Guidance

- Keep the 2021 coverage cutoff visible in health/coverage/research metadata.
- Do not "fill" newer years from another source inside this raw connector; cross-source canonical transaction modeling belongs downstream.
- Preserve approximate-date indicators.
- If Retrosheet republishes/changes the archive, verify the field layout/readme before changing `TRANSACTION_FIELDS`.

## Verification

For changes, verify:

- exact 16-field source parsing;
- approximation/date fields remain source-faithful;
- full replacement is repeatable/idempotent;
- update does not imply post-2021 freshness;
- coverage/health surfaces make the historical freeze understandable;
- overlapping-year tie-outs against another transaction source when canonical transaction work changes;
- predictive consumers treat post-freeze absence and approximate dates correctly.

## Child DOX Index

No child DOX files. This is a leaf connector contract.