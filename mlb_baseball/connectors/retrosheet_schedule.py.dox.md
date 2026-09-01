# `retrosheet_schedule.py` DOX

## Purpose

Own Retrosheet's **planned schedule** product, landing scheduled games (including postponement/makeup information) into `raw.retrosheet_schedule`. This is schedule intent/history, not the authoritative final game-result source.

## Ownership

Implementation: `retrosheet_schedule.py`.

Primary output:

- `raw.retrosheet_schedule`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

- Source: `https://www.retrosheet.org/schedule/schedule.zip`.
- The archive contains headered `{year}schedule.csv` files.
- Coverage currently spans 1877 through the latest published/future schedule year present in the source.
- Rows include planned date/game number/visitor/home/day-night information plus postponement reason and makeup date where Retrosheet provides them.
- Schedule rows can differ from final played-game facts because games are postponed, cancelled, rescheduled, or otherwise changed.
- Rights/profile behavior remains owned by repository source-rights metadata/docs.

## Column Contract

The source header repeats generic `League` and `Game` labels for visitor and home columns. Pandas disambiguates the second occurrences as `.1` names.

`COLUMN_RENAMES` deliberately maps those repeated source positions to:

- `visitor_league`
- `visitor_game`
- `home_league`
- `home_game`

This is a structural clarity rename needed to preserve which side the source column represents; it is not semantic normalization of the underlying values.

Do not rename other raw source fields simply for stylistic consistency without a raw-schema migration decision.

## Runtime / Idempotency Contract

- `schedule.zip` is small and treated as one whole-history artifact.
- Bootstrap and update both fully reload `raw.retrosheet_schedule`.
- Each member contributes `_season` derived from its filename.
- Full replacement is deliberately simpler than per-year scoped replacement for this compact, frequently updated planning product.
- Download/replay is persisted through the manifest before parsing.

## Point-in-Time / Research Semantics

This product can be useful for schedule/planning context, but historical modeling must distinguish **what the current archive says now** from what was actually known at an earlier date.

- A current full schedule archive is not automatically a historical-as-of schedule snapshot.
- Postponement/makeup fields may encode information learned after the originally scheduled time.
- Do not use current corrected schedule rows to claim an exact pregame historical information state unless the necessary observation/version history exists.
- Final game identity/outcome belongs in canonical game sources/conformance; schedule is supporting evidence.

## Dependencies

- `manifest`
- pandas / zipfile / psycopg
- generic full-replace loader
- run tracking, DB, health helpers

## Downstream Consumers

- Schedule completeness/planning research.
- Game/date/team reconciliation support where source schedule evidence is useful.
- Future forecasting workflows that need upcoming scheduled games, with clear distinction between current schedule and historical-as-of schedule state.

## Known Quirks / Decisions

- Planned schedule and final played game are different concepts.
- Repeated source headers require explicit visitor/home disambiguation.
- Whole-history reload is intentional because the source is compact and future/current schedules can change.

## Work Guidance

- Preserve the source planning semantics rather than treating this table as a final game fact table.
- If historical schedule observation snapshots become necessary, add a new observation/version contract rather than pretending repeated full reloads preserve old states.
- Verify archive member naming and repeated header behavior when source format changes.
- Coordinate any game-identity use with conformance rather than creating a second canonical game mapper here.

## Verification

For changes, verify:

- only schedule CSV members are loaded;
- filename -> `_season` parsing;
- visitor/home League/Game columns are disambiguated correctly;
- full reload is repeatable/idempotent;
- postponement/makeup source fields are preserved;
- downstream schedule/game reconciliation does not confuse planned and final game facts;
- health detects an empty/missing schedule load.

## Child DOX Index

No child DOX files. This is a leaf connector contract.