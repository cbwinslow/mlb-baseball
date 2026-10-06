## Purpose
Defines which games form the major-league regular-season pool used by models and features, and how Negro League games are flagged without being deleted.

## ADDED Requirements

### Requirement: Negro League games are flagged from a source, not guessed
`conform` SHALL mark each `core.game` row as Negro League when both clubs are in Retrosheet's Negro League club registry for that season, and SHALL NOT use `core.team.league IS NULL` as the rule.

#### Scenario: A Negro League regular game
- **WHEN** a game is between two registry Negro League clubs (for example BIR and ATN, 1937)
- **THEN** its scope flag marks it Negro League

#### Scenario: A NULL-league club that is not Negro League
- **WHEN** a game involves a NULL-league club that is not in the registry
- **THEN** it is not flagged as Negro League

### Requirement: MLB Stats API games are flagged by the same registry
Games that arrive from the MLB Stats API (team ids in the 1400s and 1500s, under `sportId=1`) SHALL be matched to the same registry (by club name and season) and flagged by the same rule. A club that cannot be matched SHALL be reported, not guessed.

#### Scenario: An API-only Negro League game
- **WHEN** `raw.mlb_schedule` holds a game between two clubs matched to the registry (for example Birmingham Black Barons, 1930)
- **THEN** its scope flag marks it Negro League, whether or not Retrosheet holds the game

#### Scenario: An unmatched club
- **WHEN** an API club with an id in the 1400s or 1500s has no registry match
- **THEN** it is listed as unmatched and its games are not silently treated as MLB

### Requirement: Mixed games are their own category
A game between one registry club and one non-registry club SHALL carry a distinct `mixed` scope value, so it is neither counted as MLB nor as Negro League.

#### Scenario: An exhibition against an MLB club
- **WHEN** a game has one registry club and one AL/NL club
- **THEN** its scope is `mixed` and it is absent from `core.game_mlb`

### Requirement: The flag is derived and rebuilt from raw data
The flag SHALL be computed by `conform` only from `raw.*` tables (the registry `raw.retrosheet_team0` and the API team tables), SHALL carry no hand-entered values, and SHALL be identical after a bootstrap from an empty database.

#### Scenario: Bootstrap from empty
- **WHEN** a fresh database is bootstrapped and conformed from the same raw inputs
- **THEN** the flagged game counts per season equal those of the long-running database

### Requirement: Raw data and flagged games are preserved
The change SHALL NOT modify or delete any `raw.*` table, and flagged games SHALL remain in `core.game`.

#### Scenario: Re-running conform
- **WHEN** `conform` runs twice
- **THEN** the flagged game count is identical and every `raw.*` row count is unchanged

### Requirement: One major-league pool for models
A view `core.game_mlb` SHALL expose regular-season games that are not flagged Negro League, and model, feature-store and readiness code SHALL read that view instead of repeating the filter.

#### Scenario: Game-win training window
- **WHEN** the game-win feature build reads its games
- **THEN** no flagged Negro League game appears in `feat.game`

### Requirement: Downstream effect is measured and recorded
The change SHALL record before/after gold backbone season totals, Lahman and Baseball-Reference reconciliation results and Retrosheet tie-out results, and every difference SHALL be explained.

#### Scenario: Lahman reconciliation
- **WHEN** gold season totals are compared with Lahman before and after the flag
- **THEN** differences appear only in seasons that contained flagged games and each is listed in `results.md`
