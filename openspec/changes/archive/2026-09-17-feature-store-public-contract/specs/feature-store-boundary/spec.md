## Purpose

Keeps the root `mlb_baseball` package's public API and documentation from
presenting two feature-building paths as though either could be "the"
point-in-time feature store, so a reader or caller cannot reasonably confuse
the legacy Engine path with the canonical DuckDB research feature store.

## ADDED Requirements

### Requirement: The public API distinguishes the legacy feature path from the canonical feature store

Any root-package function, docstring, or public documentation page that
builds or describes `gold.game_feature` (the legacy Engine feature surface)
SHALL be labeled explicitly as legacy/internal — never described in terms
that could be read as "the point-in-time feature store" or "the research
feature store." The canonical point-in-time research feature store SHALL be
described in exactly one place-independent way across all docs: built via
`mlb build` into DuckDB `feat.*`, retrieved via
`mlb_research.get_historical_features`, documented in
`docs/FEATURE_STORE.md`.

#### Scenario: A reader consults the public API docs for feature building

- **WHEN** an analyst or contributor reads `docs/PUBLIC_API.md`'s entry for
  the root package's legacy feature-rebuild function
- **THEN** the entry states plainly that it rebuilds the legacy
  `gold.game_feature` relation, not the point-in-time research feature store
- **AND** it points to `docs/FEATURE_STORE.md` / `mlb build` for the actual
  point-in-time research feature store

#### Scenario: Architecture documentation describes the feature/model surface

- **WHEN** `docs/ARCHITECTURE.md` describes what owns the project's
  feature/model surface
- **THEN** it reflects the DuckDB `feat.*` boundary (the feature/model layer
  is DuckDB-only past `core`) rather than describing `gold` as owning that
  surface

#### Scenario: A new programmatic feature-build entry point is added later

- **WHEN** a future change exposes a programmatic (non-CLI) way to trigger
  the canonical DuckDB `feat.*` build
- **THEN** it is exposed under a name that is not `build_features()` (which
  remains the legacy Engine path) and its docstring states which feature
  store it builds

### Requirement: Existing legacy feature-rebuild behavior is preserved

Labeling and documentation changes made to satisfy this capability SHALL NOT
change the runtime behavior of the existing legacy `build_features()` /
`model.run_features()` path. Any caller relying on it to rebuild
`gold.game_feature` today SHALL see identical behavior after this change.

#### Scenario: An existing caller of the legacy feature rebuild

- **WHEN** existing code calls the root package's legacy feature-rebuild
  function exactly as it did before this change
- **THEN** it rebuilds `gold.game_feature` exactly as before, with no
  behavioral difference
