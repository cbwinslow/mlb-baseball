# `bref.py` DOX

## Purpose

Own selected Baseball-Reference season-level batting/pitching statistics and Baseball-Reference WAR tables exposed through pybaseball. This connector is both a research source and an independent cross-validation source; it does not replace canonical event-derived statistics.

## Ownership

Implementation: `bref.py`.

Primary outputs:

- `raw.bref_batting`
- `raw.bref_pitching`
- `raw.bref_war_batting`
- `raw.bref_war_pitching`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source / Library Contract

- Transport/parser: installed `pybaseball` Baseball-Reference functions.
- `batting_stats_bref()` / `pitching_stats_bref()` are Baseball-Reference scrapers, not FanGraphs.
- Their underlying pybaseball range functions enforce a **2008+** lower bound. This is a library/source-access constraint, not a project decision that earlier baseball does not exist.
- Baseball-Reference WAR functions (`bwar_bat()` / `bwar_pitch()`) use a separate source path and return full historical WAR data in one call, currently reaching back to 1871.
- FanGraphs pybaseball leader scrapers have been observed failing behind Cloudflare and are intentionally not substituted here.
- Several other pybaseball Baseball-Reference helpers were evaluated and excluded because they are broken, redundant, or combinatorially expensive; do not re-add them without re-verifying current upstream behavior/value.
- Repository source-rights/profile metadata remains authoritative for permitted use/redistribution.

## Grain / Table Contract

### Season stats

- `raw.bref_batting` and `raw.bref_pitching` are fetched one season at a time.
- `_season` is added and is the scoped-replace key.
- Past seasons can be skipped when already loaded; current season refreshes.
- These are source season aggregates and should not be treated as a substitute for point-in-time game-by-game history.

### WAR tables

- WAR functions have no season argument and return full history in one call.
- `raw.bref_war_batting` / `raw.bref_war_pitching` therefore use full-table replacement every run.
- WAR is a source-defined Baseball-Reference metric. Preserve source values/definitions distinctly from any project-owned WAR/statistic implementation.

## Mojibake Repair Contract

Current pybaseball Baseball-Reference season-stat scraping has a verified response-decoding bug that can turn UTF-8 bytes in player names into literal `\\xHH` escape text.

`_repair_name_mojibake()` is intentionally narrow:

- only applied to the `Name` column of the two affected season-stat tables;
- only attempts repair when a literal `\\x` escape is present;
- reverses the observed bytes-repr transformation back to UTF-8;
- returns the original value on decode failure;
- is **not** applied generically to all source columns or WAR tables, whose source path was verified unaffected.

Do not generalize this repair to other connectors or fields without reproducing the same upstream defect. If pybaseball fixes its scraper, the no-escape fast path should leave correct names unchanged.

## Runtime / Failure Contract

- Season tables make roughly one source request per season/stat type; weekly/date chunking is unnecessary.
- Each table/season commit is isolated. A failed source call rolls back/logs/continues so one product/season does not discard every other load.
- Shared retry/backoff wraps pybaseball calls.
- WAR tables similarly isolate failure per table.
- This is not a high-frequency source; health uses last-run/table evidence rather than minute-level content freshness.

## Point-in-Time / Research Semantics

- Final/season-to-date source aggregates may be used as descriptive or validation data.
- A final season aggregate is not valid for an earlier game in that same season unless a true as-of reconstruction/snapshot exists.
- WAR is post-event aggregate information and must respect target-game cutoffs in predictive work.
- Use this source to cross-check project formulas only after aligning grain, eligibility, and definition; disagreement is evidence to investigate, not permission to overwrite one source.

## Dependencies

- `pybaseball`
- pandas/psycopg through project loaders
- `load_dataframe` / `season_already_loaded`
- shared retry, run tracking, DB, health helpers

## Downstream Consumers

- `conform.py` / `core.player_war` bridging and source identity where applicable.
- Research/stat cross-validation for season batting/pitching/WAR.
- Future features only with explicit historical cutoff/availability rules.

## Known Quirks / Decisions

- Season-stat lower bound 2008 is a pybaseball implementation constraint.
- WAR source has much deeper historical coverage and a different load shape.
- The narrow name repair exists because of a reproduced upstream encoding bug.
- Similar-looking pybaseball functions may scrape FanGraphs or broken endpoints; function provenance must be verified, not guessed from the package name.

## Work Guidance

- Before adding another pybaseball statistic, inspect its actual implementation/target site, bulk cost, coverage, and overlap with existing sources.
- Keep source-defined WAR separate from project-owned statistic definitions.
- Preserve the narrow scope of encoding repair.
- If replacing pybaseball, parity-test columns, names/encoding, coverage, source requests, and WAR history first.

## Verification

For changes, verify:

- 2008 boundary for season tables;
- season-scoped rerun idempotency and historical skip/current refresh;
- WAR full-history replacement;
- affected/non-affected name examples for mojibake repair;
- per-table rollback/failure isolation;
- downstream WAR bridge/tie-outs;
- PIT tests for any predictive consumer of season aggregates;
- health on all four source tables.

## Child DOX Index

No child DOX files. This is a leaf connector contract.