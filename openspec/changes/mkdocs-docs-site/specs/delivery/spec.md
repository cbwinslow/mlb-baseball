## ADDED Requirements

### Requirement: Published documentation site

The project SHALL publish a static documentation website that an outside
analyst can read **without cloning the repository or running anything**,
covering at minimum:

- a **data dictionary** of every table in the published backbone set — its
  grain, its columns and their types, its source, and its null policy;
- a **grain-ladder** explanation with a diagram, stating that season, team, and
  career figures are recomputed from the finer grain's numerators and
  denominators and never averaged from already-computed rates;
- **formula citations** — for every metric the project publishes, its formula
  and the published source it is cited to;
- an **honest-limitations** page — coverage boundaries, regular-season-only
  scope, known tie-out tolerances, and the "a missing measurement is not zero"
  rule.

The site SHALL be deployed at no hosting cost through the same static
GitHub Pages workflow that publishes the in-browser query page — not a second
workflow or a paid service. The in-browser query page SHALL remain reachable at
its existing path after the documentation site is published.

The data-dictionary content SHALL have a single source of truth in the
repository: the published page SHALL be generated from that source, not
maintained as a second hand-edited copy that can drift.

#### Scenario: A visitor reads the documented backbone without cloning the repo

- **WHEN** a visitor opens the published documentation site
- **THEN** they can read the data dictionary, the grain-ladder diagram, the
  cited formulas, and the honest-limitations page as rendered web pages
- **AND** no step requires cloning the repository, installing a package, or
  running a build

#### Scenario: The query page still works after the docs site ships

- **WHEN** the documentation site is deployed
- **THEN** the in-browser SQL query page is still reachable at its previous path
- **AND** it still runs queries entirely client-side against the published
  dataset

#### Scenario: The data dictionary cannot silently drift

- **WHEN** a column is added, renamed, or removed from a published backbone table
  and the repository's canonical data-dictionary source is updated
- **THEN** rebuilding the site reflects that change on the published
  data-dictionary page with no separate edit to the site
