# Change: doc-consolidation-banners

## Why

Restructure step 3 (spec §6.3, §10). Sprawl of ~150 markdown files with no
clear "which one is authoritative". A full physical archive requires a
link-safe pass over ~40 cross-references (some in `docs/DECISIONS.md`, which
must never be rewritten). This change does the safe, high-value half now:
mark every superseded / point-in-time doc so no reader or agent treats it as
current.

## What changes

- Status banner (blockquote, right after the title) on 15 docs:
  - **Superseded by `openspec/project.md`**: `docs/NORTH_STAR.md`,
    `docs/ROADMAP.md`, `docs/PRODUCT_DIRECTION.md`, `docs/MAP.md`,
    `docs/FEATURE_ADMISSION_QUEUE.md`.
  - **Historical snapshot (dated), not maintained**: `docs/CODE_REVIEW_2026-09.md`,
    `docs/POLICY_REVIEW_2026-08.md`, `docs/ECOSYSTEM_ASSESSMENT_2026-08.md`,
    `docs/PROJECT_REVIEW.md`, `docs/PLAN_02_ACCEPTANCE.md`,
    `docs/INGESTION_BULK_LOAD_ASSESSMENT.md`, `docs/PACKAGE_VALIDATION_STATUS.md`.
  - **Retired workflow**: `plans/README.md`, `plans/AGENTS.md`, `plans/PROGRESS.md`.
- `openspec/project.md` NOW list updated.

## Non-goals

- No file moves. No reference rewrites. No touching `docs/DECISIONS.md` or
  `docs/superpowers/specs/`. Those are part 2.
