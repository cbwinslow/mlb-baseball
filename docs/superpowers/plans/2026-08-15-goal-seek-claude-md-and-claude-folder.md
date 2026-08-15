# Goal seek: CLAUDE.md update and `.claude` folder commit

Goal: Two small, independent housekeeping tasks, parked from earlier in this
project's work: fold durable learnings from the 2026-08-14/15 ML-harness
session into `CLAUDE.md`, and commit the shareable part of the `.claude`
folder (currently entirely `.gitignore`'d). Neither touches application
code. Do them as two separate commits, not one — they're unrelated changes.

Safety and scope:
- No database access of any kind, `mlb` or `mlb_test` — this package is
  pure file/git work.
- Do not touch any file besides the ones named explicitly below.
- Do not run the test suite as a gate for this package (there's no code to
  test), but do run Ruff/mypy anyway if any Python file happens to change
  (it shouldn't) — this is a doc/config-only package.

Work package 1 — CLAUDE.md update:

The exact text to add is specified below — apply it close to verbatim,
adjusting only for clean integration with surrounding Markdown (spacing,
list formatting). This isn't a "figure out what to write" task — the
content decision is already made; your job is placement and clean
integration into the existing file, matching its current terse,
rule-plus-one-concrete-example voice (see how the existing "Testing"
section's `track_run`/`test_failure_path_logs_error_and_leaves_connection_usable`
bullet cites one specific test as its reference example — the new bullets
below follow that exact same pattern on purpose).

1. In the `## Testing` section, add a new bullet (order: after the existing
   `track_run` bullet, since both are "a real production bug that only a
   specific kind of test would catch" examples):

   > A new CLI subcommand needs its own CLI-dispatch-level test (through
   > `cli.main([...])` and real argparse, not just a test of the underlying
   > function it calls) — an argparse argument silently missing from a
   > subparser while the handler still reads it crashes at runtime with
   > nothing to catch it otherwise.
   > `tests/unit/test_cli_dispatch.py::test_experiment_run_command_parses_all_its_own_arguments`
   > is the reference example: it caught exactly that (a `--seed` argument
   > accidentally dropped from one subparser while being added to a sibling
   > one), which direct calls to the underlying Python function couldn't
   > have surfaced.

2. In the `## Before declaring a task finished` section (currently a single
   line), add a second bullet:

   > When accepting work from a dispatched or delegated agent (including an
   > external tool), re-run the tests and read the diff yourself before
   > treating it as done — a dispatch's own passing self-report isn't
   > sufficient evidence on its own.

   Convert the existing single sentence and this new one into a two-item
   list under that heading if that reads more naturally than two bare
   paragraphs — your call on the exact Markdown shape, not the content.

3. Add a new section, placed after `## Scope discipline` and before
   `## Definition of done` (both are about what kind of work is/isn't
   authorized, so it fits that neighborhood):

   ```markdown
   ## ML modeling work

   Broad technique search is welcome — don't rule out ensembles,
   neural/attention models, or domain-engineered features. But every
   technique clears the same bar before it counts as a result: chronological
   (never random) folds, transparent baselines beaten first, and honest
   calibration/uncertainty reporting. See `docs/NORTH_STAR.md` and
   `plans/04-modeling-simulation-and-experiments.md`'s acceptance gate for
   the full contract; `docs/RESEARCH.md` documents this domain's known
   leakage failure modes and honest accuracy ceiling.
   ```

Verify after editing: the file still reads as one coherent document (no
duplicate headings, no broken cross-references), and none of the existing
content was altered — this is a pure addition.

Work package 2 — `.claude` folder:

Current state, confirmed directly, don't re-derive: `.gitignore` has a bare
`.claude/` line excluding the whole directory. The folder itself has exactly
two files: `.claude/settings.json` (`{"enabledPlugins":
{"espn-fantasy@garavitgabriel": true}}`) and `.claude/settings.local.json`
(`{"enabledMcpjsonServers": ["mlb-mcp"], "enableAllProjectMcpServers":
true}`). Neither contains secrets, credentials, or tokens — already
verified by direct read.

1. In `.gitignore`, replace the bare `.claude/` line with
   `.claude/settings.local.json` — narrowing the exclusion instead of
   removing it outright. `settings.local.json` is Claude Code's own naming
   convention for personal, machine-specific overrides (the same category
   as this file's existing `.env` and `.mcp.json` entries) — it should stay
   local, not become shared project state. `settings.json` is project-level
   configuration (which plugin this project uses) worth having checked in
   for a future session or collaborator.
2. Stage and commit `.claude/settings.json` and the `.gitignore` change
   together. Before committing, re-verify `.claude/settings.local.json` is
   NOT staged (`git status` should show it as untracked/ignored, not
   staged) — this is the one thing in this package worth double-checking
   carefully rather than trusting the `.gitignore` edit alone.

Definition of done:
- CLAUDE.md has the three additions above, integrated cleanly, nothing else
  changed.
- `.claude/settings.json` is committed; `.claude/settings.local.json` is
  not, and stays `.gitignore`'d under a narrowed, specific rule.
- Two separate commits (CLAUDE.md update; `.claude` folder + `.gitignore`),
  pushed to `main`, per this repo's established direct-to-main workflow.
- End with: the exact diff of both commits (small enough to show in full,
  not just describe), and explicit confirmation that
  `.claude/settings.local.json` was never staged.
