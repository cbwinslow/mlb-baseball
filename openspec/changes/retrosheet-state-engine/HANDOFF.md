# Handoff — `retrosheet-state-engine` (updated 2026-10-01, seventh session)

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
  (never touch `/home/cbwinslow/workspace/mlb`). **Nothing committed this session; not pushed; no PR.**
  Committing, pushing the branch and opening a PR is pre-authorized; merging needs the owner's "merge".
- Done and uncommitted: `packages/retrosheetpy/src/retrosheetpy/cw/{parse,game,gameiter,events}.py`
  (ports of `parse.c`, `game.c` read side, `gameiter.c`, `cwevent.c` fields 0-96 + extended 0-66);
  old hand-built `state.py/outcome.py/fielding.py` + `test_state.py` + `implemented_fields.py` DELETED
  (owner approved); `tests/test_cw.py`; `season_report.py` now checks the port on all 164 columns;
  docs updated (D3 reversed in design.md/proposal.md, `packages/retrosheetpy/AGENTS.md`);
  `records.py::_int` now tolerates a trailing blank (Chadwick `atoi` does).
- Proof: **all 116 seasons 1910-2025 = 0 mismatches, 0 misaligned, 0 errors on all 164 columns**
  (~16.2M plays) against `cwevent` 0.10.0. 253 tests pass; ruff, ruff format, mypy --strict clean.
- **Only `cwevent` is ported.** NOT ported: `cwgame`, `cwbox` (`box.c` 1578 lines), `cwdaily`, `cwsub`,
  `cwcomment`, `roster.c`/`league.c`/`book.c`/`lint.c`, `cwtools.c` (CLI driver/filters).

## Known deviations from the C (fix these FIRST — each is a future-correctness risk)
1. **File reading is ours, not Chadwick's.** `records.py` (csv-based) replaces `cw_game_read`'s
   `fgets`/`cw_strtok` reader. Differences: quoting, field counts, 1024-char line limit, unknown
   record types (C warns and skips; ours raises), blank lines, `\r`. Port `cw_game_read` and
   `cw_strtok` (see `cwlib/util.h`, `game.c:674`) exactly, then keep `records.py` only if it is
   provably equivalent on every season (add a differential test against Chadwick for line framing).
2. `cw/parse.py`: parser `token` is a Python str, not Chadwick's shared `char[20]` buffer (stale-token
   behaviour on failed parses not reproduced); arrays enlarged to 32/64 (C overruns them: UB);
   `_pickoff_caught_stealing` guards a C out-of-bounds index; `play[]` truncated to 19 chars like
   `CW_STRLCPY`. Re-read every function against `parse.c` once more, line by line.
3. `cw/game.py`: `sub` before the first play raises (C crashes); `data/stat/event/line/version`
   records ignored; `com` text handling (`ej,`, `umpchange,`, `suspended,` date change in
   `cw_gameiter_process_comments`) NOT ported. `cw_atoi`/`cw_strtok` re-implemented as `_atoi`.
4. `cw/events.py`: rosters not ported (`roster.c`: `cw_roster_batting_hand/throwing_hand`); hands are
   `?` unless `badj/padj` records say so. C `NULL` strings print `(null)` (assumed glibc; matched so far).
5. Version: proof is against `cwevent` 0.10.0 only. Need a yearly check (below) and a recorded
   Chadwick version/commit in the results note.

## Next steps (in order)
1. Fix deviations 1-4 above by porting the C exactly; re-run the sweep (command below) — must stay 0.
2. Add the **new-season guard**: a documented command that runs a new season through the port and
   `cwevent`, plus a test/log that fails loudly on any unparsed play (`parse_ok` false) or unknown
   record, so next year's data cannot be silently wrong. Record Chadwick version in `results.md`.
3. Port the remaining tools from the C, in this order: `cwgame` (smallest), `cwdaily`, `cwsub`,
   `cwcomment`, `cwbox` (+ `box.c`), then roster/league/book/lint and the `cwtools.c` driver/CLI.
   Prove each against the real binary on whole seasons (same method as `season_report.py`).
4. Value check (owner asked "is this worth it / why hasn't anyone done it"): NOT yet researched.
   Before claiming value, search for existing pure-Python Chadwick/Retrosheet parsers and wrappers
   (e.g. whether Chadwick Python bindings need a C build) and report honestly. Pitch: `pip install`
   with no C toolchain, byte-identical to Chadwick. A partial port has little value; completeness matters.
5. Close-out (tasks 4.3/4.4 are effectively done; update `tasks.md`/`results.md`): update
   `packages/retrosheetpy/AGENTS.md`, independent reviewer (general-purpose agent with Bash) checks
   notices, deviations and silent skips; `openspec validate retrosheet-state-engine --strict`;
   delete this file before the PR; commit, push branch, open PR.

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
