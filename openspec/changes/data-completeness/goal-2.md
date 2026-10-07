# Goal 2: finish data completeness (continues `goal.md`)

Same rules of engagement as `goal.md` (approvals, method, logging, context). This file
only sets the work order for what is left.

## Done means
`mlb coverage --missing-only` lists no unexplained gap. Every remaining gap is either
repaired, or listed in a machine-readable accepted-gaps file with a reason. A nightly
check alerts on any new gap. Evidence is in `results-baseline.md` and `results-final.md`.

## Work order (stop at each "ASK" and wait for a plain yes)
1. Free work, no approval: read the fresh coverage report; write `results-baseline.md`
   (every gap: repair / scope / unavailable / question); log the deployment finding and
   the main-folder update; tick tasks 1.1, 1.2, 1.5, 1.6 as each is evidenced.
2. Build (branch and PR, no production writes): a narrow FanGraphs park-factor repair that
   loads only missing seasons; the accepted-gaps file and its use in `mlb coverage`;
   nightly coverage step with alert; bounded self-repair for safe gaps; cron script.
3. ASK, one command at a time, cheapest first: FanGraphs fielding 2019, FanGraphs park
   factors 1871-1900, mlb_person 147, linescores 85, Kalshi 744, Polymarket 3,560.
   After each: re-run coverage, record before/after in `log.md`.
4. Check tonight's nightly healed the 4 Statcast games and loaded the 2027 schedule.
5. Bootstrap-from-empty test for every repair path; docs updated; close out (tasks 4.1, 4.2).

## Stop conditions
Three failures for one cause; any need for a new or paid source; Negro League questions
(owned by `negro-league-scope`). Compact at about 200k tokens (see `goal.md`).
