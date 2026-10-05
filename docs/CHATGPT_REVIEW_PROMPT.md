# Prompt for an outside review (ChatGPT or any reviewer)

Copy everything below the line into the reviewer. The repository is public:
https://github.com/cbwinslow/mlb-baseball (branch `main`).

---

You are reviewing an MLB research database project. I am the owner. I am not a
specialist, so use short sentences and plain words, define any jargon, and lead
each answer with the one thing I should do.

## What the project is

A PostgreSQL database of MLB data from many sources (MLB Stats API, Statcast,
Retrosheet, FanGraphs, Baseball Reference, betting markets). It has four layers:
`raw` (source-faithful downloads), `core` (cleaned, reconciled), `gold`
(metrics and model features) and `meta` (run records). The goal is trustworthy,
reproducible numbers that can feed ML models that predict game outcomes.
Priorities in order: reliable ingestion, correct metrics, easy research exports,
then models.

## Read these files in this order

1. `openspec/project.md` : the project constitution (goals, phases, rules).
2. `openspec/HANDOFF.md` : current state and how we work.
3. `openspec/changes/pipeline-recovery/` : the active plan.
   - `proposal.md` (why), `design.md` (decisions D1 to D11), `tasks.md`
     (worklist), `results.md` (evidence log: every finding and approval).
4. `docs/DECISIONS.md` : the architecture decision log (ADRs).
5. `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md`, `docs/SOURCE_RIGHTS.md`.
6. `openspec/changes/stable-ids-incremental-conform/` : the speed design.
7. `openspec/changes/metric-catalog/` and `mlb_baseball/metrics/*.yaml` : the
   50 metric definitions and their status.
8. `openspec/changes/model-readiness-audit/` : what blocks the models.

## Where we are (2026-10-05)

- The nightly job (`mlb nightly`) runs about 2 hours: update 14 to 22 min,
  conform 44, report 14, predict 47. Planned speed fix: stable ids plus
  per-season incremental conform (option A in `pipeline-recovery`). Not built.
- `mlb doctor` passes 356 of 372 checks. The failures are classified in
  `pipeline-recovery/results.md`: real defects, wrong checks, accepted.
- Fixed at the source so far: a playoff data leak, `away_woba` overwritten with
  NULL, a pitch-sequence double count, and three sibling live-update SQL files
  with the same overwrite pattern.
- Metrics: 50 total, only 1 `validated`, 16 `implemented-untested`, 33
  `published`.
- Catcher framing (task 9.4): the in-season columns count "called strikes" from
  play text, which is wrong. A rebuild from Statcast pitch locations did not
  match Savant's published values (correlation 0.18 to 0.35), so it cannot be
  called correct. The open question is whether to withhold those columns and
  keep the Savant prior-season value.
- Known open items: empty ingestion ledger (`meta.ingestion_item`), several
  health-check bounds that may be wrong, prediction counts that look inflated
  (possible join fan-out), Negro League games blocking model readiness
  (issue #256).

## What I want from you

Answer in this order, each part short:

1. **Direction check.** Is the plan in `pipeline-recovery` the right order of
   work? What would you change or drop?
2. **Gaps.** What is missing from the specs that would let a wrong number reach
   a model? Focus on point-in-time leakage, hard-coded constants, silent NULL
   to zero, and metrics with no outside tie-out.
3. **Metric audit.** Propose a simple repeatable method to take each of the 50
   metrics to `validated` (definition, formula cited to a source, hand-worked
   test, outside reference comparison, null policy). Say what "done" means.
4. **Speed.** Is option A (stable ids plus incremental conform) the best way to
   cut the 2 hour run? Is there a faster or simpler way? Say what to measure
   first.
5. **Catcher framing.** Withhold in-season columns, or is there a sound way to
   rebuild them? Cite sources.
6. **Top five risks**, ranked, each with one concrete next step.

## Rules for your answer

- Quote the exact file and section you are judging.
- Separate what you found from what you recommend.
- If you are unsure about a fact, say so and name the file that would settle it.
- Do not invent numbers or citations. Do not suggest widening a health-check
  bound without a cited reason.
- Do not assume anything about files you have not read.
