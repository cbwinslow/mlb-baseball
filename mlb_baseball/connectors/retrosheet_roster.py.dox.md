# `retrosheet_roster.py` DOX

## Purpose

Own Retrosheet's annual team roster archive, landing one source row per player/team/season into `raw.retrosheet_roster` for historical player-team identity and roster research.

## Ownership

Implementation: `retrosheet_roster.py`.

Primary output:

- `raw.retrosheet_roster`

Public connector capabilities:

- `bootstrap()`
- `update()`
- `health_check()`

## Source Contract

- Source: `https://www.retrosheet.org/rosters.zip`.
- Coverage currently spans 1871 through the latest published Retrosheet roster season.
- Each team-season is a headerless `.ROS` file with fields:
  `player_id, last_name, first_name, bats, throws, team_id, position`.
- The archive also includes `UMPIRES{year}.txt` files; those are intentionally not landed here because Retrosheet's biodata umpire product is the richer identity source. Do not broaden this connector merely because the ZIP contains unrelated file types.
- Rights/profile behavior remains owned by repository source-rights metadata/docs.

## Filename / Season Contract

The `.ROS` row data does not repeat season metadata. The season must be derived from the filename.

- Filenames use `{team}{year}.ROS`.
- Team codes can themselves contain digits.
- `_ROS_NAME_RE` therefore anchors on the final fixed four-digit year immediately before `.ROS`; do not replace it with a naive first-digit split.
- `_season` is added from the parsed filename year.

The `team_id` field inside source rows remains the source team identity; filename parsing is for season/file selection, not an alternate canonical identity algorithm.

## Runtime / Idempotency Contract

- `rosters.zip` is a compact whole-history artifact.
- Bootstrap and update both perform a full replacement rather than maintaining hundreds of independent file scopes.
- The download is persisted through the source manifest before parsing.
- The run commits once after the full coherent roster DataFrame is loaded.
- Full reload is expected to remain cheap relative to more granular historical products; do not add per-season complexity unless source size/runtime becomes a measured problem.

## Data / Research Semantics

- Raw grain is player-team-season/source roster row.
- Roster membership is evidence for team affiliation/identity, not proof of game participation.
- Player IDs are Retrosheet source identifiers that should resolve through canonical player crosswalk/conformance.
- Position/bats/throws are source roster attributes and can have historical missingness/inconsistency; preserve source facts rather than imputing in raw.

## Dependencies

- `manifest`
- pandas / zipfile / regex / psycopg
- generic full-replace loader
- run tracking, DB, health helpers

## Downstream Consumers

- Canonical player/team identity and historical team-affiliation research.
- `retrosheet_box.py` uses the same official roster archive as support data for Chadwick `cwbox` where source archives lack roster files.
- Research features requiring prior roster/team context, subject to the appropriate historical availability semantics.

## Known Quirks / Decisions

- Team codes may end in digits, making simplistic filename parsing incorrect.
- Umpire-list members inside the archive are intentionally ignored by this connector.
- Whole-history replacement is deliberate because the source artifact is small.

## Work Guidance

- Preserve filename parsing anchored on the terminal four-digit season.
- Keep unrelated archive members excluded unless a new distinct product contract is intentionally added.
- Coordinate roster schema/ID changes with conformance and `retrosheet_box.py` support-file logic.
- Do not infer player game participation from roster presence alone.

## Verification

For changes, verify:

- filenames with team codes containing digits parse the correct season;
- non-ROS archive members are ignored;
- source field count/order remains correct;
- `_season` is assigned correctly across old/modern files;
- full reload is repeatable/idempotent;
- downstream player/team identity tests and `retrosheet_box` support-file tests when relevant;
- health detects an empty/missing roster load.

## Child DOX Index

No child DOX files. This is a leaf connector contract.