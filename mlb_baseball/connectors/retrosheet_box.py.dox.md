# `retrosheet_box.py` DOX

## Purpose

Own Retrosheet box-score-only source ingestion through Chadwick `cwbox`, closing historical/game coverage that the play-by-play event connector cannot provide. This includes pre-1910/NA-era box records and broader Negro League box-score coverage, plus Chadwick's supplementary event lists.

## Ownership

Implementation: `retrosheet_box.py`.

Primary outputs:

- `raw.retrosheet_box_game`
- `raw.retrosheet_box_batting`
- `raw.retrosheet_box_fielding`
- `raw.retrosheet_box_pitching`
- supplementary tables for doubles, triples, home runs, stolen bases, double plays, triple plays, and sacrifice bunts.

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

Retrosheet box archives currently include distinct families:

- self-contained NA-era archives such as 1871/1872/1874;
- late-1890s / 1900–1909 MLB box-only archives;
- Negro League box archives with broader coverage than the Negro League play-by-play event product.

These are not interchangeable with `retrosheet_event.py`. A game may have a box score without full event history.

Repository source-rights/profile metadata remains authoritative for permitted use/redistribution.

## Chadwick / Team Metadata Contract

`cwbox` has stricter support-file requirements than `cwevent`/`cwgame`:

- If an archive already bundles a real `TEAM{year}` and roster data, use it.
- For MLB-era archives that lack them, construct a real team file from Retrosheet's official `TEAMABR.TXT` and copy matching official roster files from `rosters.zip`.
- For Negro League archives, construct team files from Retrosheet `biodata.zip` `teams0.csv` and use appropriate roster data.
- An empty team-file placeholder is **not** sufficient for `cwbox`; team identity is resolved from that metadata.

Do not copy the empty-placeholder workaround from `retrosheet_event.py` into this connector.

## Raw Table Contract

`chadwick_tools.run_cwbox()` returns core box tables plus supplementary lists. Every returned non-empty source product belongs in the explicit `TABLE_MAP`.

The supplementary lists are real source products, even if a particular year has zero rows. Do not remove them merely because they are sparse or derivable from other event data.

Each DataFrame receives:

- `_season`
- `_group` (`na`, `era`, or `negro_league`)
- `_scope` = `<year>_<group>`

Scoped replacement is by `_scope`, preserving independently sourced archive families for the same year.

## Empty / Malformed Source Semantics

- Some authoritative archive-year slices can be genuinely empty (for example a source ZIP containing only reference metadata and no `.EB?` game records). Treat a verified empty slice as successful zero-row source coverage, not a parser failure.
- Some current official Negro League box files can make `cwbox` emit malformed output after unattributable `NA` integer errors. The current connector skips only the affected year rather than guessing which games/fields to delete or coerce.
- Preserve this limitation explicitly in health/coverage documentation; do not fabricate repaired rows.

## Runtime / Idempotency Contract

- Downloads are persisted through the manifest before parsing.
- Archive extraction is temporary.
- Each archive/year/group is replaceable through `_scope`.
- Bootstrap can skip already-loaded manifest artifacts.
- `update()` currently forces reprocessing of these otherwise historical archives so any in-place Retrosheet corrections can be picked up; the operation remains idempotent.
- Caller/orchestration owns commits; successful archive work must not be lost because a later unrelated archive fails.

## Dependencies

- Chadwick `cwbox` through `chadwick_tools`
- Retrosheet `TEAMABR.TXT`, `biodata.zip`, and `rosters.zip`
- `manifest` / `archive`
- pandas / psycopg
- generic scoped loader, run tracking, DB, health helpers

## Downstream Consumers

- Historical box-score research outside full PBP coverage.
- Cross-validation of player/team/game facts against event/CSV/game-log products.
- Future grain-complete batting/pitching coverage extensions for eras where event-level data does not exist, with explicit source/grain limitations.

Do not silently treat box-only statistics as if they contain the same event-level observability as play-by-play.

## Known Quirks / Decisions

- The source family spans very different eras/leagues; team/roster support must be constructed from the correct official Retrosheet registry.
- The 1890s archive name does not imply a full decade; source contents define coverage.
- `cwbox` supplementary lists are intentionally retained.
- A source parser limitation with some Negro League `NA` values is documented rather than guessed around.

## Work Guidance

- Verify source archive contents before changing coverage assumptions.
- Keep team-file construction tied to official Retrosheet registries.
- When Chadwick behavior changes, test self-contained, constructed-team-file, and Negro League cases.
- Preserve `_scope` group separation.
- Do not convert source/parser limitations into synthetic zeros.

## Verification

For changes, verify:

- correct archive/year discovery;
- real team/roster support-file construction for archives that lack them;
- self-contained archives bypass unnecessary synthesis;
- `cwbox` core + supplementary parsing;
- genuinely empty source slices remain valid;
- `_season` / `_group` / `_scope` and scoped rerun idempotency;
- known Negro League malformed-value path remains explicit/safe;
- Chadwick-missing health behavior;
- representative downstream historical tie-outs.

## Child DOX Index

No child DOX files. This is a leaf connector contract.