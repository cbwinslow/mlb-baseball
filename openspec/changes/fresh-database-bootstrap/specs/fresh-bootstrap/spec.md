# Spec Delta

## Purpose
Defines what a new user's bootstrap must achieve on an empty database and how failures are reported.

## ADDED Requirements

### Requirement: Bootstrap works from an empty database
The documented bootstrap sequence SHALL build every table the project declares from an empty PostgreSQL database, using only documented commands and configuration.

#### Scenario: No hidden manual step
- **WHEN** a new user runs the documented sequence on an empty database
- **THEN** every raw table with a coverage expectation reaches it, or is listed as skipped with a reason (profile, missing key, source gap)

#### Scenario: Sequence is proven automatically
- **WHEN** the test suite runs
- **THEN** a fixture slice goes from an empty schema through migrate, bootstrap, conform and audit without a failure

### Requirement: Failures are named and recoverable
A failed step SHALL stop the chaining command with the step name and the exact command that retries it, and re-running the command SHALL skip work already done.

#### Scenario: Re-run after failure
- **WHEN** the command is run again after a failed step is fixed
- **THEN** completed steps change nothing and the failed step runs
