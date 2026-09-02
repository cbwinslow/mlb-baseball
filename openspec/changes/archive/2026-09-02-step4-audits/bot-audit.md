# PR-review bot audit — cbwinslow/mlb-baseball

**Date:** 2026-09-02
**Sample:** last ~35 merged/closed PRs (#100–#141), of which ~24 had real code-review activity.
**Method:** pulled `issues/*/comments`, `pulls/*/comments`, `pulls/*/reviews` for each PR; read the
threads and the owner's replies (`cbwinslow` left 117 inline replies in the window — a good signal of
what he treated as real vs. declined); cross-checked against `.github/workflows/` and branch protection.

**Merge gate today:** branch protection on `main` requires exactly two checks — `test` and `secrets`
(both GitHub Actions, app_id 15368). Everything else is advisory whether or not it looks like a gate.

**Standing project decisions (context):** Kilo Code is the kept AI reviewer; CodeRabbit is advisory-only.

---

## Scoreboard

| Bot | PRs touched | Clear real findings (conservative) | Noise / false-positive rate | Verdict |
|---|---|---|---|---|
| **Codex** (`chatgpt-codex-connector`) | ~23 | ~20 (many P1 leakage/correctness; several became tracked issues #113/#114/#115) | Low (~15% — a few "out of scope for a pure-move refactor" declines) | **KEEP** (non-blocking) |
| **Kilo Code** (`kilo-code-bot`) | 33 | ~12 (caught the league-prior leak, fragile column-ordering, a few real bugs) | High (~65% — its SUGGESTION tier: type-hint nags, `Decimal(0)` constant, "combine two queries" — repeatedly declined) | **KEEP** (project's chosen reviewer) — but suppress SUGGESTION severity |
| **CodeRabbit** (`coderabbitai`) | 34 | ~12 (league-prior leak, test-schema stub bug, run-aggregation `team_id` bug) | High (~65% — MD001 heading nits, "hyphenate the compound modifier", LanguageTool grammar; owner declined the same MD001 nit on 3+ PRs) | **KEEP-BUT-NONBLOCKING** (already advisory) — switch profile ASSERTIVE → CHILL |
| **CodeAnt** (`codeant-ai`) | 35 | ~3 unique (boolean→int cast Critical on `pitching_game_build.sql`; mostly duplicates Codex/CodeRabbit/Kilo) | Very high — posts a review-status table **and** a "Thanks for using CodeAnt! Share on X / Reddit" marketing comment on every PR (79 issue comments / 35 PRs) | **KILL** |
| **Qodo** (`qodo-code-review`) | 35 | 0 | 100% — every one of its 35 comments is "reviews are paused because the subscription is no longer active. Manage billing" | **KILL NOW** |
| **Macroscope** (`macroscopeapp`) | 35 (check only) | 0 | 100% — `Macroscope - Correctness Check` is `skipped` on every commit: "did not review due to a billing issue" | **KILL NOW** |
| **Mergify** (`mergify`) | 19 | 0 | 100% — "Tick the box to add this pull request to the merge queue" on every PR; also leaves `Mergify Merge Queue` / `Merge Protections` checks perpetually **pending** in the checks list. Maintainer merges manually; no queue in use | **KILL** |
| **Guardrails** (`guardrails`) | 1 comment + `guardrails/scan` check | 0 shown | Low volume, but zero demonstrated value and redundant — it's the 3rd secret/SAST scanner behind gitleaks (`secrets`, required) and GitGuardian | **KILL** (redundant) |
| **GitGuardian** (check only) | all (silent) | 0 in window (comments only on a real secret hit) | Low noise, but redundant — `secrets` (gitleaks) is the required scanner; this is a 2nd/3rd secret scanner | **KEEP-BUT-NONBLOCKING** (or kill as redundant — low urgency) |
| **`dependency-review` workflow** (`github-actions`) | ~29 | 0 (nothing flagged) | Medium — posts "✅ No vulnerabilities … Scanned Files: None" on nearly every PR because `comment-summary-in-pr: always` | **KEEP workflow, fix config** (`always` → `on-failure`) |
| **CommitCheck** (check only) | all | n/a — validates commit-message format | ~zero noise (silent check) | **KEEP-BUT-NONBLOCKING** (leave as is) |
| **qlty** (`qlty check`, check only) | all | 0 ("No blocking issues") | ~zero noise, but overlaps ruff/mypy/sqlfluff in the `lint` job | **KILL** (redundant, low urgency) |
| **pre-commit.ci** (check only) | all | 0 | ~zero noise (`autofix_prs: false`), partial overlap with the `lint` job | **KEEP-BUT-NONBLOCKING** (or kill as redundant) |
| **`ci` workflow** (`test` + shards) | all | n/a — the actual test suite | n/a | **KEEP** (this is the gate) |

---

## Detail per KILL / change

### Qodo — KILL NOW (pure billing spam)
- **What it emits:** 35/35 comments are `<!-- qodo:billing-blocked -->` "subscription is no longer active".
- **How to turn off:** Repo → **Settings → GitHub Apps** (or the org's *Installed GitHub Apps*) → **Qodo Merge / qodo-code-review → Configure → Repository access →** remove `cbwinslow/mlb-baseball` (or **Uninstall**). No repo config file exists (`git ls-files` shows none); nothing to delete in-tree.

### Macroscope — KILL NOW (billing-skipped on every commit)
- **What it emits:** no PR comments; a `Macroscope - Correctness Check` check-run that is `skipped` with a billing-issue message on every commit.
- **How to turn off:** **Settings → GitHub Apps → Macroscope (`macroscopeapp`) → Configure →** remove this repo, or **Uninstall**. The stale check-run disappears once the app is gone. No in-repo config.

### CodeAnt — KILL (marketing spam + near-total duplication)
- **What it emits per PR:** a "🤖 CodeAnt AI — Review Status" table, a separate **"Thanks for using CodeAnt! … Share on X · Reddit"** promo comment, a "CodeAnt Nitpicks" block, and ~1 inline suggestion/PR. Real unique catches in the window: essentially just the `boolean`→`integer` cast Critical on `mlb_baseball/sql/pitching_game_build.sql` (and that PR, #130, was closed unmerged anyway). Everything else it flagged was already flagged by Codex, CodeRabbit, or Kilo.
- **How to turn off:** **Settings → GitHub Apps → CodeAnt AI (`codeant-ai`) → Configure →** remove `cbwinslow/mlb-baseball`, or **Uninstall**. No `.codeant.yaml` / `.codeant/` in the tree to remove.

### Mergify — KILL (unused merge queue, comment on every PR, perpetually-pending checks)
- **What it emits:** a "Tick the box to add this pull request to the merge queue" comment on ~every PR (19 in the window), plus `Summary`, `Mergify Merge Protections`, and `Mergify Merge Queue` checks — the last two sit **pending** forever and clutter `gh pr checks`.
- **How to turn off:** **Settings → GitHub Apps → Mergify → Configure →** remove this repo, or **Uninstall**. Also delete `.mergify.yml` / `.github/mergify.yml` **if one is added later** — none is committed today (`git ls-files | grep mergify` is empty), so the config lives only in Mergify's dashboard.

### Guardrails — KILL (redundant 3rd scanner, no shown value)
- **What it emits:** one "all findings fixed" comment in the whole window + a non-required `guardrails/scan` status check.
- **How to turn off:** **Settings → GitHub Apps → GuardRails → Configure →** remove this repo, or **Uninstall**. No `.guardrails/` config in-tree. Secret scanning stays covered by the required `secrets` job (gitleaks) in `ci.yml`.

### GitGuardian — optional KILL (redundant with gitleaks)
- Currently a silent passing check; only speaks up on a real secret. It's the 2nd secret scanner behind the required `secrets`/gitleaks job (and Guardrails was a 3rd). If you want one secret scanner: **Settings → GitHub Apps → GitGuardian → Uninstall**, keep gitleaks. Low urgency — it isn't generating noise.

### `dependency-review` — KEEP workflow, stop the "nothing found" comment
- File: `.github/workflows/dependency-review.yml`. Change:
  ```yaml
  comment-summary-in-pr: always   →   comment-summary-in-pr: on-failure
  ```
  The workflow still blocks a PR that adds a high-severity-vuln or bad-license dependency; it just stops posting a comment when there's nothing to say (~29 empty comments removed).

### CodeRabbit — KEEP-BUT-NONBLOCKING, dial down the profile
- It's already advisory. Its `CHANGES_REQUESTED` reviews are not a required check, so they don't gate — fine. The noise is the ASSERTIVE review profile generating MD001 heading nits, "hyphenate the compound modifier", and LanguageTool grammar on doc-heavy PRs. In the CodeRabbit dashboard (Organization UI → Review profile) switch **ASSERTIVE → CHILL**, or add a `.coderabbit.yaml` with `reviews.profile: chill` and path filters excluding `docs/**` and `plans/**` prose. No config file exists yet.

### Kilo Code — KEEP (chosen reviewer), suppress SUGGESTION tier
- Highest volume by far (310 inline + 70 review events across 33 PRs; flags "Address before merge" on 49 review passes). Real WARNING/CRITICAL catches are worth it (the `sim_predict` league-cache-key leak, fragile `rec[:-1]` column ordering). The SUGGESTION tier is where the declined noise lives (season-range guards, `Decimal(0)` module constant, "merge two `to_regclass` queries"). In the Kilo dashboard, set the minimum reported severity to WARNING (drop SUGGESTION), or lower the per-PR comment cap.

### Codex — KEEP (best signal in the sample), currently dormant
- Deepest, most repo-aware findings: caught point-in-time leakage in the league prior (#100), hindsight starters in the holdout (#101), the paired-uncertainty gap before declaring a Markov winner (#101/#102), the Parquet-schema-drift bug and transaction-commit bug in the exporter (#123). Owner acted on almost all of them ("Fixed — real leak, good catch").
- **Note:** Codex stopped commenting after ~#133 (no reviews on #134–#141) — it may already be disabled or out of quota. If it's off, that's a loss of the highest-value reviewer; worth re-enabling. It runs via the ChatGPT/Codex GitHub connector, not a workflow file.

---

## Workflow files in `.github/workflows/` — advisory vs. gating

| File | Trigger | Blocking? | Notes |
|---|---|---|---|
| `ci.yml` | push/PR to main | **YES** — `test` and `secrets` are the required checks | `test` aggregates `unit` + all 3 `integration` shards; `secrets` = gitleaks. Everything real. |
| `codeql.yml` | push/PR + weekly | No | SARIF → Security ▸ Code scanning. Advisory by design (header says so). |
| `scorecard.yml` | push to main + weekly | No | SARIF → Security tab; `publish_results: false`. Never touches a PR. Advisory. |
| `dependency-review.yml` | PR | No (check not in required contexts) | `fail-on-severity: high` fails its own non-required check; **comments on every PR** — see fix above. |
| `workflow-lint.yml` | PR/push touching `.github/workflows/**` | No | actionlint `fail_level: none` + reviewdog PR comments; zizmor → SARIF. Explicitly "informational (non-blocking) for now". |
| `link-check.yml` | weekly cron + manual | No | Not on PRs at all; `fail: true` only fails the scheduled run. |
| `sbom.yml` | release published | No | No PR impact; only runs when a release is cut (none yet). |
| `labeler.yml` | PR opened/sync | No | Auto-labels by path; no comment, no gate. Harmless — keep. |

All eight non-`ci` workflows are advisory. No change needed beyond the one-line `dependency-review.yml` edit.

---

## Recommended action order

1. **Now:** uninstall **Qodo** and **Macroscope** (100% billing-failure spam, zero value).
2. **Now:** uninstall **CodeAnt** (marketing spam on every PR) and **Mergify** (unused queue, pending checks).
3. **Now:** uninstall **Guardrails** (redundant 3rd scanner).
4. **1-line PR:** `dependency-review.yml` → `comment-summary-in-pr: on-failure`.
5. **Dashboard tuning:** CodeRabbit ASSERTIVE→CHILL (+ exclude `docs/**`, `plans/**`); Kilo drop SUGGESTION severity.
6. **Check:** confirm **Codex** is still enabled — it's the strongest reviewer and has been silent since #133.
7. **Optional later:** drop **GitGuardian**, **qlty**, **pre-commit.ci** as redundant with `secrets`/gitleaks and the `lint` job.

After 1–3, PR comment volume drops by roughly two-thirds (Qodo 35 + CodeAnt ~79 + Mergify 19 + dependency-review ~29 = ~160 junk comments removed across the 35-PR window), leaving Codex + Kilo + CodeRabbit as the review voices and `test` + `secrets` as the only gates.
