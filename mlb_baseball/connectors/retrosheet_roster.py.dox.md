# retrosheet_roster.py DOX

## Purpose

Own Retrosheet annual team-roster ingestion: one raw row per player-team-season
from the official `rosters.zip` product.

## Ownership

Source implementation: `retrosheet_roster.py`.

Owned raw relation: `raw.retrosheet_roster`.

Registry source name: `retrosheet_roster`.

Focused integration test: `tests/integration/test_retrosheet_roster_load.py`.

## Source and Parsing Contracts

- Source archive: `https://www.retrosheet.org/rosters.zip`.
- Each roster is a headerless `{team}{year}.ROS` file with fields:
  `player_id`, `last_name`, `first_name`, `bats`, `throws`, `team_id`, `position`.
- Team IDs can end in digits. Filename parsing therefore uses a regex anchored on
  the final four-digit year before `.ROS`; do not replace it with naive slicing
  that assumes alphabetic team codes.
- `_season` is derived from the roster filename and added as project metadata.
- Bundled annual umpire lists are intentionally not loaded here because richer
  umpire identity data is already owned by the Retrosheet reference connector.

## Runtime Contracts

- The archive is a small whole-history source; `bootstrap()` and `update()` both
  full-reload the relation.
- The source file is downloaded/persisted through the manifest layer before
  parsing.
- Non-roster archive members are ignored explicitly.
- A rerun replaces the snapshot and remains idempotent.
- Player/team identity values remain source-faithful; canonical reconciliation is
  downstream work.

## Downstream Context

Roster rows are useful for player-team-season identity evidence and for preparing
Chadwick box/event parsing contexts. Do not silently normalize source player/team
IDs in raw.

## Verification

Run:

```bash
uv run pytest tests/integration/test_retrosheet_roster_load.py -q
uv run ruff check mlb_baseball/connectors/retrosheet_roster.py tests/integration/test_retrosheet_roster_load.py
```

Include a filename/team code containing a digit when changing filename parsing.
