# Results and rules learned

> **Reference version.** "Chadwick 0.10.0" in this change means the Chadwick *development* source at commit `c685ab5` (`v0.10.0-26-gc685ab5`, 2026-03-13), which still reports version "0.10.0"; the installed `cw*` binaries and the source the port was translated from are that build. The released v0.10.0 tag differs (checked 2026-10-02: `cwevent`, `cwgame`, `cwdaily`, `cwsub` output differs on 2025 files; `cwcomment` is identical), so the port does not match the released 0.10.0.

## What was built

`retrosheetpy.cw` is a function-by-function Python port of the Chadwick C library and its six
tools (design D3). It is a derivative of Chadwick (GPL-2.0-or-later); every ported module keeps
Chadwick's copyright and licence notice. No rule was inferred from output. The first attempt (the
earlier "infer rules from `cwevent` output" engine, 2019-2025 at 0 mismatches) was replaced by the
port in October 2026; its notes are in git history only.

## Proof (real Chadwick vs the port, stdout byte for byte)

| Check | Result |
|---|---|
| All six tools, 116 seasons 1910-2025, 2,719 event files, real team/roster files (`all-years.md`) | 696 runs, 0 diffs |
| `cwevent` all 164 columns, 16.2 million plays | 0 diffs |
| Installed commands in a clean venv, 116 seasons x 16 option sets (`cli_all_years.py`) | 1,856 comparisons, 0 diffs |
| Every option, valid/malformed/conflicting, + 60 random combos per tool (`cli_sweep.py`) | 4,914 comparisons, 0 diffs |
| Play parser: real + mutated + 60,000 grammar-built plays | 224,296 plays, 0 diffs, 170 skipped (C undefined behaviour) |
| Synthetic well-formed games, 6 tools x 11 option sets | about 4,800 runs, 0 diffs |
| Write side/mutators, 400 random edit scripts, damaged files | bytes identical |
| `lint.c`: fixtures, 250 damaged, 400 mutated files | identical |
| Package test suite (last full run, with coverage) | 840 passed; line+branch coverage 91% |

Reference = Chadwick development commit `c685ab5` (see the note at the top).

## Deviations from the C (all documented in module docstrings)

1. `ValueError` where the C crashes, exits or reads uninitialised memory.
2. Real defects in Chadwick 0.10.0 that the port does not copy: `cwbox -S` segfaults on nearly every
   game (port writes `.runner`; reference build is patched the same way); `cwbox -S` reads past a
   short pitch string (port reads none); `cwbox -X` `pb` attribute reads uninitialised memory (port
   uses 0); parser undefined behaviour (`po_flag[sym-'1']`, unterminated token buffer). The owner
   chose not to report the `-S` bug to Chadwick.
3. `cw_game_read` warnings go to `logging`; the CLI routes them to stderr. `-y` longer than 5
   characters is cut at 5. Usage text prints the bare tool name, not `argv[0]`.
4. Speed: about 25x slower than the C (`cwevent` on 2010NYA: C 0.075 s, port 1.37 s).
5. `records.py`, `play.py`, `validation.py`, `report.py` are the older csv/inferred-output tools and are
   not part of the port; their fate is a later decision.

## Not validated / limits

- Seasons after 2025 are untested by definition; `guard.py` flags plays the C itself cannot parse.
- Some rare parser branches are unreached by real data and are covered only by the grammar fuzzing.
