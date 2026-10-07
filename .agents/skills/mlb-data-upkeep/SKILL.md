---
name: mlb-data-upkeep
description: Keep the MLB database complete and current. Use when asked whether data is missing, whether a source changed, or to fix a coverage gap. Reads the reports, shows a dry run, asks before any production write, and logs the result.
allowed-tools: Bash(mlb:*), Bash(psql:*)
license: MIT
compatibility: Requires the `mlb` CLI and DATABASE_URL for the target database.
---

# MLB data upkeep

The deterministic tools find and fix gaps; you read their reports, decide, and ask. Never guess data. Command list: `docs/COMMANDS.md` (generated). Rules: `openspec/project.md` and the root `AGENTS.md`.

## Steps

1. **Name the database.** Production is `mlb` and is real data. Say which one you are using before anything else.
2. **See what is missing (read-only).** `mlb coverage --missing-only --unexplained --json`. A gap listed in `mlb_baseball/coverage/accepted_gaps.toml` is already explained; do not chase it.
3. **See what the sources changed (read-only toward the database).** `mlb schema-watch --json`. Exit 1 is drift (a field or file was added, removed or retyped), exit 2 is "could not check". Do not treat 2 as "nothing changed".
4. **Preview the fix.** `mlb repair --dry-run --json`. Each action is `planned`, `report_only`, `capped` or `suspended`. Only `planned` ones can run, and only the listed command. For anything else read the coverage `fix` line and the table's `note`.
5. **Ask the owner before any production write.** One plain sentence: what it does and what it touches, then yes or no. Approval covers the named command only. Show the command after approval, not before as the question.
6. **Run it.** `mlb repair --apply`, or the single `mlb ingest <source> ...` command the owner approved. Run one at a time; check `pgrep -fa "mlb ingest"` first so two heavy loads never overlap.
7. **Re-check.** Run step 2 again. A gap that remains after two runs is not repaired by trying again: stop and report it.
8. **Log it.** Append to the change's `log.md`: date and time (UTC), what, why, command, who approved (quoted), before and after numbers, result.

## Rules

- A new field or file from `schema-watch` is a decision, not a repair: report it. `mlb schema-watch --accept` only after the owner has seen it.
- Three failures in a row suspend a repair. `mlb repair --reset raw.<table>` only after the cause is fixed.
- `mlb ingest <source> --dry-run` checks arguments and rights profile and loads nothing.
- No new or paid sources, no profile other than `local_research`, no destructive SQL, no force-push.
- A check that cannot reach its source says "unchecked". Never report it as fine.
