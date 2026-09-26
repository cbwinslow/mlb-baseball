## Context

See `proposal.md` and the `model-readiness` delta spec. The repository already
has the ingredients of a trustworthy feature workflow: PostgreSQL `raw`/
`core`/`gold`, a DuckDB-only `feat.*` store, `mlb verify` leakage checks,
backbone tie-out scripts, a metric catalog, and `mlb_research` retrieval.
They are not currently assembled into one versioned, user-facing admission
decision. `docs/FEATURE_REGISTRY.md` documents many legacy
`gold.game_feature` families, while `docs/FEATURE_STORE.md` identifies
DuckDB `feat.*` as the canonical modeling surface.

## Goals / Non-Goals

**Goals:**

- Produce a deterministic readiness result for a declared feature set and a
  designated, non-ambiguous data/build target.
- Give external users a compact, inspectable contract for the first game-win
  feature set without making them reverse-engineer Python or SQL.
- Turn existing tie-out/leakage/health evidence into explicit model admission
  gates, with failures reported as blockers.
- Freeze a feature version after it passes its declared gate and require a
  separate approved version for later additions.
- Bound organization work to the researcher path: CLI help, public docs,
  feature declarations, metric catalog links, and obsolete/duplicate entry
  points that could make that path ambiguous.

**Non-Goals:**

- Retrospectively externally validate every cataloged metric or rewrite every
  legacy Engine module before modeling begins.
- Change a source of record, add a hosted service, add a model framework, or
  implement the next predictive model.
- Treat the readiness result as a claim that a model will outperform a
  baseline; it only establishes a defensible dataset for testing that claim.
- Conduct a repository-wide style refactor unrelated to a documented
  researcher workflow failure.

## Decisions

### 1. Make one feature-set declaration the training contract

Add a small versioned declaration for `game-win-v1` alongside the public
`mlb_research` package. It names selected `feat.game` fields and any linked
form features, with source relation, entity key, availability rule, null
policy, coverage interval, citation/provenance pointer, and test/evidence
reference. It is an allow-list, not a second metric registry: the metric
catalog remains formula/provenance truth, while this declaration answers which
already-built columns may enter one named experiment.

Alternatives considered:

- Infer columns from every catalog entry. Rejected because catalog entries
  describe metrics at different grains and layers, not a model-specific,
  leak-safe training matrix.
- Continue using `gold.game_feature`. Rejected because it is explicitly a
  legacy compatibility surface and its broad historical inventory obscures the
  first experiment's input contract.

### 2. Report readiness; do not silently rebuild or query production

Add a read-only `mlb readiness` command (exact spelling confirmed during
implementation) that accepts an explicit DuckDB path/version and uses existing
configuration for the already-built PostgreSQL source. It emits stable JSON for
automation and a concise Markdown/text summary for researchers. It MUST NOT
ingest, conform, report, migrate, or rebuild data. The operational runbook
will state the deliberate prerequisite sequence: build gold, run its tie-outs,
build `feat.*`, then run readiness.

The report records a redacted source identifier, feature build timestamps,
feature-set declaration version, check results, and a per-season/per-feature
coverage and null-rate profile. It does not persist a new database table;
JSON/Markdown are portable research artifacts.

Alternatives considered:

- Make `mlb verify` absorb all readiness output. Rejected because `verify`
  proves store mechanics and backbone tie-out, whereas readiness also needs a
  declared feature allow-list, coverage profile, and a stable reusable
  artifact.
- Add a `meta.readiness_run` subsystem. Rejected as unnecessary operational
  infrastructure before a demonstrated need for run history.

### 3. Use explicit blockers, not universal invented thresholds

The report is `ready` only when the declared build passes backbone tie-outs,
store leakage/integrity checks, and every selected field has complete admission
metadata and no missingness outside its declared null policy. It reports
observed coverage/null rates rather than enforcing a project-wide arbitrary
percentage: early-season form, starter identity, and Statcast eras have
legitimate, different coverage shapes. The declaration must state the intended
training coverage window; a field outside that window is excluded, not filled
with zero.

This separates *measurement* (automated) from *research judgment* (whether an
observed coverage profile is useful for a particular experiment). The report
cannot be green while concealing either.

### 4. Completion is a hierarchy of irreversible decisions

Record the following finish lines in the public readiness documentation and
the change's tasks:

1. **Feature version complete:** its declaration is complete, readiness is
   green for the named data window, and its limitations are published. Later
   additions require a new version.
2. **Model experiment complete:** its chronological folds, baseline, metrics
   (log loss, Brier, calibration), and promotion threshold are declared before
   fitting. Its output is promote / retain baseline / negative result.
3. **Phase-A completion:** the existing `openspec/project.md` v1/v1.1 gates,
   including the backbone tie-outs and public delivery surfaces, remain the
   project-level exit condition. This change does not weaken or replace them.

This allows useful modeling to proceed after the feature-set gate while
preventing a feature from being continuously reopened because a later model
underperforms.

### 5. Organization audit has a bounded inventory and repair rule

Inventory only the public entry points a new analyst uses: README/PUBLIC_API,
`mlb --help`, `docs/FEATURE_STORE.md`, `docs/FEATURE_REGISTRY.md`, metric
catalog docs, `mlb_research` public APIs, SQL resource locations, and tests.
Classify each finding as blocking ambiguity, stale/duplicate documentation, or
non-blocking cleanup. Fix the first two in this change; record the last as
deferred rather than expanding scope.

## Risks / Trade-offs

- [Tie-out scripts need a fully built real database] → readiness runs only
  against an explicit designated target and names missing prerequisites rather
  than substituting fixture-only evidence.
- [Coverage differs materially by era] → declaration names its valid coverage
  window; readiness profiles rather than hides nulls or imputes values.
- [A report can become another stale document] → generate it from the current
  declaration and current build, version its schema, and test its JSON shape.
- [Legacy docs contain useful history] → label and link them; do not delete or
  rewrite historical evidence in a broad cleanup.

## Migration Plan

1. Add the declaration, readiness command/report, and focused tests without
   changing `mlb build`, legacy rebuild behavior, or model code.
2. Exercise the report against a disposable integration database and a
   designated fully-built verification target; publish the resulting example
   and known limits.
3. Update researcher docs and CLI/API references, then run the bounded
   organization audit and record all non-blocking findings.
4. Run project quality gates and OpenSpec validation. A separate proposal may
   begin an ML candidate only after the report reaches `ready` for the declared
   feature version.

## Open Questions

- The exact first `game-win-v1` column allow-list will be chosen from the
  existing `feat.game` schema during implementation, after its real coverage
  profile is measured. This does not alter the contract: every chosen column
  must carry the evidence specified above.
