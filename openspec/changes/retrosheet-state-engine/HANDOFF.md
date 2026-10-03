# Handoff — `retrosheet-state-engine` (updated 2026-10-03, fourteenth session)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start."

## Owner direction (non-negotiable, restated forcefully)
- `retrosheetpy` is a **port of the Chadwick tools to pure Python**, meant as a drop-in replacement
  that people `pip install` instead of building Chadwick's C library. Do it **exactly as Chadwick
  does it**: translate the C source function by function. No guessing, no "our own thing", no rules
  inferred from output, no simplifications. It must be **future-proof**: correct on next year's
  files, not just the seasons we have. Matching output on old seasons is a check, not the method.
- Owner wants short plain replies (options + a recommendation), and a reminder to clear context ~200k.
  Latest instruction: "I don't care what you do, just keep working on this ... no guessing, keep
  translating the Chadwick code to Python code."
- Reading AND translating Chadwick source is allowed (decision D3 in `design.md`; source is
  GPL-2.0-or-later, our package AGPL-3.0-or-later, compatible). Every ported module keeps Chadwick's
  copyright/licence notice. Chadwick source: `~/workspace/tmp/chadwick/src/{cwlib,cwtools}`.

## State
- Branch `feat/retrosheet-state-engine-impl`, worktree `/home/cbwinslow/workspace/mlb-pure-python`
  (never touch `/home/cbwinslow/workspace/mlb`). **Committed locally; not pushed; no PR.**
  Committing, pushing the branch and opening a PR is pre-authorized; merging needs the owner's "merge".
- **All six Chadwick tools are now ported, with their command-line drivers**, in
  `packages/retrosheetpy/src/retrosheetpy/cw/`:
  `parse.py` (parse.c), `game.py`, `file.py`, `book.py` (read side), `roster.py` (roster.c, league.c),
  `tools.py` (cwtools.c bits), `gameiter.py`, `box.py` (box.c), `lint.py` (lint.c),
  `events.py` (cwevent: all 97+67 fields, value logic + exact ascii/fixed formatting via `_FORMATS`),
  `cwgame.py`, `daily.py` (cwdaily), `sub.py` (cwsub), `comment.py` (cwcomment),
  `cwbox.py` (cwbox text), `cwboxxml.py` (cwbox -X), `cwboxsml.py` + `xmlwrite.py` (cwbox -S),
  `cli.py` (cwtools.c `main`, option parsing, help/`-d` texts, per tool), `__main__.py`, `guard.py`.
  Console scripts (pyproject): `cwevent`, `cwgame`, `cwdaily`, `cwsub`, `cwcomment`, `cwbox` (owner
  chose to DROP the `-py` suffix, 2026-10-02; they shadow the C tools if first on PATH. Tests find the
  real C tools with `chadwick_tool.real_tool`, which skips the venv; `CHADWICK_BIN` overrides). `python -m retrosheetpy.cw TOOL ...` also works.
- Proof (every one against the real C, byte for byte, stdout):
  - cwevent: all 164 columns 1910-2025 (earlier sessions); this session exact line formatting,
    ascii + `-ft`, `-f 0-96 -x 0-66`, with real rosters: 1915, 1950, 2007, 2025 = 0 diffs;
    81 differential tests (fixtures x 4 variants x with/without synthetic rosters, damaged copies).
  - cwgame: both formats, all fields + ext, real rosters: 1915, 1950, 1976, 1998, 2007, 2020, 2025 = 0 diffs.
  - cwbox text: same 7 seasons + 1980 = 0 diffs; `-X` XML and `-S` SportsML: 7 seasons = 0 diffs
    (see the C defects below; reference build patched for `-S`).
  - cwdaily 1950 = 0 diffs (all event files, both formats); cwsub, cwcomment: 1950, 1980, 2007, 2025.
  - lint.c: identical messages and result on fixtures, 250 damaged and 400 mutated files.
  - CLI: `tests/test_cli_differential.py` runs the real tool and the port in scratch dirs for 23
    option cases x 6 tools (help, `-d`, bad option, bad field specs, missing files, missing
    team file, game/date selection, header, fixed, xml): stdout, stderr and exit status identical.
  - Full suite at last run before the CLI: 534 passed. Re-run (a run was started at the end of the
    session writing `/tmp/fullsuite.txt`; do not trust it, re-run).
- Harnesses: `tests/chadwick_tool.py` (`run_tool` = installed binary; `build_sanitised`/`run_filled`/
  `run_clean` = tool built from the Chadwick sources under ASAN/UBSAN, optionally with source
  patches, run with different allocator fill bytes so inputs with undefined behaviour are skipped),
  `tests/reference/*_season.py ZIP YEAR` (season checks, need the Retrosheet decade zips; copies
  from earlier sessions were at `/tmp/claude-1000/-home-cbwinslow-workspace-mlb/*/scratchpad/ev/*seve.zip`,
  otherwise `Client(cache).download(resolve(Product.EVENTS_DECADE, YEAR))`).

## Real Chadwick 0.10.0 defects found (documented in the module docstrings; port deviations)
1. `cwbox -S` (`cwboxsml.c` `cwbox_action_baseball_play`) passes `state->runners[1]`/`[2]` (whole
   structs) to `%s`: the real binary **segfaults on nearly every game**. Port writes `.runner`
   (what `runners[3].runner` does). Reference build for tests patches the same
   (`chadwick_tool.SPORTSML_PATCH`, also clamps defect 2).
2. `cwbox -S`: a play whose pitch string is shorter than the previous event's is read from past its
   NUL (real data has some, e.g. 1915SLA). Port reads no pitches there.
3. `cwbox -X` (`cwboxxml.c` `cwbox_xml_player`): `player->positions[pos] == 2` indexes by fielding
   position and reads uninitialised `malloc` memory -> `pb` attribute depends on the allocator.
   Port defines those entries as 0. Real output differs from the port only in `pb="..."`.
4. Earlier sessions: C undefined behaviour in the parser (`po_flag[sym-'1']`, unterminated token
   buffer), `exit(1)`/NULL derefs -> port raises `ValueError`.

## Known deviations from the C (remaining)
1. `ValueError` where the C crashes/exits/reads uninitialised data (all modules; see docstrings).
2. `cw_game_read` warnings go to `logging` ("retrosheetpy.cw"); `cli.py` routes them to stderr.
3. Proof is against Chadwick dev commit c685ab5 (reports 0.10.0; NOT the released v0.10.0 tag, which differs). Noted in `results.md`/`all-years.md`.
4. `records.py` (csv-based) is still used by the non-port tools (validation, report, play).
5. `cli.py`: `-y` longer than 5 chars is cut at 5 (the C leaves it unterminated).

## Write side and mutators (done, twelfth session)
- `cw/write.py`: `game_write` (+ header/starters/comments/events/stat/line/data parts; like the C it never
  writes `evdata`), `scorebook_write`, `roster_write`, `league_write`. `%s` of NULL prints `(null)`.
- Mutators as methods: `Game.set_version/info_append/info_set/starter_append/event_append/truncate/
  substitute_append/{data,stat,evdata,line}_append/data_set_er/comment_append/replace_player`,
  `event_comment_append`; `Scorebook` (book.py: append/insert/remove/iterate/read, keeps leading comments);
  `Roster.set_*/player_insert/player_append/player_count`, `Player.set_*_name`, `League.roster_append`.
- Proof: `tests/reference/write_dump.c` (+ `write_dump.py`, `tests/test_write_differential.py`): reads with
  Chadwick, applies a script of edits, writes; bytes identical to the port on fixtures, 400 random edit
  scripts, damaged files, scorebook insert/remove (incl. equal date+number), rosters, team files.
  Mutation-tested (two deliberate bugs were caught).
- Command namespace: Chadwick has exactly six tools; all ported as `cwevent` ... `cwbox`, plus the
  umbrella `retrosheetpy cwevent ...` (`cli.main_umbrella`, also `python -m retrosheetpy.cw`).
- Owner question "should we fix Chadwick's bugs?": recommendation given = no. Match the C wherever its
  behaviour is defined; only where it crashes or reads garbage does the port differ (ValueError / defined
  value), documented above. Not yet confirmed by the owner.

## Thirteenth session: what was done (all committed locally, nothing pushed; HEAD 2be115b)
- `-py` suffix DROPPED (owner choice): console scripts are `cwevent cwgame cwdaily cwsub cwcomment cwbox` + `retrosheetpy`.
  Tests find the REAL C tools with `chadwick_tool.real_tool` (skips the venv; `CHADWICK_BIN` overrides). Never use
  `shutil.which("cwevent")` in tests: inside the venv it finds the port and compares the port with itself.
- **Reference version found wrong and fixed in docs:** "Chadwick 0.10.0" = dev commit c685ab5 (`v0.10.0-26-gc685ab5`),
  which still prints 0.10.0. The released v0.10.0 tag DIFFERS (cwevent/cwgame/cwdaily/cwsub differ on 2025; cwcomment same).
  Owner decision: target the dev commit; no old-release mode. Noted at the top of `results.md` and `all-years.md`.
- **Request 1 (all-years run) DONE:** `tests/reference/all_years.py` (+ coverage hook `COVERAGE_DATA`): 6 tools x 116 seasons
  1910-2025, 2719 event files, 696 runs, 0 diffs, 0 skipped. 1964DET.EVA makes the C hit a harmless `touches[-1]` write
  (`chadwick_tool.TOUCHES_UNDERFLOW` tolerates exactly that UBSAN message); 1964 cwbox re-run alone after that. Table:
  `all-years.md` (this directory).
- **End-to-end installed commands DONE:** `tests/reference/cli_all_years.py ZIPDIR PORT_BIN` (wheel in a clean venv; both tools
  started by bare name with only their own bin dir on PATH): 116 seasons x 16 option sets = 1856 comparisons, 0 diffs,
  21.7 GB. Known deviation: C prints argv[0] as typed in usage text; the port prints the bare name.
- **Option sweep DONE:** `tests/reference/cli_sweep.py`: every option, valid/malformed/conflicting, + 60 random combos per tool,
  7 seasons: 4914 comparisons, 0 diffs (1747 are cases where the real tool errors; port matched stderr+exit).
- **Coverage measured:** pytest suite alone 87%; suite + real data (cwevent all years, other tools on 12 sample seasons) = 92%
  lines+branches (6408 stmts). Biggest gaps: `cw/parse.py` 90%, `cw/box.py` 85%, `extended.py` 47%, `playtext.py` 0%,
  `cw/__main__.py` 0%, lint.py 87%. Python coverage data: scratchpad `combined.cov` (may be gone; regenerate:
  `COVERAGE_DATA=PREFIX python all_years.py ... ` then `coverage combine`).
- **Chadwick (C) coverage via gcov:** `scratchpad/gcovbuild.sh SCRATCH` builds instrumented tools into `SCRATCH/gcov/bin`;
  `tests/reference/gcov_run.py ZIPDIR GCOV_BIN` runs them over all seasons x option sets + the sweep (6802 runs, none crashed);
  then `gcov -b -o lib|tool ...` per source. Real data leaves unreached (C lines): parse.c rare syntax (TUR advance, TH1/TH2/TH3/THH
  modifiers, INT/BINT/OBS/G/U/AP/BR/FO combos, muff flag, bunt/foul/DP flag branches, many `cw_parse_invalid` returns),
  cwevent.c 230-246 + gameiter.c 672-689 (batter hand from `padj` pitcher-hand records), gameiter.c 379-384 (backward runner
  advances 3-2 / 3-1), 627-632, cwgame.c linescore/lob/(null) bits, cwdaily.c stat=-1 error paths, cwbox.c roster-less names
  (`visitors->city` NULL), ph/pr positions, `-S`. cwboxsml.c/xmlwrite.c unreached because the real `-S` segfaults (covered by the
  patched sanitised build instead). book.c/game.c/roster.c/league.c unreached = write/mutator side (covered by write_dump.c).
- Owner said: do NOT file the cwbox -S bug with Chadwick.

## Fourteenth session: what was done (committed locally, nothing pushed)
- **Parser fuzzing, grammar-based:** `tests/reference/parse_grammar.py` builds plays from every token `parse.c` compares against
  (error/trajectory modifiers, running plays, SBH(UR), `;` chains, advances, malformed forms). `parse_fuzz.py` refactored
  (`compare()`; `GRAMMAR=N`, `ONLY_GRAMMAR=1`, `DIFFS=file`). The C harness is now built with `-fsanitize=bounds-strict
  -fno-sanitize-recover=all` so plays where Chadwick stores past `putouts[3]/assists[10]/errors[10]/touches[19]` into the next struct
  field (undefined) are skipped, not compared. Result: 224,296 plays (real + mutated + 60,000 grammar), 0 diffs, 170 UB skipped.
  C `parse.c` parser functions: every line reached except none left (the ~70 other unreached lines are `cw_event_*` helpers the C
  tools never call: `cw_event_data_copy`, `is_official_ab`, ...). Port `parse.py` 99% (rest = those helpers, now unit-tested in
  `test_event_helpers.py`, and a few C-unreached branches).
- **Synthetic games (the other coverage gaps):** `tests/reference/synth_games.py` (+ `synth_check.py`): random well-formed games with a
  runner simulator (so `cwbox` lint passes), `padj/badj/ladj/radj/presadj`, switch hitters, backward advances (`3-2`, `3-1`, `2-1`),
  PH/PR, DH loss, pitcher re-entry, roster-less players, `htbf`, suspended-game comments, box-score-only (`stat bline/pline/dline...`)
  games, "chaos" files with deliberately inconsistent plays. 6 tools x 11 option sets, stdout+stderr+status vs real: 0 differences over
  ~4,800 runs (seeds 1-780). Runs where the C crashes or whose output changes with `MALLOC_PERTURB_` (uninitialised memory, e.g. `pos`
  of a pinch hitter in `cwbox -X` on box files) are skipped. C coverage by gcov afterwards: gameiter.c all but 6 lines (319-320, 658,
  725, 731, 737), box.c box-file path all but 9, cwevent/cwgame/cwdaily/cwsub/cwcomment/cwbox only CLI `main` paths missing (those are
  covered by the option sweep, not by this run). Pytest: `test_parse_grammar_differential.py` (3 seeds x 3000 plays),
  `test_synthetic_differential.py` (24 seeds x 11 runs, ~90 s), `test_event_helpers.py`.
- **Speed:** profiled `cwevent` on 2010NYA (C 0.075 s, port 2.0 s). Hotspot was a regex per output field in `events._c_format`
  (231,588 calls). Parsed once per format (`functools.cache`) + selected-field list built once per game: 2.0 s -> 1.37 s (-30%).
  Re-profile: remaining cost is spread (field lambdas, `fgets`, `read_game`, `len`). No further cheap win seen; whole 2010 season
  `event_season.py` still 0 diffs (4m52 for 30 teams x 2 formats). README should say ~25x slower than the C.
- Full suite: 840 passed (15 min, with coverage on); ruff, ruff format, `mypy --strict src` clean. Python coverage of the suite alone 91%
  (lines+branches, 6413 stmts); `extended.py` 47% and `playtext.py` 0% are legacy "inferred from output" modules (see below).
- Found while looking: `playtext.py` is imported by nothing; `extended.py` only by `tests/test_extended.py`; `play.py`,
  `validation.py`, `report.py`, `records.py` are the old csv/infer tools. Candidates to delete or move onto `cw/` (owner decision).

## Next steps (in order)
1. **Decision 1 done (owner chose A):** deleted `playtext.py`, `extended.py`, `test_extended.py`. `play.py`/`validation.py`/`report.py`/`records.py` stay for now. **Still open:** CI choice — (A) run only non-Chadwick tests, or (B) also build Chadwick c685ab5 in CI (recommended). The owner said "option A" without saying which decision; confirm. (Old text follows.) (a)
   `play.py`/`validation.py`/`report.py`/`records.py` (move onto `cw/` or drop); (b) CI: add a job running `packages/retrosheetpy/tests`
   (non-differential tests run; differential ones skip without Chadwick) — or also build Chadwick c685ab5 in CI so the parity tests run
   (autotools build, more CI time). Root `pyproject` `testpaths` already lists `packages/retrosheetpy/tests`; the package is a uv
   workspace member (`packages/*`).
2. Optional remaining coverage: the 6 gameiter lines above (go-ahead-RBI clearing, strikeout-batter-hand, fc_flag responsibility on
   3rd), `cw/__main__.py` (tested only through subprocess), lint.py branches, `box.py` box-file branches in-process.
3. **Owner request 3 (later, not now):** separate repo + documentation site (see earlier list; licence note unchanged).
4. Close-out: rewrite `tasks.md`/`results.md`/`proposal.md`/`design.md` for the port approach (they still describe the old
   infer-from-output plan; results.md says "No Chadwick code was copied", obsolete), update `packages/retrosheetpy/AGENTS.md`
   (owning-change path says `pure-python-retrosheet`; add `cw/` map, console scripts, harness notes incl. `synth_*`/`parse_grammar`,
   the PATH-shadowing note), README.md/API.md (speed: ~25x slower than C); independent reviewer (general-purpose agent with Bash)
   checks notices, deviations, silent skips; `openspec validate retrosheet-state-engine --strict`; re-run full suite + ruff +
   format + mypy; delete this file before the PR; push, open PR (merge needs the owner's "merge").

## Commands
- Tests: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests -q -p no:cacheprovider`
  (about 10 minutes; the CLI/event/game/box differential files alone take about 3 minutes).
- Lint/type: `uvx ruff check packages/retrosheetpy`, `uvx ruff format --check packages/retrosheetpy`, `uvx mypy --strict packages/retrosheetpy/src`
- Season check: `export PATH=$HOME/.local/bin:$PATH; uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/{event,game,box_text,daily,sub,comment}_season.py ZIP YEAR`
  (years in parallel with `xargs -P4`; the real tools are in `~/.local/bin`).
- OpenSpec: `export PATH=$HOME/.nvm/versions/node/v24.16.0/bin:$PATH; openspec validate retrosheet-state-engine --strict`
- Use `grep -n` / `find`, not `ls` (RTK hook). Commit hook runs ruff-format: if a commit "fails", re-run `ruff format` and commit again.
  Never claim checks passed unless run.
- Synthetic games: `uv run --package retrosheetpy python tests/reference/synth_check.py FIRST LAST [--gcov-bin DIR] [--cov PREFIX] [--keep DIR]` (needs the real tools on PATH). Parser: `GRAMMAR=60000 ONLY_GRAMMAR=1 PD=./parse_dump python parse_fuzz.py SEED ZIP` (build `parse_dump` as in its docstring).
- All-years / e2e / sweep / gcov drivers: `tests/reference/{all_years,cli_all_years,cli_sweep,gcov_run}.py`. Decade zips (all 12 incl. 2020s with 2025):
  `Client(cache).download(resolve(Product.EVENTS_DECADE, YEAR))`; copies existed under the old session scratchpads
  `.../ea625da7-ab50-41c2-93d1-c4fc963a3e48/scratchpad/cache/events_decade/` (may be gone). Wheel: `uv build --package retrosheetpy --wheel`.
- Never `pkill -f` a pattern that matches your own shell command (it killed the session shell once).
