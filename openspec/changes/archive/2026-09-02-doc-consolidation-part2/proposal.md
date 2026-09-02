# Change: doc-consolidation-part2 (physical archive)

## Why

Follow-up to `doc-consolidation-banners`. Physically move the superseded and
historical docs (already bannered) into `docs/archive/`, so the active `docs/`
tree only holds current material. Deferred from part 1 because it needs a
link-safe rewrite of ~40 cross-references and careful handling of files that
must NOT be rewritten.

## What changes

- `git mv` to `docs/archive/`:
  - `plans/` -> `docs/archive/plans/` (7 numbered plans + AGENTS.md + README.md
    + PROGRESS.md)
  - `docs/superpowers/plans/` -> `docs/archive/superpowers-plans/` (~26 files)
  - `docs/{NORTH_STAR,ROADMAP,PRODUCT_DIRECTION,MAP,FEATURE_ADMISSION_QUEUE}.md`
  - `docs/{CODE_REVIEW_2026-09,POLICY_REVIEW_2026-08,ECOSYSTEM_ASSESSMENT_2026-08,
    PROJECT_REVIEW,PLAN_02_ACCEPTANCE,INGESTION_BULK_LOAD_ASSESSMENT,
    PACKAGE_VALIDATION_STATUS,AGENT_CONTEXT_ARCHITECTURE,
    PROGRESSIVE_CONTEXT_ARCHITECTURE}.md`
- Create `docs/archive/README.md` with the old->new path map.
- Rewrite references ONLY in active files (list below); leave historical refs
  in `docs/DECISIONS.md` and `docs/superpowers/specs/*.md` as-is (they are
  correct as of their date; the archive README documents the mapping).

## Active files needing reference rewrites (verified 2026-09-02)

AGENTS.md, CLAUDE.md, CONTRIBUTING.md, README.md, docs/ARCHITECTURE.md,
docs/EXPERIMENT_RUNBOOK.md, docs/RESEARCH.md, docs/SQLMESH_OPERATIONS.md,
docs/THEORY_AND_METHODOLOGY.md, docs/reference/tango_the_book.md,
openspec/project.md, and comment-only refs in:
mlb_baseball/model/__init__.py, mlb_baseball/model/nrfi.py,
mlb_baseball/reap_test_databases.py, scripts/eval_markov_holdout.py,
scripts/lint_sql_ownership.py, tests/conftest.py,
tests/integration/test_model_enrich_stage.py,
tests/integration/test_model_pitcher_estimators.py

## Non-goals

- Not rewriting `docs/DECISIONS.md` or `docs/superpowers/specs/`.
- Not reorganizing the runbooks into subdirectories (separate polish).

## Verification

`python scripts/check_dox.py` exits 0; `git grep -nE 'plans/[0-9]' -- '*.md'
':!docs/archive' ':!docs/DECISIONS.md' ':!docs/superpowers/specs'` returns
nothing; `uv run pytest tests/unit -q` (comment-ref changes don't break code).
