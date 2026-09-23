## Purpose

Defines how a team-era row in `core.team` resolves to a permanent franchise
identity and that franchise's current Retrosheet code, so any consumer that
needs "today's code for this team" gets one correct, self-updating answer
instead of hand-patched literals scattered across the codebase.

## ADDED Requirements

### Requirement: A team-era row resolves to a franchise when a crosswalk exists

The system SHALL link a `core.team` row to a `core.team_franchise` row
whenever that team-era's `retro_team_id` has a matching row in
`raw.lahman_teams` (joined on `teamidretro`) whose `franchid` also appears
in `raw.lahman_teams_franchises`.

The system SHALL leave `core.team.franchise_id` null, not a guessed value,
when no such crosswalk row exists (for example the pre-1969 Negro League
team-eras Lahman's own franchise data does not cover).

#### Scenario: A modern team-era resolves to its franchise

- **WHEN** `core.team` has a row for `retro_team_id = 'ATH'` and
  `raw.lahman_teams`/`raw.lahman_teams_franchises` carry a matching
  crosswalk entry for that code
- **THEN** that `core.team` row's `franchise_id` is populated with the
  Athletics franchise's `franchise_id`

#### Scenario: A team-era with no Lahman crosswalk stays honestly unresolved

- **WHEN** a `core.team` row's `retro_team_id` has no matching row in
  `raw.lahman_teams`
- **THEN** that row's `franchise_id` is null
- **AND** no other franchise's `franchise_id` is assigned to it by guessing

### Requirement: A franchise's current code is its most recently started team-era, not whichever era is flagged active

`core.team_franchise.current_retro_team_id` SHALL be the `retro_team_id` of
the team-era row with the greatest `first_year` among that franchise's
resolved `core.team` rows. It SHALL NOT be chosen by `core.team.last_year`
(a franchise's retired code can still be marked `last_year = 9999` in
source data that has not yet caught up to a real code reissue).

#### Scenario: A relocated franchise's retired code is not treated as current

- **WHEN** a franchise has two `core.team` eras — an older `retro_team_id`
  with `last_year = 9999` from stale source data, and a newer
  `retro_team_id` with a later `first_year`
- **THEN** `core.team_franchise.current_retro_team_id` for that franchise is
  the newer `retro_team_id`, not the one marked `last_year = 9999`

#### Scenario: A franchise with one era resolves trivially

- **WHEN** a franchise has exactly one resolved `core.team` era
- **THEN** `core.team_franchise.current_retro_team_id` is that era's
  `retro_team_id`

### Requirement: A season-scoped consumer resolves a record to its own era, not to a single franchise-wide anchor

A consumer that resolves a dated/seasoned external record (for example
Lahman's own per-season team statistics) to a `core.team` row SHALL
prefer a direct match on that record's own `retro_team_id`, scoped to the
`core.team` era whose year range contains the record's season. It SHALL
fall back to another `core.team` row sharing the same `franchise_id`
(still scoped to that season) only when the record's own `retro_team_id`
has no matching `core.team` row at all for that season.

The system SHALL NOT unconditionally resolve every era of a franchise to
one single anchor code (neither the oldest nor the newest), because a
franchise can have more than one historical code change — resolving
everything to one anchor would misattribute or drop every other era's
real records, not just the one relocation being handled.

#### Scenario: Each era of a multiply-relocated franchise resolves to its own record

- **WHEN** a franchise has three or more `core.team` eras, each with its
  own distinct `retro_team_id` and year range, and dated records exist for
  more than one of those eras
- **THEN** each record resolves to the `core.team` row for its own era,
  not to any other era's row

#### Scenario: A record whose own code has no matching era yet falls back within its franchise

- **WHEN** a dated record's `retro_team_id` has no matching `core.team`
  row, but another `core.team` row shares that record's franchise and its
  year range contains the record's season
- **THEN** the record resolves to that other row, rather than being
  silently dropped

### Requirement: A historical or old-coded team resolves to the correct current code for a consumer with no season context of its own

A consumer that specifically needs "the franchise's real, current code"
with no season/year of its own to scope by (for example matching an
external source's live ticker/alias) SHALL resolve to that franchise's
`current_retro_team_id`.

This requirement is distinct from season-scoped resolution above: it
applies only to a consumer that has no season context to resolve
against in the first place, not to a general substitute for it.

#### Scenario: An external source's current-season reference resolves to the current code

- **WHEN** a franchise has real records filed under both its older and
  newer `retro_team_id`, and a consumer with no season context needs the
  franchise's current, real-world code
- **THEN** that consumer resolves to `core.team_franchise.current_retro_team_id`,
  not an older retired code

### Requirement: An expected-but-unresolved franchise link is surfaced, not silent

`mlb doctor` SHALL report a failure when a `core.team` row's `retro_team_id`
has a matching row in `raw.lahman_teams` (i.e. a crosswalk is expected to
exist) but `core.team.franchise_id` is still null after conformance runs.

`mlb doctor` SHALL NOT report a failure for a `core.team` row whose
`retro_team_id` genuinely has no `raw.lahman_teams` match (an expected,
documented gap, not a defect).

#### Scenario: A team the Lahman crosswalk should cover but doesn't is flagged

- **WHEN** a `core.team` row's `retro_team_id` matches a `raw.lahman_teams`
  row but ends up with a null `franchise_id` after `mlb conform` runs
- **THEN** `mlb doctor` reports a failure naming the unresolved row

#### Scenario: A known, documented historical gap does not fail the health check

- **WHEN** a `core.team` row's `retro_team_id` has no `raw.lahman_teams`
  match at all
- **THEN** `mlb doctor` does not report a failure for that row
