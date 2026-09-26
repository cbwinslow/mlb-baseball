## ADDED Requirements

### Requirement: The canonical feature store publishes model-admission evidence

The canonical DuckDB `feat.*` feature store SHALL provide a versioned,
researcher-facing feature-set declaration and readiness result before it is
used as the input to a new predictive model experiment. This evidence SHALL
identify the build/version, selected columns, time semantics, null policy,
coverage, and required validation results; it SHALL not present legacy
`gold.game_feature` compatibility columns as part of that declared surface.

#### Scenario: A researcher chooses a model-ready feature surface

- **WHEN** a researcher follows the documented feature-store workflow to build
  a model training matrix
- **THEN** they receive the declared DuckDB `feat.*` feature set and its
  readiness evidence, with legacy `gold.game_feature` clearly excluded from
  that workflow

#### Scenario: The build is stale or has failed a required audit

- **WHEN** a DuckDB feature build is missing, stale for its declared source, or
  fails a required model-admission audit
- **THEN** the readiness result identifies the failure and does not label the
  feature version model-ready
