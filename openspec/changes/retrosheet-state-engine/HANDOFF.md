# Handoff — `retrosheet-state-engine` (updated 2026-10-02, twelfth session)

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
  Console scripts (pyproject): `cwevent-py`, `cwgame-py`, `cwdaily-py`, `cwsub-py`, `cwcomment-py`,
  `cwbox-py` (the `-py` suffix is deliberate: tests find the real C tools with `shutil.which`,
  so the port must never shadow them). `python -m retrosheetpy.cw TOOL ...` also works.
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
3. Proof is against Chadwick 0.10.0 only; record version/commit in `results.md`.
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
- Command namespace: Chadwick has exactly six tools; all ported as `cwevent-py` ... `cwbox-py`, plus the
  umbrella `retrosheetpy cwevent ...` (`cli.main_umbrella`, also `python -m retrosheetpy.cw`).
- Owner question "should we fix Chadwick's bugs?": recommendation given = no. Match the C wherever its
  behaviour is defined; only where it crashes or reads garbage does the port differ (ValueError / defined
  value), documented above. Not yet confirmed by the owner.

## Next steps (in order)
1. Full suite (802 passed), ruff, format, mypy --strict were clean at the last commit; re-run before the PR.
2. (done) write side and mutators.
3. Value check done earlier (nothing else is a pure-Python, Chadwick-identical, pip-installable
   replacement; quick search, PyPI pages not opened directly).
4. Close-out: rewrite `tasks.md`/`results.md`/`proposal.md`/`design.md` for the port approach
   (they still describe the old infer-from-output plan; results.md says "No Chadwick code was
   copied", which is obsolete), update `packages/retrosheetpy/AGENTS.md` (its owning-change path
   says `pure-python-retrosheet`; add the `cw/` map, console scripts, harness notes) and
   `README.md`/`API.md`; record the Chadwick version in `results.md`; an independent reviewer
   (general-purpose agent with Bash) checks notices, deviations and silent skips;
   `openspec validate retrosheet-state-engine --strict`; delete this file before the PR; push, open PR.

## Commands
- Tests: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests -q -p no:cacheprovider`
  (about 10 minutes; the CLI/event/game/box differential files alone take about 3 minutes).
- Lint/type: `uvx ruff check packages/retrosheetpy`, `uvx ruff format --check packages/retrosheetpy`, `uvx mypy --strict packages/retrosheetpy/src`
- Season check: `export PATH=$HOME/.local/bin:$PATH; uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/{event,game,box_text,daily,sub,comment}_season.py ZIP YEAR`
  (years in parallel with `xargs -P4`; the real tools are in `~/.local/bin`).
- OpenSpec: `export PATH=$HOME/.nvm/versions/node/v24.16.0/bin:$PATH; openspec validate retrosheet-state-engine --strict`
- Use `grep -n` / `find`, not `ls` (RTK hook). Commit hook runs ruff-format: if a commit "fails", re-run `ruff format` and commit again.
  Never claim checks passed unless run.
