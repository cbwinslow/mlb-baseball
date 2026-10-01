# Play-syntax parse coverage (task 4.5)

Measured 2026-10-01 with `retrosheetpy.PlayCoverage` in diagnostic mode over
official Retrosheet event files. A play counts as "parsed" only when every
component (event, modifier, advance, parenthesised parameter) was classified;
nothing is skipped or guessed.

| Era / source | Files | Plays | Parsed | Unsupported |
| --- | --- | ---: | ---: | ---: |
| Modern regular season, 2019 (`2010seve.zip`) | 2019 `.EV?` | 222,047 | 222,047 | 0 |
| 1950 regular season (+ the 1950 deduced file) | local copy | 106,558 | 106,549 | 9 |
| Early covered seasons 1908-1919, regular (`1910seve.zip`) | `.EVN/.EVA/.EVF` | 1,295,997 | 1,295,994 | 3 |
| Deduced-data files 1908-1919 (`1910seve.zip`) | `.EDN/.EDA/.EDF` | 23,285 | 23,285 | 0 |
| Post-season, all years (`allpost.zip`) | `.EVE` | 166,720 | 166,696 | 24 |
| All-Star games (`allas.zip`) | `.EVE` | 10,558 | 10,558 | 0 |
| Negro League play-by-play (`allevr.zip`) | `.EVR` | 175,714 | 175,714 | 0 |
| Negro League files inside `1910seve.zip` | `.EVR` | 832 | 832 | 0 |
| **Total** | | **2,001,711** | **2,001,675** | **36** |

## Unsupported syntax families (all of them)

Every unsupported component is a modifier. Families are shapes: digit runs
are written `$`.

| Count | Family | Example (file:line) | Note |
| ---: | --- | --- | --- |
| 14 | empty modifier (`//`) | `99//FL` (1950.EDN:3390) | Source has two slashes in a row. |
| 6 | `B` | `14/SH/B.1-2` (1983NLCS.EVE:74) | Bare `B` modifier; undocumented. |
| 5 | `U$` | `E5/G56+/U6` (1996NLD1.EVE:388) | `U` plus fielder; undocumented. |
| 4 | `B$` | `34/B23/SH.1-2` (1925WS.EVE:724) | `B` plus digits; undocumented. |
| 4 | `B$S` | `14/B1S/SH.1-2` (1925WS.EVE:258) | `B` plus digits and a letter; undocumented. |
| 1 | `L$lD` | `D7/L7lD` (1957WS.EVE:112) | Lowercase `l`: looks like a source typo. |
| 1 | `REV` | `K/REV` (2012ALD2.EVE:784) | Undocumented; the documented codes are `MREV` and `UREV`. |
| 1 | `#` | `6/#` (1917BSN.EVN:9723) | A modifier consisting only of an uncertainty marker. |

These stay unsupported on purpose: their meaning is not in Retrosheet's
published documentation, so the parser reports them (strict mode raises,
diagnostic mode lists them) instead of guessing.

## Syntax supported beyond the published modifier list

Found by this measurement and added because they are frequent and regular:

- `BF` as a plain modifier (455 plays, e.g. `K/BF`). The code is recorded;
  its meaning is not interpreted.
- Fielding credits with a throw note inside advance parentheses, such as
  `(826/TH)` (436 plays).

## Reproduce

Not yet a CLI (the machine-readable report is task 5.4). The numbers come from
`PlayCoverage.add_records(...)` over `iter_event_zip`/`read_event_file`
streams, grouped by file extension and archive. Re-run after any parser change.

## Notes and limits

- Modern coverage is one season (2019), as the task requires. Other modern
  seasons were not measured in this run.
- The 1950 copy used here is a local set of 17 team files plus `1950.EDN`, not
  the complete season.
- Parsed means syntactically classified, not baseball-correct. Meaning
  (outs, runs, base state) is the later state-reducer's job and is where
  Chadwick/CSV comparison (section 5) will find disagreements.
