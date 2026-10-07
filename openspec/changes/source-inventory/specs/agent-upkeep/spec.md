## ADDED Requirements

### Requirement: Upkeep has one documented command per action
Detecting gaps, detecting source changes, planning a repair and running a repair SHALL each have one `mlb` command with consistent flags and machine-readable (`--json`) output, documented in the namespace index.

#### Scenario: Agent lists upkeep actions
- **WHEN** an agent reads the namespace index
- **THEN** it finds each upkeep action, its flags, whether it writes, and its cost

### Requirement: Writing commands support a dry run
Every command that can write to production SHALL accept `--dry-run` that prints the planned work and writes nothing.

#### Scenario: Dry run
- **WHEN** a repair command runs with `--dry-run`
- **THEN** it lists the items it would load and the database is unchanged

### Requirement: An upkeep skill governs agent behaviour
A skill SHALL tell an agent to read coverage and drift reports first, choose only listed commands, state any production write in one plain sentence and wait for a named yes, and log the action.

#### Scenario: Agent finds a gap
- **WHEN** an agent is asked to fix a gap
- **THEN** it runs the dry run, shows the plan, and asks before the write
