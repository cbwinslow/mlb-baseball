## Purpose

Defines how durable project direction, subsystem contracts, bounded work, and
machine-verifiable completion relate so that architectural reviews become
actionable repository state instead of parallel documentation.

## Requirements

### Requirement: The project has one constitutional North Star and invariant owner

The project SHALL keep its project-wide North Star and concise durable
engineering invariants in `openspec/project.md`. Detailed subsystem semantics
SHALL live in the nearest owning contract or durable capability spec and SHALL
be linked rather than duplicated as a competing rule set.

#### Scenario: A review introduces a durable project-wide rule

- **WHEN** a review identifies a rule that must apply across multiple subsystems
- **THEN** the concise rule is incorporated into the project constitution
- **AND** implementation detail is assigned to an existing owning contract or a
  bounded OpenSpec change

### Requirement: Every material review finding has a disposition

A correctness-, architecture-, or product-significant review finding SHALL be
mapped to one of: an existing durable owner, an active OpenSpec change, a named
future OpenSpec change behind the existing phase gates, an executable
verification gate, or an explicitly rejected/archived rationale.

#### Scenario: A holistic review is completed

- **WHEN** the review is accepted as planning input
- **THEN** no high-priority finding remains only in chat or an unowned checklist

### Requirement: Completion combines a rule, a gate, and evidence when practical

Correctness-critical completion criteria SHALL define the human-readable
requirement, the executable check that can disprove it where practical, and the
evidence artifact that records the result.

#### Scenario: Stable identity is declared complete

- **WHEN** stable canonical identity work is marked complete
- **THEN** the contract states the identity rule
- **AND** an automated repeat-run/equivalence check exists
- **AND** the production or representative verification evidence is recorded

### Requirement: Platform Convergence gates broad expansion

Broad new Engine/model/market/product expansion SHALL NOT bypass the current
Platform Convergence gate merely because an idea appears in a later roadmap
phase. Existing owner-approved bounded work may continue, but unresolved
foundation defects remain higher priority.

#### Scenario: A new speculative modeling program is proposed

- **WHEN** Platform Convergence has unresolved required blockers
- **THEN** the proposal is queued behind the gate unless it directly fixes a
  blocker or the owner explicitly reprioritizes the project

### Requirement: GitHub issues do not become a second specification

GitHub issues MAY index and track significant OpenSpec changes, but the
authoritative detailed implementation requirements and checkboxes SHALL remain
in the OpenSpec change and its durable specs.

#### Scenario: An issue tracks an OpenSpec change

- **WHEN** the issue is updated
- **THEN** it links the owning OpenSpec change and completion criteria rather
  than copying the full task list
