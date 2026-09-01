# `retrosheet_gamelog.py` DOX

## Purpose

Own Retrosheet's classic fixed-layout game-log products: regular-season per-year game logs plus separately published whole-history postseason/All-Star game-log archives. This product has broader historical game coverage than the modern Retrosheet CSV connector and provides a valuable independent per-game cross-check.

## Ownership

Implementation: `retrosheet_gamelog.py`.

Primary outputs:

- `raw.retrosheet_gamelog` — regular-season game logs, one row per game.
- `raw.retrosheet_gamelog_post` — separately published World Series, All-Star, Wild Card, Division Series, and LCS logs.

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

- Regular-season files: `retrosheet.org/gamelogs/gl{year}.zip`.
- Coverage begins in 1871 and continues through current published seasons.
- Each yearly file is headerless with the documented/verified 161-field game-log layout.
- Postseason/All-Star data is **not** bundled in normal per-year regular-season archives. It is published as separate whole-history archives (`glws.zip`, `glas.zip`, `glwc.zip`, `gldv.zip`, `gllc.zip`).
- The postseason separation was confirmed through direct product tie-out; do not assume regular-season game logs are a complete all-game source.
- Rights/profile behavior remains owned by repository source-rights metadata/docs.

## Field Layout Contract

- `GAMELOG_FIELDS` is the source-layout contract and must remain exactly 161 fields unless Retrosheet changes its documented product.
- The list includes game metadata, team totals, umpire/manager/pitcher identities, and nine lineup slots for each side.
- The module-level `assert len(GAMELOG_FIELDS) == 161` guards accidental drift; preserve an equivalent explicit validation if refactoring.
- Do not rename raw source fields for convenience without a deliberate raw-schema compatibility decision.

## Runtime / Idempotency Contract

### Regular season

- Each year is downloaded/persisted before parsing.
- `_season` is added and used for scoped replacement.
- Rerunning one year is idempotent and must not replace other years.
- Bootstrap runs years sequentially rather than using the previously attempted bounded-thread approach; the project chose the simpler reliable path after a real Retrosheet concurrency hang elsewhere.
- Each year commits independently so a late source issue does not destroy all earlier history.

### Postseason / special logs

- Each whole-history archive is assigned a stable `_type` (`worldseries`, `allstar`, `wildcard`, `divisionseries`, `lcs`).
- `raw.retrosheet_gamelog_post` is replaced by `_type`, not merged into the regular-season table.
- Keeping the source products separate preserves source lineage and avoids silently changing an established populated raw table.

## Update Contract

- Refresh current regular-season year.
- Refresh all special/postseason whole-history archives because they can grow/correct over time.
- Historical regular-season years are not needlessly reloaded by routine update.

## Research Semantics

- Game logs are per-game summary facts, not play-by-play.
- They are useful for game/team/player identity cross-checks, historical game outcomes, lineups, park/umpire metadata, and aggregate tie-outs.
- They cannot substitute for event/pitch sequence data where event-level grain is required.
- A game-log result is postgame knowledge; predictive features must use only history before the target game's cutoff.

## Dependencies

- `manifest`
- pandas / zipfile / psycopg
- generic scoped loader
- run tracking, DB, health helpers

## Downstream Consumers

- Game identity/outcome and historical coverage cross-validation.
- Research game-grain tie-outs against Retrosheet CSV/event and MLB API sources.
- Historical lineup/umpire/park/team summary research where the game-log product has fields unavailable in another source.

## Known Quirks / Decisions

- The source is headerless; field order is contractual.
- Postseason is separate from regular-season yearly logs.
- Regular and postseason raw tables are deliberately separate.
- Sequential download/load behavior is preferred over unproven Retrosheet concurrency.

## Work Guidance

- Verify field-count/layout changes against both Retrosheet documentation and a real source sample before modifying `GAMELOG_FIELDS`.
- Preserve regular/postseason source separation.
- Do not derive a false all-game completeness assumption from the regular table alone.
- Keep per-year/type scoped idempotency and manifest replay behavior.

## Verification

For changes, verify:

- 161-field parsing on representative old/modern seasons;
- correct yearly member selection inside ZIPs;
- `_season` scoped rerun idempotency;
- each postseason archive maps to the intended `_type` and replaces only that type;
- current-year + special-archive update behavior;
- representative game tie-outs across CSV/event/game-log products;
- health on both regular and postseason tables.

## Child DOX Index

No child DOX files. This is a leaf connector contract.