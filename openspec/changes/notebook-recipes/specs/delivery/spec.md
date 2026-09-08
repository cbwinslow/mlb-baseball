## MODIFIED Requirements

### Requirement: A runnable example notebook

The project SHALL include **at least five** notebooks, each answering a distinct
concrete analyst question using **only the released delivery surface** (the
`mlb-research` package or the published Parquet), never a live database
connection. Each notebook SHALL run end to end from a clean environment with the
package installed, and SHALL recompute any rate from summed numerators and
denominators rather than averaging already-computed rates.

#### Scenario: Every example notebook runs against released data only

- **WHEN** any notebook under `notebooks/` is executed in a clean environment
  with `mlb-research` installed
- **THEN** it completes without error
- **AND** it makes no connection to a Postgres database and imports no
  database-layer package

#### Scenario: The notebook set covers at least five distinct questions

- **WHEN** the `notebooks/` directory is listed
- **THEN** there are at least five runnable notebooks
- **AND** each answers a different analyst question, not five variations of one
