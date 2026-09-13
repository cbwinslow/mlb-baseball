## Purpose

Gives every statistic/metric this project implements exactly one cited,
status-honest, machine-readable record, so a researcher (or the owner) can
discover, trust, and query what exists without reading source code or a
decision log — and so the public/private line is drawn by the project's own
"published formula ships" rule rather than by which directory a file happens
to live in.

## ADDED Requirements

### Requirement: Every implemented metric has exactly one catalog entry

Every statistic/metric implemented under `mlb_baseball/model/`, and every
named statistic materialized in a `gold`/`feat` relation, SHALL have exactly
one catalog entry carrying: a stable `name`; a plain-English `definition`
(no unexplained jargon); a `formula` (a direct pointer to the code/SQL that
computes it); a `citation` (the formula's published source + year, or
"project-derived" if none exists); a `data_source` (which raw/core inputs the
numbers themselves come from — distinct from `citation`, which names the
idea, not the data); a `grain`; a `layer` (`gold`, `feat`, or `model`); a
`complexity` (`arithmetic` or `complex`); an `implementation`
(`sql`/`sqlmesh`/`python`); a `status`; and a `visibility`. An entry with a
missing mandatory field is invalid.

#### Scenario: A metric's data source is recorded separately from its formula's origin

- **WHEN** a catalog entry is created
- **THEN** it names both `citation` (whose idea the formula is) and
  `data_source` (which ingested tables the numbers are computed from), and
  the two are not conflated into one field

### Requirement: Every shipped value has a reproducible pointer to what produced it

Every catalog entry SHALL carry a generated, version-pinned pointer (a
`source_permalink`) to the exact file and git revision that computed the
value, derived from `formula` and the release the catalog was built against —
never a link to a moving branch. This is in addition to, not instead of,
`citation`: `citation` says whose formula it is, `source_permalink` proves
what code actually ran.

#### Scenario: A published value can be traced to the exact code that made it

- **WHEN** a researcher looks up a metric on the public catalog page for a
  specific published data release
- **THEN** they find a link to the exact `.sql` or `.py` file, at the git
  revision that release was built from, that computed that value

#### Scenario: The pointer never silently goes stale

- **WHEN** the underlying implementation file is later changed or moved on
  the main branch
- **THEN** a `source_permalink` generated for an already-published release
  still resolves to the original code, not the changed version

#### Scenario: A metric module with no catalog entry fails CI

- **WHEN** a file under `mlb_baseball/model/` (or a new named `gold`/`feat`
  statistic) has no corresponding catalog entry
- **THEN** the catalog-completeness check fails and blocks merge

#### Scenario: An entry missing a mandatory field is rejected

- **WHEN** a catalog entry is missing `citation`, `status`, or `visibility`
- **THEN** catalog validation fails with the specific missing field named

### Requirement: Status reflects actual validation, not aspiration

A catalog entry's `status` SHALL be one of `published` (a cited formula,
correctly implemented, not yet independently tie-out tested),
`validated` (has a passing automated test that reproduces an independent
published value within a documented tolerance), `implemented-untested`
(runs, produces output, no independent check exists), `negative-result`
(implemented and evaluated; did not outperform a documented baseline; kept
for the record), or `archived` (superseded or removed). `validated` SHALL
NOT be set without a linked, currently-passing test.

#### Scenario: A metric with no tie-out test cannot claim validated

- **WHEN** a catalog entry declares `status: validated`
- **THEN** it names a specific automated test, and that test currently
  passes and asserts a numeric comparison against an independent published
  value within a stated tolerance

#### Scenario: An honest negative result is preserved, not deleted

- **WHEN** a model or metric was implemented and evaluated but did not beat
  its baseline
- **THEN** its catalog entry is retained with `status: negative-result`
  rather than removed, per the project's evidence-retention rule

### Requirement: Visibility follows the publication rule, not the directory

A catalog entry's `visibility` SHALL be `public` if the metric's formula is
drawn from published, citable literature (a book, paper, or a source the
project already cites elsewhere), regardless of which source directory
currently implements it. `visibility` SHALL be `internal` only for tuned
parameters/weights not themselves published, blended/ensembled outputs,
ranked feature-selection results, market-disagreement research, or
non-baseline backtest results.

#### Scenario: A published formula is public even if implemented under model/

- **WHEN** a metric implements a formula with a citable public source (e.g.
  a linear-weights run value from a published book or site)
- **THEN** its catalog entry has `visibility: public`, independent of which
  package or directory contains the implementing code

#### Scenario: A tuned or ensembled result stays internal

- **WHEN** a catalog entry represents a tuned model's fitted parameters, an
  ensemble blend, or backtest results for a non-baseline model
- **THEN** its catalog entry has `visibility: internal`

### Requirement: The catalog makes SQL/Python misplacement visible, not re-argued

A catalog entry's `complexity` SHALL be `arithmetic` if its formula is a
deterministic aggregation over already-normalized data that a researcher
could recompute by hand from the same inputs, and `complex` otherwise
(iterative fit, simulation, or a stochastic method). `implementation`
records what actually computes the metric today. Any entry with
`complexity: arithmetic` and `implementation: python` SHALL be queryable as
a migration candidate — this requirement does not mandate the migration
happen in this change, only that the candidate set is derivable from the
catalog rather than re-discovered by memory each time someone asks.

#### Scenario: A misplaced arithmetic metric is findable

- **WHEN** the catalog is queried for entries where `complexity = 'arithmetic'`
  and `implementation = 'python'`
- **THEN** every such entry is returned, and no `complex` entry is included
  in that result regardless of its `implementation`

### Requirement: The catalog is queryable in two forms from one source

The catalog's underlying records SHALL be the single source of truth for
two generated views: a public documentation page listing every
`visibility: public` entry with its plain-English definition and citation
(sorted so `validated` entries are distinguishable from `implemented-untested`
ones), and a PostgreSQL `meta.metric` table loaded from the same records so
a SQL user can join catalog metadata against computed output. The two views
SHALL NOT be maintained as separate hand-edited copies.

#### Scenario: The public docs page never shows an internal entry

- **WHEN** the public catalog page is generated
- **THEN** it contains no entry whose `visibility` is `internal`

#### Scenario: meta.metric and the docs page agree

- **WHEN** the catalog records change and both views are regenerated
- **THEN** `meta.metric`'s public rows and the docs page's entries describe
  the same set of metrics with the same citation and status text

### Requirement: This change does not alter computed values

Building the catalog SHALL NOT change any metric's implementation, formula,
tuned parameter, or computed output. It is a read-only inventory over
existing code.

#### Scenario: No production value changes as a result of cataloging

- **WHEN** the catalog is built and published
- **THEN** every `gold`/`feat`/`model`-derived value already in production
  is bit-for-bit unchanged
