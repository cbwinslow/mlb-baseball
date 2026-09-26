## Purpose

Defines the reproducible evidence and finite decisions that determine whether a
versioned `feat.*` feature set is safe to admit to a new chronological MLB
model experiment, and makes that evidence useful to outside researchers.

## ADDED Requirements

### Requirement: A declared model feature set has a complete admission contract

The system SHALL publish a versioned feature-set declaration for the first
game-win ML experiment. It SHALL list every selected `feat.*` column, its
entity/grain, source relation, availability semantics, null policy, and the
evidence that supports its use. It SHALL explicitly exclude labels,
post-game fields, market outcomes, and legacy `gold.game_feature` columns.

#### Scenario: A researcher inspects the game-win feature set

- **WHEN** a researcher opens the published declaration for a feature version
- **THEN** they can determine every input column, its point-in-time meaning,
  its expected coverage limits, and why it is admitted or excluded without
  reading model implementation code

#### Scenario: A prohibited field is proposed as a training input

- **WHEN** a label, post-game field, market outcome, or legacy compatibility
  column is included in a declared game-win feature set
- **THEN** feature-set validation reports the field as ineligible and the set
  cannot receive a ready result

### Requirement: Model readiness is reported from reproducible evidence

The system SHALL provide a machine-readable and human-readable readiness
report for a named feature version and declared source build. The report SHALL
identify the source/build version, execute or consume the backbone tie-out and
feature-store leakage evidence, and report relation integrity, coverage, null
rates, and each selected feature's admission evidence.

#### Scenario: A complete feature build is ready

- **WHEN** the declared source build passes required backbone tie-outs,
  feature-store leakage checks, relation-integrity checks, and every selected
  feature has complete admission evidence
- **THEN** the readiness report returns `ready` and records the evidence and
  observed coverage for that exact build/version

#### Scenario: A required check fails or evidence is missing

- **WHEN** a required check fails, a selected feature lacks its declared
  provenance/time/null/test evidence, or unexplained missingness is observed
- **THEN** the report returns `not_ready`, names each blocking condition, and
  does not imply that the feature set is safe for model training

### Requirement: Feature and model work have finite completion decisions

The project SHALL treat a feature version as complete once its admission
contract and readiness report are green for its declared coverage window. A
future model candidate SHALL use a predeclared chronological evaluation window
and baseline comparison; it SHALL be recorded as promoted, retained as a
baseline, or rejected with its evidence, rather than retuned indefinitely.

#### Scenario: A feature version reaches its completion gate

- **WHEN** a feature version has a green readiness report and its documented
  coverage/limitations meet the declared use case
- **THEN** it is frozen for that model experiment and later improvements
  require a new feature version rather than reopening its completion status

#### Scenario: A candidate model does not meet its predeclared comparison rule

- **WHEN** a chronological evaluation does not meet the model candidate's
  predeclared calibration and baseline-comparison rule
- **THEN** the candidate is recorded as a negative result or remains a
  non-promoted experiment, not iteratively tuned without a new approved scope
