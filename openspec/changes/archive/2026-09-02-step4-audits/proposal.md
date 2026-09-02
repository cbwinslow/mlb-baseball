# Change: step4-audits (dependency + bot audits)

Restructure step 4 (spec §8.2, §8.4, §9.2).

## Dependency + Postgres-extension audit

`report.md` — full audit. **Outcome: adopt nothing now.** Prior reviews
(POLICY_REVIEW_2026-08, ECOSYSTEM_ASSESSMENT_2026-08, ADR-043) hold. One gap:
ingestion `print()` vs `logging` — filed as issue #142. ADR-279 records it.
Everything else gated on a documented trigger.

## PR-review bot audit

`bot-audit.md` — scored the last ~35 PRs' review activity.

**In this change (repo files):**
- `.github/workflows/dependency-review.yml`: `comment-summary-in-pr:
  always -> on-failure` (stops ~29 empty "nothing found" comments).
- `.coderabbit.yaml` (new): CHILL profile, no markdownlint/LanguageTool,
  skip `docs/**` `openspec/**` `**/*.md` — kills the MD001 / grammar nits
  the maintainer keeps declining. CodeRabbit stays advisory.

**Owner actions (GitHub App uninstalls — no repo file):** Qodo, Macroscope
(both 100% billing-failure spam), CodeAnt (marketing comment every PR),
Mergify (unused queue + perpetually-pending checks), Guardrails (redundant
3rd secret scanner). ~160 junk comments/35 PRs removed.

**Owner dashboard tuning:** Kilo — drop SUGGESTION severity (keep
WARNING/CRITICAL).

**Merge gate unchanged:** `test` + `secrets` only; all 8 non-`ci` workflows
already advisory.

## Non-goals

No library adoption. Not touching the `ci` workflow. Codex auto-review stays
off per the owner's earlier instruction (the audit notes it was historically
the highest-signal reviewer; on-demand `@codex review` remains available).
