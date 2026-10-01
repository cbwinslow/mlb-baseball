# Handoff — `retrosheet-state-engine` (updated 2026-10-01, second session)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start."

## State
- Branch `feat/retrosheet-state-engine-impl` (worktree `/home/cbwinslow/workspace/mlb-pure-python`;
  never touch `/home/cbwinslow/workspace/mlb`). Not pushed yet, no PR yet. Pushing a branch and opening
  a PR is pre-authorized; merging needs the owner's "merge" per PR.
- tasks.md: sections 1, 2, 3.1-3.4 done (11 of 21 incl. 3.4). Remaining: 3.5, 3.6, 4.1-4.4, 5.1-5.4.
- Engine: `packages/retrosheetpy/src/retrosheetpy/{state,outcome,fielding}.py`. `event_rows(records, strict=True)`
  yields one dict per play keyed by cwevent column names (+ `UNSUPPORTED`, `STATE_UNCERTAIN` extras; diagnostic
  mode = `strict=False`).
- Proven: **2019 full season = 0 mismatches, 0 misaligned over 192,025 plays on 66 columns**
  (`tests/implemented_fields.py` lists them). 8 fixtures also match (`tests/test_state.py`). 239 tests pass,
  ruff/format/mypy --strict clean. Rules learned are in `results.md` (keep adding to it).
- Owner direction/roadmap unchanged (see `proposal.md`): retrosheetpy = independent pure-Python replacement for
  all Chadwick tools, byte-identical; owner wants short plain replies, options + recommendation, and a
  reminder to clear context around 200k.

## Remaining base fields (cwevent -f), in `field-table.md`
- 62-65 `BAT_PLAY_TX`, `RUN1/2/3_PLAY_TX` (fielding text for the batter/runner, e.g. `53`, `26`, `E1`, `99`)
- 75-77 `RUN1/2/3_RESP_PIT_ID` (responsible pitcher of each runner)
- 80-87 pinch-runner flags, runner removed for PR, batter removed for PH + its position
- Then extended `-x 0-66` (task 3.6): team ids, half-inning flags, scores, PA counts, base state codes, starter
  flags, on-deck/hold ids, runner lineup/fielding/origin event, responsible catcher, pitch-count splits (33-44),
  force flags, fates, 6th-10th assists, unknown-fielding/uncertain flags, count text, auto-runner flags (radj).
  Note `radj` (extra-inning runner) is not yet applied to the state: it needs handling when a half-inning starts.

## How to work (what worked)
1. Add the new columns to the engine; run the season check; read the mismatches; find the rule; record it.
2. Season check (needs `cwevent` 0.10.0 at `~/.local/bin`, dev-only):
   `uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/season_report.py ZIP YEAR --out r.json [--fields A,B]`
   ZIP for 2010s is cached at the old scratchpad (gone): re-download with
   `Client(cache).download(resolve(Product.EVENTS_DECADE, 2019))` (public Retrosheet, ~25 MB, `2010seve.zip`).
   Default fields = `tests/implemented_fields.py::IMPLEMENTED`. Add new columns there only once they match.
3. Handy helpers to recreate in the scratchpad: print the Chadwick rows for one game (call
   `ChadwickReference.events` on a game's lines), a summariser of `r.json` by field, a context printer for a
   file:line. Use `grep -n` / `find`, not `ls` (RTK hook).
4. Widen after 2019: other seasons never used for tuning (task 4.4); stop and report any season that cannot
   reach 0. Known open item: `B`/`B1S` modifier (48 plays, 1976, task 4.3). Era oddities expected (old files,
   deduced games, ladj/presadj, `99` unknown plays — already handled for fielding credit).
5. Before the PR: delete this file; update `packages/retrosheetpy/AGENTS.md`; independent reviewer (general-purpose
   agent with Bash) for clean-room check and silent skips (task 5.3); `openspec validate retrosheet-state-engine --strict`.

## Clean-room rule (owner decision)
Reading Chadwick source for understanding is ALLOWED (GPL-2.0 vs our AGPL-3.0); copying or line-by-line
translating is NOT. Write own code, prove equality by output, record each learned rule in `results.md`.

## Commands
- Tests: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests -q -p no:cacheprovider`
- Lint/type: `uvx ruff check packages/retrosheetpy`, `uvx ruff format --check packages/retrosheetpy`, `uvx mypy --strict packages/retrosheetpy/src`
- OpenSpec: `export PATH=$HOME/.nvm/versions/node/v24.16.0/bin:$PATH; openspec validate retrosheet-state-engine --strict`
- Commit hook runs ruff-format: if a commit "fails", re-run `ruff format` and commit again. Never claim checks passed unless run.
