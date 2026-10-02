# Handoff — `retrosheet-state-engine` (updated 2026-10-01, eighth session)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start."

## Owner direction (non-negotiable, restated forcefully this session)
- `retrosheetpy` is a **port of the Chadwick tools to pure Python**, meant as a drop-in replacement
  that people `pip install` instead of building Chadwick's C library. Do it **exactly as Chadwick
  does it**: translate the C source function by function. No guessing, no "our own thing", no rules
  inferred from output, no simplifications. It must be **future-proof**: correct on next year's
  files, not just the seasons we have. Matching output on old seasons is a check, not the method.
- Owner wants short plain replies (options + a recommendation), and a reminder to clear context ~200k.
- Reading AND translating Chadwick source is allowed (decision D3 in `design.md`; source is
  GPL-2.0-or-later, our package AGPL-3.0-or-later, compatible). Every ported module keeps Chadwick's
  copyright/licence notice. Chadwick source: `~/workspace/tmp/chadwick/src/{cwlib,cwtools}`.

## State
- Branch `feat/retrosheet-state-engine-impl`, worktree `/home/cbwinslow/workspace/mlb-pure-python`
  (never touch `/home/cbwinslow/workspace/mlb`). **Committed locally (5 commits); not pushed; no PR.**
  Committing, pushing the branch and opening a PR is pre-authorized; merging needs the owner's "merge".
- Ported from Chadwick C, all in `packages/retrosheetpy/src/retrosheetpy/cw/`: `parse.py` (parse.c),
  `game.py` (`cw_game_read`, comments), `file.py` (`fgets` framing, `cw_strtok`, `cw_atoi`),
  `book.py` (`cw_scorebook_read`, `cw_file_find_first_game`), `roster.py` (roster.c, league.c),
  `tools.py` (cwtools.c driver bits: rosters, date range, game select), `gameiter.py`, `events.py` (cwevent
  fields 0-96 + extended 0-66), `guard.py` (new-season guard).
- Proof this session (cwevent 0.10.0, WITH real TEAM/.ROS files): 1950, 2007, 2020, 2025 = 0 mismatches
  on all 164 columns. (Earlier sessions: all 116 seasons 1910-2025 without rosters = 0.) 301 tests pass;
  ruff, ruff format, mypy --strict clean.
- Differential tests vs the real C (`tests/test_reader_differential.py`, harness `tests/reference/reader_dump.c`,
  needs gcc + Chadwick sources, skips otherwise): reader, scorebook, roster, team file = identical on fixtures
  and 300 damaged files each; reader also identical on 4 whole seasons and 3000 damaged files.
- Parser differential (dev-only, NOT committed): a C harness printing every `CWEventData` field per play,
  forked per line under ASAN/UBSAN (to skip inputs where the C has undefined behaviour), against `parse_event`
  on ~185k real + mutated play strings. First run: 11 diffs, all mutated `POCS`/pickoff texts; cause was the
  C's unterminated token buffer (fixed: `_Parser._tok`/`put`) and `po_flag[sym-'1']` out-of-bounds (C undefined
  behaviour, port guards it). Re-run after the fix: 192k plays, only 8 diffs, all garbled `POCS(...` plays (C undefined behaviour). Harness
  committed as `tests/reference/parse_dump.c` + `parse_fuzz.py`. Deviation 2 closed.
- New-season guard: `tests/reference/new_season_guard.py ZIP YEAR` (and `cw/guard.py`). It already flags two
  real 2025 plays that Chadwick also fails to parse: `BOS202509030` `C/E2/OBS/G2-.3-H(RBI);2-3;B-1` and
  `KCA202506140` `BK.2-3(SB3);1-2`.
- Only `cwevent` is ported. NOT ported: `cwgame` (1786 lines), `cwbox` (+ `box.c`), `cwdaily`, `cwsub`,
  `cwcomment`, `lint.c`, `book.c` write side, the CLI driver (arguments, `-f` field lists, output formats).

## Known deviations from the C (remaining)
1. `cw/game.py`: `sub`/`badj`/etc. needing a previous play raise `ValueError` where the C crashes (NULL).
2. `parse.py`: arrays enlarged (C overruns them: UB); `_pickoff_caught_stealing` guards the C's
   `po_flag[sym-'1']` out-of-bounds write; `play[]` truncated to 19 like `CW_STRLCPY`. Finish the parser
   differential (above), then re-read any function it flags line by line.
3. `cw_game_read` warnings go to `logging` ("retrosheetpy.cw"), not stderr. A NUL hand char is kept as `\0`.
4. Version: proof is against `cwevent` 0.10.0 only; record Chadwick version/commit in `results.md`.
5. `records.py` (csv-based) is still used by the non-port tools (validation, report, play); the port no longer uses it.

## Next steps (in order)
1. (Done 2026-10-02: full sweep with rosters = 0 differences; see results.md.)
2. Port the remaining tools from the C, in this order: `cwgame` (smallest), `cwdaily`, `cwsub`,
   `cwcomment`, `cwbox` (+ `box.c`), then `lint.c` and the CLI driver. Prove each against the real binary on
   whole seasons (same method as `season_report.py`).
3. Value check (owner asked "is this worth it / why hasn't anyone done it"): NOT yet researched.
   Search for existing pure-Python Chadwick/Retrosheet parsers and wrappers and report honestly.
   A partial port has little value; completeness matters.
4. Close-out: update `tasks.md`/`results.md`, `packages/retrosheetpy/AGENTS.md`, independent reviewer
   (general-purpose agent with Bash) checks notices, deviations and silent skips;
   `openspec validate retrosheet-state-engine --strict`; delete this file before the PR; push, open PR.

## Commands
- Season check (needs `cwevent` 0.10.0 at `~/.local/bin`, dev-only), all 164 columns:
  `uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/season_report.py ZIP YEAR --out r.json`
  ZIPs: `Client(cache).download(resolve(Product.EVENTS_DECADE, YEAR))` (public Retrosheet; decades 1910-2020;
  the session scratchpad cache is gone — re-download). A sweep script ran years in parallel with `xargs -P4`.
- Tests: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests -q -p no:cacheprovider`
- Lint/type: `uvx ruff check packages/retrosheetpy`, `uvx ruff format --check packages/retrosheetpy`, `uvx mypy --strict packages/retrosheetpy/src`
- OpenSpec: `export PATH=$HOME/.nvm/versions/node/v24.16.0/bin:$PATH; openspec validate retrosheet-state-engine --strict`
- Use `grep -n` / `find`, not `ls` (RTK hook). Commit hook runs ruff-format: if a commit "fails", re-run `ruff format` and commit again.
  Never claim checks passed unless run.
