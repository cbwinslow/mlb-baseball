# Slice B go/no-go (task 7.5)

Written 2026-10-01 from `parse-coverage.md` and `reference-validation.md`.

## Recommendation: GO, as its own change, with a hard equality target

Evidence for going:

- The play parser reads 2,001,711 real plays and leaves 36 unsupported (about
  0.002%), all rare modifier oddities; `B`/`B1S` (48 plays) are the known open ones.
- Fields readable from play text match Chadwick `cwevent` with 0 mismatches on
  7 seasons (3 held out). The parser is a sound base for a state engine.
- Chadwick can be run locally, so Slice B can be checked event by event.

What Slice B must still build (not started): the game-state engine for outs,
runners, runs, RBI, putouts/assists and base state, then the fields in
`cwevent -f 0-96 -x 0-66`.

Risks to plan for:

- Biggest unknown: how many seasons need special handling (old rules, runner
  placement, deduced games). Only 7 seasons have been compared so far.
- Allowed: read Chadwick source to understand; not allowed: copy or
  line-by-line translate (GPL-2.0 vs AGPL-3.0). Prove equality by output.
- Speed is about 70k lines/s; fine for correctness, may need tuning later.

Suggested first step: new OpenSpec change, state engine proven on 2019 only,
then widen to all seasons; stop and report if any season will not reach 0 mismatches.
