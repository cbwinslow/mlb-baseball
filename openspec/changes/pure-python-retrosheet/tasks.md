Scope: Slice A only. This change establishes the standalone Python package,
official source client, lossless record/play parser, and differential-test
framework. It does not replace the production Chadwick-backed connectors.

TDD applies to behavior: write a failing test, verify the failure is meaningful,
then implement the smallest passing behavior.

## 1. Package and source contract

- [ ] 1.1 Check PyPI and repository-name collisions and record the final
  distribution name and import namespace. Do not reuse pyretrosheet.
- [ ] 1.2 Scaffold the package under packages/ and add it to the existing uv
  workspace. The package must install/import with no compiler, CMake, autotools,
  Chadwick executable, PostgreSQL client, pandas, or mlb_baseball.
- [ ] 1.3 Add README/source-rights text naming Retrosheet as the source and
  reproducing the required attribution guidance without implying endorsement.
- [ ] 1.4 Add a small public API document. Keep the first stable surface limited
  to source acquisition, record iteration, play parsing, and structured errors.

## 2. Official resource client

- [ ] 2.1 Add a typed Resource/Artifact model with source URL, product, season
  or group, local path, SHA-256, size, and retrieved timestamp.
- [ ] 2.2 Implement deterministic official URL resolution for the source
  products already used by mlb-baseball: yearly parsed CSV bundles, event
  decade archives, postseason, All-Star, Negro League event archives, roster
  resources, and box-score archive families.
- [ ] 2.3 Implement safe cached download and zip-member iteration. Reject path
  traversal and corrupt/non-zip responses; do not silently overwrite a cached
  artifact whose bytes differ without returning new metadata.
- [ ] 2.4 Tests use captured tiny archives or mocked byte responses. Routine CI
  must not depend on live Retrosheet availability.

## 3. Lossless raw record framing

- [ ] 3.1 Define typed record models for id, info, start, sub, play, data,
  comment, and adjustment/metadata records encountered in the current
  Retrosheet corpus.
- [ ] 3.2 Implement a streaming record reader that yields records with source
  file, line number, game id when known, and exact raw text.
- [ ] 3.3 Unknown record types fail in strict mode and become explicit
  UnsupportedRecord values in diagnostic mode. They are never skipped.
- [ ] 3.4 Add fixture tests spanning regular, postseason, deduced, All-Star, and
  Negro League event files where those formats differ materially.

## 4. Play syntax model

- [ ] 4.1 Define enums/dataclasses for primary event, modifiers, runner
  advances, fielding credits/errors, run-credit annotations, and raw/unknown
  components.
- [ ] 4.2 Parse the Retrosheet play field into those components without mutating
  game state.
- [ ] 4.3 Preserve raw tokens on every parsed component and provide a structured
  ParseError with parser stage and location.
- [ ] 4.4 Port no implementation code from Chadwick. Tests are derived from
  Retrosheet documentation, captured source records, and observable reference
  outputs.
- [ ] 4.5 Run parse-coverage measurement over at least one modern season, one
  dead-ball/early covered season, one deduced-data season, postseason, and Negro
  League play-by-play. Record every unsupported syntax family.

## 5. Differential validation harness

- [ ] 5.1 Add a dev/test-only ChadwickReference adapter that discovers
  cwevent/cwgame on PATH and records the exact Chadwick version. Absence skips
  reference tests cleanly; it is not a runtime package requirement.
- [ ] 5.2 Capture Chadwick 0.10.0 reference output for a small legal fixture set
  so normal CI can run deterministically without native tools.
- [ ] 5.3 Add the official Retrosheet parsed-play crosswalk as test metadata and
  compare fields that are already derivable without a state engine.
- [ ] 5.4 Emit a machine-readable coverage report: records parsed, play strings
  parsed, unsupported families, and reference mismatches.

## 6. mlb-baseball boundary proof

- [ ] 6.1 Add no production dependency or connector switch in this slice.
- [ ] 6.2 Write an integration-contract test or documented spike showing how
  mlb_baseball can consume Artifact metadata and a stream of parsed records
  without the new package importing mlb_baseball.
- [ ] 6.3 Confirm the current official-CSV connector and current
  Chadwick-backed event/box connectors remain behaviorally unchanged.

## 7. Verification

- [ ] 7.1 Run the package unit/fixture suite, ruff, format check, and type check.
- [ ] 7.2 Run root tests that guard uv workspace/package discovery.
- [ ] 7.3 Run OpenSpec strict validation for this change and all specs.
- [ ] 7.4 Review the final diff for native build dependencies, copied Chadwick
  implementation text, silent unsupported-event handling, or accidental
  PostgreSQL/mlb_baseball coupling.
- [ ] 7.5 Record a Slice B go/no-go note based on parse coverage and the measured
  complexity of the remaining state-engine parity work.
