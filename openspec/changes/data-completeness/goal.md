# Goal: data completeness

## The goal

Know exactly what data every source offers and what we hold, then close every gap or
explain it, and keep it that way automatically. Done means: `mlb coverage` shows zero
unexplained gaps, every raw table has an expectation or a written reason, a bootstrap from
an empty database reproduces the same result, and a nightly check alerts on any new gap.

## Rules of engagement

**Approvals (the owner decides; Claude never infers consent from silence or a background notice)**
- Free, no approval: read-only queries, reading source documentation, running
  `mlb coverage`, writing docs and code on a branch, opening and merging PRs once `test`
  and `secrets` pass (`CLAUDE.md`).
- Ask first, in one plain sentence: any production write (ingest, repair, migration run by
  hand, deleting anything). Approval covers the named command only, not later runs.
- Optional standing approval: the owner may name specific repair commands that are
  additive and repeatable (for example `mlb ingest mlb_api --mode backfill`) as allowed to
  run without asking again. Claude lists them in `log.md` under "Standing approvals" only
  after the owner says so.
- Never: new sources or paid services without owner approval and a rights review
  (`docs/SOURCE_RIGHTS.md`); `local_research` profile only; destructive SQL; force-push.

**Method**
1. Pick one source or table at a time. Do not run heavy ingests in parallel with each
   other or with a running backfill; check `pgrep` and the logs first.
2. Verify against the source (documentation or a live probe), not memory.
3. Fix at the originating layer. Raw stays source-faithful; do not fill a gap with a guess.
4. A gap that the source cannot serve is recorded as unavailable with evidence, not retried forever.
5. Every fix must also be reproduced by bootstrap from empty (test it), and be repeatable.
6. If a step fails three times for the same cause, stop, log it, and ask the owner.
7. Scope fence: Negro League labelling and new endpoint families belong to
   `negro-league-scope` and `full-source-ingestion`; link to them, do not absorb them.

## The ten steps (the owner's list, tightened)

1. **Scan offerings and coverage.** For each source, list what it offers (tables,
   endpoints, seasons, players, dates) from its documentation and a live probe. Record in
   `docs/sources/<source>.md`. Run `mlb coverage --probe`.
2. **Assess all missing data.** For every source and raw table, state offered, held,
   missing, scope (not wanted) and unavailable. Give every raw table an expectation or a
   written reason. Use the published MLB schedule for current and future games and the
   Chadwick register for players.
3. **Find existing scripts.** For each gap, find the project command that fixes it
   (`mlb ingest ...`, `scripts/`, connector repair paths) and confirm what it does and costs.
4. **Run or build.** Run existing commands (with approval). Where none exists, build a
   maintenance or ingestion script as a normal project command with tests, not a loose script.
5. **Re-check and validate.** Re-run coverage after each fix; confirm row counts, dates,
   and spot-check values against the source. Record before and after.
6. **Log progress** in `log.md` as it happens (format below).
7. **Address issues and log them.** Each problem gets a log entry, an owner (a task, spec
   or PR), and its resolution. Accepted findings are not left only in chat.
8. **Make it permanent.** Nightly coverage run with alert, bounded self-repair for safe
   gaps, cron entries in `scripts/` following `mlb_daily_update.sh` (flock, log file),
   docs updated, tests added.
9. **Handle the unexpected.** If something outside this list blocks the goal, log it,
   decide the smallest fix, and ask the owner if it needs approval or changes scope.
10. **Keep context healthy.** See below.

## Logging (append to `log.md`, newest at the bottom)

Each entry: date and time (UTC), what, why (rationale), command or PR, approval
(who, quoted), before and after numbers, result, follow-up. Decisions get the
reasons and the options rejected. Keep entries short.

## Context management

Claude cannot run `/compact`; the owner types it. Rule: at about 200k tokens of context
(earlier than the owner's 250k, because summaries lose detail the longer they run),
Claude finishes the current step, updates `tasks.md` and `log.md`, writes a handoff
(state, next step, running processes, open approvals) to `log.md`, and tells the owner
in one line that it is a good time to compact. After compaction Claude reads `tasks.md`
and the last `log.md` entries before doing anything.

## Reporting to the owner

Plain, short, one decision at a time (`CLAUDE.md`). Status at each task boundary: what
changed, what is next. Details live in `log.md`, not in chat.
