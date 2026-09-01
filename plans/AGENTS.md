# Execution Plans DOX

## Purpose

Own the ordered work queue, acceptance gates, and evidence/progress records used
to coordinate implementation across humans and agents.

## Ownership

- numbered `*.md` plans define broad durable work programs;
- `README.md` identifies the active sequence and paused/deferred tracks;
- `PROGRESS.md` records evidence of completed work and important handoffs;
- dated design/goal-seek plans under `docs/superpowers/` may supplement this tree
  but do not silently override the active plan index.

## Local Contracts

- A plan is intent, not proof of implementation.
- Mark work complete only when its acceptance evidence exists.
- Keep active/paused/blocked status explicit; older modeling/site plans must not
  pull work ahead of the current research-database focus.
- Do not silently begin the next work package when the current gate has not been
  reviewed.
- Bounded delegated work must name the exact plan/work package and return changed
  files, verification performed, limitations, and unresolved findings.
- Preserve negative/rejected findings when they matter to future decisions; do
  not rewrite plan history to make work look cleaner than it was.
- If repository truth has moved beyond a plan, update the active index/living docs
  and treat the old plan as historical rather than forcing code back to stale
  intent.

## Work Guidance

Prefer small implementation slices with observable acceptance criteria. Separate
research/design decisions from mechanical execution when that improves review.

Plans should reference canonical source contracts (`AGENTS.md`, `.dox.md`, table
contracts, registries, ADRs) instead of restating them in full.

When a plan affects multiple subtrees, require each implementer to read the local
DOX chain for the files it edits.

## Verification

Before marking a work package complete:

1. inspect the diff;
2. run the checks required by the affected subtree DOX;
3. confirm docs/registries/contracts match behavior;
4. record concrete evidence/results, not only "done";
5. identify the next gate without automatically starting it.

## Child DOX Index

No child DOX files currently. If plan families become independently maintained,
add children by durable program rather than by date.
