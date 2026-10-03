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
