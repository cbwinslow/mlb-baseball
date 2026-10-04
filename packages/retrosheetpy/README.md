# retrosheetpy

Pure-Python port of the Chadwick tools (`cwevent`, `cwgame`, `cwdaily`, `cwsub`,
`cwcomment`, `cwbox`) plus a Retrosheet file client. Install it instead of building
Chadwick's C library: no compiler, no Chadwick programs, no PostgreSQL, no pandas.
The tools are translated from Chadwick's C source and their output is byte-identical to
the real tools on every season 1910-2025, apart from the defects listed below (proof in the `retrosheet-state-engine` OpenSpec
change). Console scripts use Chadwick's names, so they replace the C tools if first on
`PATH`; `retrosheetpy cwevent ...` also works.

It is about 25 times slower than the C (`cwevent` on one team-season: 0.075 s in C, about
1.4 s here). Where the C crashes or reads uninitialised memory the port raises
`ValueError` instead; see the module docstrings and the change's `results.md`.

## Source and attribution

All data this package reads comes from Retrosheet (https://www.retrosheet.org).
Retrosheet's data-use notice asks that anyone using its data say so. If you
publish anything built on it, include this notice:

> The information used here was obtained free of charge from and is
> copyrighted by Retrosheet. Interested parties may contact Retrosheet at
> "www.retrosheet.org".

This package is independent. Retrosheet does not endorse or sponsor it, and the
package ships no Retrosheet data. The package code is AGPL-3.0-or-later.
`retrosheetpy.cw` is a derivative work of Chadwick (GPL-2.0-or-later, Copyright Dr T L
Turocy and the Chadwick Baseball Bureau); each ported module keeps that notice. Chadwick
itself is needed only to run the parity tests. Captured Chadwick output for the fixture
games is stored under `tests/reference/`.

## Coverage report

`python -m retrosheetpy.report FILE_OR_ZIP... [--chadwick-csv F] [--plays-csv F]`
prints JSON: record counts, plays parsed, every unsupported syntax family, and
field-level disagreements with the references. No native tool is run.

## Differences from Chadwick

- Where the C crashes or reads uninitialised memory the port raises `ValueError` or uses a defined value; `cwbox -S` (which segfaults in Chadwick 0.10.0) and the `pb` attribute of `cwbox -X` are compared against a patched build.
- The reference is Chadwick's development commit `c685ab5` (it reports 0.10.0), not the released v0.10.0 tag, whose output differs on 2025 files.
