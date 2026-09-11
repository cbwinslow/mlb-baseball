## 1. Constitution + decision record

- [ ] 1.1 `openspec/project.md` — add the one-sentence clarification to the
  Phase A/B boundary: a metric implementing a published, citable formula is
  Phase A / public regardless of its current directory; only tuned
  parameters, ensembles, ranked feature-selection results, and non-baseline
  backtest results are Phase B / internal. Mark Phase B ladder step 1
  ("Engine triage + a `meta.metric` registry table") as satisfied by this
  change, noting the remaining full-module triage is tracked as an ongoing
  NEXT-queue item, not a Phase B start. Verify: the sentence reads correctly
  in context; `openspec/project.md` still describes one coherent policy, not
  two competing ones.
- [ ] 1.2 `docs/DECISIONS.md` — one ADR recording (a) the gate clarification
  and its rationale, (b) the decision to build a metric catalog now as
  documentation-only, pulled forward from Phase B step 1, (c) the YAML +
  `meta.metric` + docs-page shape from `design.md`. Verify: ADR number is
  the next unused one; cross-referenced from the proposal.

## 2. Catalog schema and loader

- [ ] 2.1 Define the YAML schema for a metric entry (fields: `name`,
  `definition`, `formula`, `citation`, `grain`, `layer`, `status`,
  `visibility`, `test_ref`, `notes`) as a `jsonschema` (or `pydantic`) model
  in `mlb_baseball/catalog.py`, choosing whichever library adds the smaller
  new footprint given current `pyproject.toml` deps. Verify: a unit test
  feeds one valid and several invalid fixtures (missing field, bad `status`
  enum value, bad `visibility` enum value) and asserts accept/reject.
- [ ] 2.2 Create `mlb_baseball/metrics/` directory with a `README.md`
  documenting the schema (mirrors the doc comment already in `design.md`)
  and a `.gitkeep` or first real entry. Verify: directory exists, README
  matches the schema in `catalog.py` field-for-field.
- [ ] 2.3 `migrations/<next>_meta_metric.sql` — `CREATE TABLE meta.metric`
  (id/name `text PRIMARY KEY`, typed columns per schema, `status`/
  `visibility` as `text` with `CHECK` constraints enumerating allowed
  values, `loaded_at timestamptz NOT NULL DEFAULT now()`). Additive.
  Verify: `mlb migrate` on a scratch DB applies cleanly; `\d meta.metric`
  shows the constraints.
- [ ] 2.4 `mlb_baseball/sql/meta_metric_upsert.sql` — named INSERT resource
  (no SQL strings in Python, per existing rule) used by the loader.
  `mlb_baseball/catalog.py::load()` reads every `mlb_baseball/metrics/*.yaml`,
  validates each against the schema (task 2.1), and does the existing
  project idempotent full-rebuild pattern: `TRUNCATE meta.metric` + insert
  every validated entry in one transaction. Verify: an integration test
  seeds two YAML fixtures, runs `load()` twice, asserts `meta.metric` has
  exactly those two rows both times (idempotent) and that an invalid third
  fixture raises with the specific missing/bad field named, not a bare
  stack trace.
- [ ] 2.5 Wire `catalog.load()` into a CLI verb (`mlb catalog build` — a new
  verb, decided over folding into `mlb report`, since this has no `raw`
  source and a different cadence). Verify: `mlb catalog build` on a scratch
  DB populates `meta.metric` from the repo's real
  `mlb_baseball/metrics/*.yaml`; `mlb doctor` gets a cheap check that
  `meta.metric` row count equals the number of `.yaml` files on disk.

## 3. CI catalog-completeness check

- [ ] 3.1 `scripts/check_metric_catalog.py` — walks `mlb_baseball/model/*.py`
  (excluding `__init__.py` and non-metric infra files, enumerated
  explicitly, not guessed by a naming heuristic) and every named statistic
  materialized in `gold`/`feat` per `docs/DATA_DICTIONARY.md`; for each,
  checks a `mlb_baseball/metrics/*.yaml` entry exists whose `formula` field
  points at it. Reports every gap by file. Verify: run against the repo
  today (before task 4's entries land) and confirm it reports the expected
  large gap count; after task 4, confirm it reports zero gaps for the
  entries that batch covers and the expected remaining gap count for the
  rest.
- [ ] 3.2 The Decision-2 lint (design.md): flag an entry whose `citation`
  matches a known-public-source allow-list but `visibility: internal`, or
  the reverse. Verify: a unit test fixture pair (one correctly public, one
  deliberately mismatched) produces the expected flag/no-flag.
- [ ] 3.3 The Decision-3 check: for every `status: validated` entry, confirm
  `test_ref` names a real, currently-passing test; best-effort flag (not
  hard-fail) a `validated` entry whose named test only compares against a
  value computed in the same test body (self-referential), rather than an
  externally-sourced fixture constant. Verify: one fixture pair (a real
  external-fixture tie-out test vs. a self-derived-value test) produces the
  expected flag.
- [ ] 3.4 Wire `check_metric_catalog.py` into CI as an advisory (non-blocking)
  check for this PR (per `design.md`'s Migration Plan step 3 — promote to
  required once the first full triage pass lands, tracked separately, not in
  this change). Verify: CI run on this PR shows the check executing and
  reporting, without blocking merge.

## 4. First batch — flagship metrics, real evidence only

- [ ] 4.1 Write catalog entries for the metrics this session already has
  concrete evidence for for citation/status: `gold.fangraphs_guts` (FanGraphs
  Guts! constants, ADR-290 — `public`, `published`, since it is FanGraphs'
  own published constant, verbatim-conformed, not yet independently tie-out
  tested against a second source), `gold.fangraphs_park_factors` (same
  posture), WAR (`model/war.py`), wOBA/wRC+, comprehensive baserunning
  (`model/bsr.py`), catcher framing (`model/framing.py`), Elo (`model/elo.py`),
  win probability/leverage (`model/win_expectancy.py`, `model/leverage.py`,
  `model/wpa.py`), park factors (`model/park.py`). For each: read the module
  and its test file, determine `status` honestly per the Decision-3 rule
  (do not default to `validated` — most will land `implemented-untested` or
  `published` unless a real external tie-out exists), determine `visibility`
  per the publication rule, cite the real source. Target 15-20 entries.
  Verify: `check_metric_catalog.py` reports zero gaps for exactly this list;
  every `validated` entry's `test_ref` passes the Decision-3 check.
- [ ] 4.2 Spot-check at least 3 of the batch's entries by hand against the
  actual code and test file (not the entry's own description) before this
  task is marked complete — catches a copy-paste citation or a status
  claimed without reading the test. Verify: the 3 spot-checked entries are
  named in the PR description with what was confirmed.

## 5. Public catalog page

- [ ] 5.1 A generator script (or `mlb catalog docs` verb) that queries
  `meta.metric WHERE visibility = 'public'`, sorts `validated` before
  `implemented-untested` before `published`, and writes a Markdown page
  with each entry's plain-English definition and citation. Verify: run
  against the batch from task 4; every `gold.fangraphs_*` entry (already
  known `public`) appears; no `internal` entry appears (spec scenario).
- [ ] 5.2 Land the generated page under the existing docs site
  (`docs/site/` or wherever `mkdocs-docs-site`'s nav lives — check that
  change's output first) with a nav entry. Full navigation/visual design is
  explicitly out of scope (design.md Non-Goals) — a working, linked page is
  sufficient. Verify: `mkdocs build` (or the project's existing docs CI
  check) succeeds with the new page linked from the nav.

## 6. Cross-links and queue update

- [ ] 6.1 `docs/DATA_DICTIONARY.md` — add a pointer to the new public
  catalog page instead of duplicating any citation already captured there.
  Verify: no citation text exists in two places with different wording.
- [ ] 6.2 `openspec/project.md` NOW/NEXT — add a tracked, explicitly-batched
  item for triaging the remaining `model/` modules (the ~135-140 not covered
  by task 4), sized as multiple future changes, not one. Verify: the queue
  entry states a batch size and says "batched, not big-bang" per the
  project's own existing incremental-porting convention.

## 7. Full verification

- [ ] 7.1 `ruff`/`mypy`/`sqlfluff` clean on all new/changed files.
- [ ] 7.2 Full test suite touching new code passes (unit tests for
  `catalog.py`'s schema validation, integration tests for the loader and
  `meta.metric`, the CI check script's own fixture tests).
- [ ] 7.3 `openspec validate metric-catalog --strict` passes.
- [ ] 7.4 Owner review: read the generated public catalog page and confirm
  the plain-English definitions are actually plain English, and that the
  `public`/`internal` split on the batch matches their own judgment for at
  least the entries they know well.
