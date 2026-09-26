# retrosheet-parsing Specification

## Purpose

Defines the reusable Python surface for acquiring and interpreting official
Retrosheet files without requiring a system Chadwick installation. The
capability is deliberately independent of the mlb-baseball warehouse.

## Requirements

### Requirement: The Retrosheet package installs without native Chadwick

The package SHALL have a Python-only core installation. Installing the package
with pip or uv SHALL NOT require a C compiler, CMake, autotools, a separately
installed Chadwick executable, PostgreSQL, or mlb_baseball.

Optional dataframe adapters MAY add Python data-library dependencies, but they
SHALL NOT be required to parse source records.

#### Scenario: Clean Python environment

- WHEN a user installs the core package in a supported clean Python environment
- THEN the package imports and its parser/client APIs are usable without any
  Chadwick binary or native build step

### Requirement: Official Retrosheet artifacts are first-class resources

The package SHALL resolve supported resources to official Retrosheet locations
and SHALL return artifact metadata containing the source URL, product identity,
season/group where applicable, local path, byte size, SHA-256, and retrieval
timestamp.

Downloads SHALL be cacheable and replayable. Archive handling SHALL reject path
traversal and malformed archives.

#### Scenario: Cached source is reused

- WHEN an artifact with the expected identity already exists locally
- AND the client recomputes its SHA-256 and it matches the recorded metadata
- THEN the client reuses it without a second network fetch and returns the same
  content hash

#### Scenario: Modified cached source is not trusted

- WHEN a locally cached artifact's recomputed SHA-256 differs from its recorded
  metadata
- THEN the client SHALL NOT return it as valid and SHALL fetch it again or fail
  with an integrity error

### Requirement: Raw records are parsed losslessly

The record reader SHALL stream Retrosheet event files and represent every
recognized record type as a typed object carrying its exact raw source text and
location metadata.

An unrecognized record SHALL NOT be silently discarded.

#### Scenario: Unsupported record in strict mode

- WHEN strict parsing encounters an unsupported record type
- THEN parsing fails with a structured error naming the file, line, game when
  known, raw text, and parser stage

#### Scenario: Unsupported record in diagnostic mode

- WHEN diagnostic parsing encounters an unsupported record type
- THEN it yields an explicit unsupported record containing the untouched raw
  text and the unsupported record is included in coverage counts

### Requirement: Play syntax is separate from game-state mutation

The package SHALL parse a play description into typed components for its primary
event, modifiers, runner advances, fielding/error annotations, and run-credit
annotations without mutating game state.

Each component SHALL retain the source token from which it was parsed.

#### Scenario: A caller only needs syntax

- WHEN a caller parses a play record without constructing a game reducer
- THEN the caller can inspect the event, modifiers, advances, and raw tokens
  without initializing a lineup, score, or base state

### Requirement: Compatibility claims are versioned and evidenced

The package SHALL NOT claim generic "Chadwick compatibility." Any compatibility
surface SHALL name the reference profile, beginning with chadwick-0.10.

Reference testing MAY invoke Chadwick as a development/test oracle, but Chadwick
SHALL NOT be a runtime requirement of the package.

A future production connector replacement SHALL require a recorded field-level
parity report and a list of all unsupported syntax/semantics.

#### Scenario: Upstream Chadwick behavior changes

- WHEN a newer Chadwick release changes event or game output semantics
- THEN the existing chadwick-0.10 profile remains stable and the changed
  behavior is represented by a new compatibility profile rather than silently
  changing old results

### Requirement: Retrosheet's official parsed data provides an independent check

Where Retrosheet publishes a parsed field that maps to a compatibility field,
the validation harness SHALL be able to compare the Python result with both the
selected Chadwick reference output and Retrosheet's official parsed product.

A three-way disagreement SHALL be reported as evidence; validation code SHALL
NOT silently overwrite the native result to match either oracle.

#### Scenario: Reference outputs disagree

- WHEN Python, Chadwick, and the official parsed CSV disagree for a mapped field
- THEN the validation result identifies the source record and all available
  values so the discrepancy can be investigated

### Requirement: Source gaps and parser gaps remain distinct

The package SHALL distinguish data that is absent in Retrosheet from data that
is present but unsupported by the parser. Missing source detail SHALL remain
missing. Unsupported syntax SHALL raise or surface an explicit unsupported
value according to parser mode.

#### Scenario: Historical field is not present

- WHEN an older Retrosheet record genuinely lacks a detail available in modern
  records
- THEN the parsed model represents that detail as missing and does not synthesize
  a modern default

### Requirement: The standalone package does not own warehouse persistence

The Retrosheet package SHALL NOT connect to PostgreSQL or write mlb-baseball
raw/core/gold relations. It SHALL expose typed records, artifact metadata, and
conversion adapters that a warehouse connector can consume.

#### Scenario: mlb-baseball consumes the package

- WHEN mlb-baseball later adopts the package as a parser backend
- THEN dependency direction remains mlb-baseball to the Retrosheet package and
  never the reverse
