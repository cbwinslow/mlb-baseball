## Why

The repository has a working point-in-time feature store and a complete metric
catalog pass, but those facts do not prove that a particular training matrix is
current, well-covered, independently checked, or safe to use in a model. We
need one reproducible readiness decision before expanding beyond the shipped
reference baseline, and explicit exit criteria so feature work ends when the
evidence is sufficient rather than becoming perpetual tinkering.

## What Changes

- Add a reproducible model-readiness report that evaluates a named feature
  version against a declared PostgreSQL source database and DuckDB build.
- Define an admissible first ML training surface: `feat.game` and its linked
  `feat.player_form` / `feat.pitcher_form` inputs, not legacy
  `gold.game_feature` compatibility columns or post-game artifacts.
- Make the report prove, rather than merely document: backbone tie-outs,
  feature-store leakage checks, relation uniqueness, coverage/missingness, and
  every selected feature's provenance, grain, time semantics, and test status.
- Publish a concise researcher-facing feature/data contract and a generated
  readiness manifest so external users can reproduce the same build and see
  known coverage limits without reading implementation internals.
- Establish finite completion rules for (a) an individual feature version,
  (b) the model-readiness gate, and (c) a future model candidate's promote / do
  not promote decision. Record excluded or failed features as evidence rather
  than reopening them indefinitely.
- Perform a bounded organization audit of the public feature/metric entry
  points, naming and duplicated/stale documentation. Fix only findings that
  block the documented researcher workflow; do not launch a repository-wide
  cleanup.

## Capabilities

### New Capabilities

- `model-readiness`: reproducible readiness evidence, feature admission
  manifests, and finite go/no-go criteria before a new ML model experiment.

### Modified Capabilities

- `feature-store-boundary`: require model-admission evidence and a stable,
  researcher-facing contract for the DuckDB `feat.*` surface.

## Impact

- Likely affects `mlb build` / `mlb verify` or a closely related read-only CLI
  report, `mlb_baseball/feat.py`, the `mlb_research` public loader/retrieval
  API, feature-store SQL metadata, docs, and focused integration tests.
- Uses the existing metric catalog, doctor checks, and tie-out scripts; it
  adds no new model framework, data source, hosted service, or duplicate
  registry.
- Does not authorize a new predictive model implementation. A later, separate
  change may start the first ML experiment only after this gate reports ready.
