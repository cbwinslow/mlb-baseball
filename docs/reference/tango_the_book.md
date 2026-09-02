# The Book — transcribed reference values for tie-out only

Tom Tango, Mitchel Lichtman, Andrew Dolphin, *The Book: Playing the
Percentages in Baseball* (Potomac Books, 2006).

**Not a substitute for computing these from our own Retrosheet data**
(`gold.run_expectancy_24`, ADR-090). Use these to *check* our computed
values, per `docs/archive/plans/06-package-validation-and-tieout.md`. If a WIRE conversion needs a constant, cite the
row below or fit it on our data. Do not copy an invented Engine-package
weight and call it Tango.

Page numbers below are given only where Tango has restated the table in
public writing. We do not have a marked-up physical copy in this repo.

---

## Table 7 — linear weights, 1999–2002 (run value vs average)

Tango restated these as “Table 7 of The Book” in
[Evolution of a stat: wOBA](https://www.insidethebook.com/ee/index.php/site/comments/evolution_of_a_stat_woba/)
(2025). These are **true linear weights** (run value relative to average),
not wOBA-scale weights.

| Event | Linear weight (The Book Table 7) |
|---|---:|
| HR | 1.397 |
| Triple | 1.070 |
| Double | 0.778 |
| Single | 0.475 |
| Walk | 0.323 |
| Out | −0.30 |

wOBA is these values plus the out value, so every event is measured above
an out. Tango’s own conversion of the same table:

| Event | Table 7 + 0.30 (run value above out) |
|---|---:|
| HR | 1.697 |
| Triple | 1.370 |
| Double | 1.078 |
| Single | 0.775 |
| Walk | 0.623 |
| Out | 0.000 |

FanGraphs then rescales that vector so league wOBA ≈ league OBP. **Those
scaled coefficients change by season** (Guts! table). Our
`team_woba_retrosheet_update.sql` uses a fixed modern set; do not call
that number “FanGraphs wOBA” unless the season’s Guts! row is the source
(admission-queue evidence rule).

`docs/research/SABERMETRIC_LITERATURE_INDEX.md` previously listed walk
0.69 / single 0.88 / … as “The Book Chapter 1.” Those look like
**wOBA-scale** weights, not Table 7. Prefer this file.

Stolen-base linear weights used in this repo’s `bsr_v1` (ADR-081) are
Tango’s `wSB = SB·0.20 + CS·(−0.42) − lgwSB·(1B+UBB+HBP)`, not Table 7.

---

## 24-state run expectancy — nearest published Tango matrix

The Book’s own RE24 table is the 1999–2002 matrix (Chapter 2). Tango later
published a full historical CSV,
[re24_matrix.csv](https://tangotiger.net/files/re24_matrix.csv)
(blog: [Complete Historical Run Expectancy Chart](http://tangotiger.com/index.php/site/comments/complete-historical-run-expectancy-chart),
2024). The **1993–2009** bucket is the published slice that covers The
Book’s years. Values below are `reoi` rounded to 3 decimals from that
file. They are **not** a page scan of the 1999–2002 table.

| Bases | 0 outs | 1 out | 2 outs |
|---|---:|---:|---:|
| empty | 0.546 | 0.292 | 0.113 |
| 1B | 0.943 | 0.564 | 0.245 |
| 2B | 1.173 | 0.722 | 0.349 |
| 1B+2B | 1.561 | 0.965 | 0.471 |
| 3B | 1.441 | 0.992 | 0.387 |
| 1B+3B | 1.853 | 1.216 | 0.532 |
| 2B+3B | 2.050 | 1.449 | 0.625 |
| loaded | 2.387 | 1.633 | 0.813 |

Our production source of truth is `gold.run_expectancy_24`, estimated
from `raw.retrosheet_event` (ADR-090). It was already checked against
Tango within ~0.07 runs. If a WIRE package needs RE24, join that table.
Do not hard-code this grid into a feature.

---

## What this file is for

1. Catch a WIRE conversion that invents `2.2` / `0.0022` “run” weights
   with no citation.
2. Tie out our empirical RE24 / linear-weight SQL against a named Tango
   source.
3. Keep The Book’s true LW and FanGraphs’ scaled wOBA from being treated
   as the same numbers.
