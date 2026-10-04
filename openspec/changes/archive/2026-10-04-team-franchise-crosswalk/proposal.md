## Why

A team's Retrosheet code changes whenever a franchise relocates or is
reissued a new code (most recently the Athletics: `OAK` through 2024, `ATH`
from 2025), but `core.team` stores one row per team-era with no link back to
the permanent franchise. Every consumer that needs "the current code for
this franchise" has hand-patched the same fact with duplicated,
easy-to-miss-a-spot `CASE WHEN 'ATH' THEN 'OAK'` SQL: `report.py` (two
places) and, as of the most recent fix, `mlb_baseball/model/season.py`
(three query sites). `docs/DECISIONS.md` ADR-013 already named this exact
gap ("No franchise-continuity table yet linking e.g. Boston/Milwaukee/
Atlanta Braves — a known, deliberate gap until something needs it") and
ADR-029 established the player-identity-style precedent (`mlb_team_id`, a
stable numeric anchor) this change extends to a real franchise dimension.

## What Changes

- New `core.team_franchise` table: one row per real MLB franchise (not per
  team-era), each carrying a stable `franchise_id`, a display name, and a
  `current_retro_team_id` — the code that should be used whenever "today's
  code for this team" is needed, instead of a hand-typed literal.
- New `core.team.franchise_id` column (nullable) linking every team-era row
  to its franchise.
- New `conform.py` builder step, following the existing `_build_team_alias`
  pattern, populating both from data already ingested
  (`raw.lahman_teams_franchises` + `raw.lahman_teams.franchid`/
  `teamidretro`, already confirmed to match `core.team.retro_team_id`) —
  no new external source. `current_retro_team_id` is resolved as the
  team-era row with the greatest `first_year` for that franchise, not
  "whichever era `core.team.last_year` marks active" — verified against
  real production data that Retrosheet's own source file still marks the
  retired `OAK` code active (`last_year = 9999`) while `ATH` is the real
  current code.
- `mlb_baseball/model/season.py` (`load_schedule_from_db`,
  `team_strength_asof`, `team_wins_asof`) and `mlb_baseball/report.py`
  updated to resolve through `core.team_franchise` instead of inline
  `CASE WHEN` SQL, retiring the just-added ad hoc fix.
- New `mlb doctor` health check: fails when any `core.team` row (whose
  franchise is expected to be resolvable, i.e. it has a real Lahman
  crosswalk row available) has a null `franchise_id` — surfaces a future
  new/renamed team the Lahman data hasn't caught up to yet, instead of
  silently mis-resolving it.
- A new ADR in `docs/DECISIONS.md`, in the style of ADR-013/028/029,
  recording this decision.

Explicitly out of scope (raised and deliberately deferred with the owner):
making `season.py`'s hardcoded `ALL_MLB_TEAMS`/`MLB_DIVISIONS` lists
dynamically derived from the database (a new expansion team is a content
update, not a code-resolution bug), and point-in-time division/league
realignment history (teams switching divisions over time is a separate,
larger problem this change does not touch).

## Capabilities

### New Capabilities
- `team-identity`: how a team-era row in `core.team` resolves to a stable
  franchise identity and that franchise's current Retrosheet code, by
  analogy to the existing `player-identity` capability.

### Modified Capabilities
(none — no existing spec capability currently governs team-code
resolution; `season.py`/`report.py`'s prior `CASE WHEN` behavior was
undocumented ad hoc code, not a specified requirement)

## Impact

- **Schema**: one new migration — `core.team_franchise` table,
  `core.team.franchise_id` column, supporting indexes.
- **Code**: `mlb_baseball/conform.py` (new builder + backfill step,
  wired into `run()` after `_build_teams()`), `mlb_baseball/model/season.py`,
  `mlb_baseball/report.py`, `mlb_baseball/health.py` (or wherever `mlb
  doctor`'s checks live) for the new health check.
- **Tests**: new integration tests in `tests/integration/test_conform.py`
  reproducing the actual mechanism (an old era's code resolving to the
  wrong current code — not just an Athletics-specific symptom check), plus
  updates to the `season.py`/`report.py` tests that currently assert on the
  inline `CASE WHEN` behavior.
- **Docs**: `docs/DECISIONS.md` (new ADR), `mlb_baseball/AGENTS.md` or
  `conform.py`'s DOX if the new builder needs documenting there.
- **No new external data source or paid dependency.**
