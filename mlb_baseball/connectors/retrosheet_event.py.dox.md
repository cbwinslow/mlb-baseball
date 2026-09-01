# `retrosheet_event.py` DOX

## Purpose

Own Retrosheet's authoritative raw play-by-play event-file ingestion, parsed locally through Chadwick `cwevent` and `cwgame`. This source is distinct from the official pre-parsed CSV connector (`retrosheet.py`): both are retained because event files are the source-of-record and local parsing avoids permanent dependence on Retrosheet's own CSV generation choices.

## Ownership

Implementation: `retrosheet_event.py`.

Primary raw outputs:

- `raw.retrosheet_event` — per-play Chadwick `cwevent` output.
- `raw.retrosheet_game` — per-game Chadwick `cwgame` output.

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

- Source base: `https://www.retrosheet.org/events`.
- Regular-season play-by-play coverage is approximately 1910–present/current published archive, plus special Federal League/other source-era coverage documented by Retrosheet.
- Retrosheet also publishes special whole-history archives for postseason, All-Star, and Negro League play-by-play.
- Some historical seasons contain deduced/reconstructed play-by-play rather than contemporaneous full event records. Raw currently does not separately flag every deduced row; preserve this known limitation in research coverage metadata rather than pretending all eras have equal evidentiary quality.
- Box-score-only eras/games are intentionally excluded here and owned by `retrosheet_box.py`.
- Rights/profile rules remain owned by repository source-rights metadata/docs.

## Archive / Parsing Contract

- Most regular-season event downloads are decade/multi-year ZIPs, not one independent ZIP per season.
- Archives mix event, team, and roster files across years.
- Chadwick tools must run one year at a time because the `-y` year controls team/roster lookup.
- The connector extracts each downloaded archive to a temporary directory, splits files into per-year directories through `chadwick_tools.split_by_year()`, parses there, and discards extraction afterward.
- The downloaded ZIP remains the durable replay/provenance artifact through `manifest.download()`.
- Do not keep expanded archives as the primary persisted source or parse multi-year archives in one Chadwick invocation.

## Team-File Quirk

- Some special event archives, notably Negro League play-by-play, may lack `TEAM{year}`/roster files.
- `cwevent`/`cwgame` require a team file to exist even when the event records themselves carry enough team identifiers for these products.
- `_split_by_year()` creates an empty placeholder team file only for this event/cwgame use case.
- Do **not** generalize that workaround to `cwbox`: box-score parsing requires real team metadata and has a different contract in `retrosheet_box.py`.

## Scope / Idempotency Contract

Every parsed DataFrame receives:

- `_season` — actual season/year for analysis.
- `_group` — source archive family (`pbp`, `postseason`, `allstar`, `negro_league`).
- `_scope` — `<year>_<group>`, used for scoped replacement.

`_season` and `_scope` must remain distinct. Multiple archive families can legitimately contribute rows for the same season. Replacing by `_season` alone previously caused later special archives to delete already-loaded regular-season rows.

Do not simplify scoped replacement to season-only without proving that overlapping archive groups have been structurally eliminated.

## Failure / Resume Contract

- Per-year parsing is isolated: one Chadwick failure skips that year and preserves other successfully parsed years from the same archive.
- Per-archive bootstrap work is also isolated: one bad archive must not abort every later archive.
- Successful archive units commit independently.
- Manifest status allows a resumed bootstrap to skip already-loaded archives unless `force=True`.
- This resilience is based on a real historical failure where one `cwevent` field-range incompatibility in 1919 caused an entire full-history run to produce no durable result before isolation was added.

## Update Contract

- Current decade regular-season archive is re-downloaded with `force=True` because Retrosheet appends/corrects it in place.
- Postseason and All-Star whole-history archives are also refreshed because they grow over time.
- Historical closed decade archives are not needlessly re-parsed on routine update.

## Chadwick Contract

- `cwevent` and `cwgame` are required runtime tools.
- Field/version compatibility is project-owned through `chadwick_tools.py`; do not alter field specs here independently.
- Health must report missing Chadwick tools clearly.
- When changing Chadwick versions/fields, validate representative early/modern/special archives rather than one modern season only.

## Data / Research Semantics

- `raw.retrosheet_event` is source/event history, not automatically a pregame feature source.
- Event outcomes can feed descriptive stats and **prior-history** predictive features only when the feature window ends before the target game.
- Historical coverage quality and deduced-era limitations should remain visible in coverage metadata.
- Source game/team/player IDs require downstream conformance into canonical identities.

## Dependencies

- `manifest` / `archive`
- `chadwick_tools`
- `load_dataframe`
- `track_run`
- PostgreSQL / health helpers

## Downstream Consumers

- `conform.py` uses Retrosheet event/game facts for canonical game/play/player/team reconciliation.
- `gold.batting_game` / `gold.pitching_game` and later grain-complete statistics depend on atomic Retrosheet event facts.
- Official Retrosheet CSV and game-log products provide independent cross-checks at different grains.

## Work Guidance

- Preserve event-file and CSV connector separation.
- Preserve archive group in load scope.
- Never solve a Chadwick failure by dropping a year/archive silently without documenting health/coverage impact.
- Changes to event fields should review grain/stat builders and conformance downstream.
- Keep source archive download/replay manifest behavior intact.

## Verification

For behavior changes, verify:

- multi-year archive split into correct years;
- placeholder team-file behavior for the archives that need it;
- `cwevent` and `cwgame` parsing on representative eras;
- `_season`/`_group`/`_scope` correctness and overlapping-group idempotency;
- one-year parse failure does not lose other years;
- one-archive failure does not abort later archives;
- manifest resume and forced current-archive refresh;
- downstream conformance and batting/pitching game tie-outs;
- health behavior when Chadwick tools are missing.

## Child DOX Index

No child DOX files. This is a leaf connector contract.