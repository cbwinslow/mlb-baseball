## 1. Port the library (cwlib)

- [x] 1.1 Port `parse.c` (play parser), `game.c`/`file.c`/`book.c` (read side), `roster.c`/`league.c`, `gameiter.c` (state engine); verify with differential tests against the real C (reader dumps, 224,296 plays through `parse_fuzz.py`/`parse_grammar.py`).
- [x] 1.2 Port the write side and mutators (`write.py`, `Game`/`Scorebook`/`Roster`/`League` methods); verify with `write_dump.c` (400 random edit scripts, damaged files, bytes identical).
- [x] 1.3 Port `lint.c`; verify identical messages and results on fixtures, 250 damaged and 400 mutated files.

## 2. Port the tools (cwtools)

- [x] 2.1 `cwevent` (all 97 + 67 fields, exact ascii/fixed formatting); verify all 116 seasons 1910-2025, 0 diffs.
- [x] 2.2 `cwgame`, `cwdaily`, `cwsub`, `cwcomment`, `cwbox` (text, `-X`, `-S`); verify all 116 seasons, 0 diffs (see `all-years.md`).
- [x] 2.3 Command-line drivers (`cli.py`, console scripts `cwevent` ... `cwbox`, `retrosheetpy`); verify help, `-d`, option errors, exit status identical (`test_cli_differential.py`, `cli_sweep.py` 4,914 comparisons, `cli_all_years.py` 1,856).

## 3. Proof beyond real data

- [x] 3.1 Grammar-based parser fuzzing and random well-formed synthetic games; verify 0 diffs (`parse_grammar.py`, `synth_check.py`).
- [x] 3.2 C coverage by gcov and Python coverage; record what real data does not reach.
- [x] 3.3 New-season guard (`guard.py`): flag plays the C cannot parse instead of guessing.

## 4. CI and close-out

- [x] 4.1 CI job builds Chadwick at the reference commit and runs the package tests.
- [x] 4.2 Remove dead legacy modules (`playtext.py`, `extended.py`).
- [ ] 4.3 Rewrite change docs for the port approach; update `packages/retrosheetpy/AGENTS.md`, `README.md`, `API.md`.
- [ ] 4.4 Run package tests, `ruff`, `ruff format --check`, `mypy --strict`; verify clean output.
- [ ] 4.5 Independent review: licence notices on ported files, documented deviations, silent skips in tests; verify by a reviewer that also runs the code.
- [ ] 4.6 `openspec validate retrosheet-state-engine --strict`; delete `HANDOFF.md`; mark the PR ready (owner says "merge" before any merge).
