## Context

Chadwick's rules for turning event files into events, box scores and summaries are written in its C code
(`cwlib/parse.c`, `gameiter.c`, `game.c`, `box.c`, `cwtools/*`). The first attempt rebuilt them from
`cwevent` output; the owner replaced that with a straight port (D3). Reference: Chadwick development commit
`c685ab5` (reports 0.10.0; see `results.md`). Source: `~/workspace/tmp/chadwick/src`.

## Goals / Non-Goals

**Goals:**

- Same output as the six Chadwick tools, byte for byte, on any valid Retrosheet file, including future seasons.
- Same command-line behaviour (options, help text, errors, exit status).
- Proof that does not depend only on the seasons we happen to have (fuzzing, synthetic games, coverage of the C).

**Non-Goals:**

- Speed (about 25x slower than the C is accepted).
- Dataframes, PostgreSQL loads, switching any mlb_baseball connector to the package.
- Copying Chadwick's defects where the C crashes or reads uninitialised memory (documented in `results.md`).

## Decisions

**D1. Structure follows the C.** One Python module per C source file, functions in the C order with the C names
(`cw/parse.py` = `parse.c`, `cw/gameiter.py` = `gameiter.c`, ...), so each can be read beside its original.

**D2. Differential testing is the contract.** Tests run the real C tools (or small C dump programs built from the
Chadwick sources, under ASAN/UBSAN) and the port on the same input and compare bytes. Inputs where the C has
undefined behaviour are skipped visibly, never compared.

**D3. Port Chadwick's rules; do not infer them (owner decision, 2026-10-01, replaces the
earlier clean-room rule).** The rules for turning event files into events are finite and are
written down in Chadwick's own C code (`cwlib/parse.c`, `gameiter.c`, `game.c`,
`cwtools/cwevent.c`). `retrosheetpy.cw` is a function-by-function Python translation of that
code, kept in the same order and with the same quirks, so each Python function can be read next
to its C original. It is a derivative work of Chadwick (GPL-2.0-or-later, Copyright Dr T L
Turocy and the Chadwick Baseball Bureau); every ported module carries that notice, and the
package's AGPL-3.0-or-later licence is compatible through the "or later" clause. Equality is
still proven by output, against `cwevent` on whole seasons. Rules are never reverse-engineered
from output.

**D4. Reference data.** Fixture captures and small C dump programs run in CI (CI builds Chadwick). Whole-season
and gcov runs are on-demand drivers in `tests/reference/` that need the Retrosheet decade zips; results are
recorded in `results.md` and `all-years.md`.

**D5. Where the C is undefined, define it and say so.** Crashes, `exit(1)`, NULL dereferences and uninitialised reads
become `ValueError` or a defined value, listed in the module docstring and in `results.md`. Everywhere else the port
matches the C exactly, including its quirks.

## Risks / Trade-offs

- [Derivative of GPL source] -> keep the copyright/licence notice in every ported module; reviewer checks notices
  and that nothing was added from guesswork.
- [Reference is a development commit, not the 0.10.0 tag] -> stated in `results.md`; owner decided to target the
  dev commit. CI pins the commit.
- [Future Retrosheet syntax the C cannot parse] -> `guard.py` flags such plays instead of guessing.
- [Slow] -> accepted; stated in the README.

## Open Questions

- Fate of the older csv/inferred-output modules (`play.py`, `validation.py`, `report.py`, `records.py`).
- Public release: separate repository, documentation site, human legal read of the licence note.
