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

### Requirement: A franchise also has a stable legacy code for consumers that require one fixed identity across a relocation

`core.team_franchise.legacy_retro_team_id` SHALL be the `retro_team_id` of
the team-era row with the smallest `first_year` among that franchise's
resolved `core.team` rows (the franchise's original code) — the opposite
end from `current_retro_team_id`.

A consumer that must key a franchise's full history to one fixed
`core.team` row for reasons independent of "what code is current today"
(for example a table whose uniqueness constraint spans a team identifier
and a season, or a caller with its own separate, already-established
current-code convention it is not this change's job to update) SHALL
resolve through `legacy_retro_team_id`, not `current_retro_team_id` — so
adding this crosswalk does not, by itself, change what such a consumer
already outputs today.

#### Scenario: A franchise's original code anchors its stable identity

- **WHEN** a franchise has two `core.team` eras with different
  `retro_team_id` values
- **THEN** `core.team_franchise.legacy_retro_team_id` for that franchise is
  the older era's `retro_team_id`

### Requirement: A historical or old-coded team resolves to the correct current code in downstream results

Any consumer that specifically needs "the franchise's real, current code"
(for example matching an external source's live ticker/alias) SHALL
resolve a real record filed under a franchise's older `retro_team_id` to
that franchise's `current_retro_team_id`, so the franchise's full real
history is represented under one code rather than being split or dropped.

#### Scenario: An external source's current-season reference resolves to the current code

- **WHEN** a franchise has real records filed under both its older and
  newer `retro_team_id`, and a consumer needs the franchise's current,
  real-world code
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
