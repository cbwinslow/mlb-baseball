# Handoff — `retrosheet-state-engine` (updated 2026-10-01, third session)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start."

## State
- Branch `feat/retrosheet-state-engine-impl` (worktree `/home/cbwinslow/workspace/mlb-pure-python`;
  never touch `/home/cbwinslow/workspace/mlb`). Not pushed yet, no PR yet. Pushing a branch and opening
  a PR is pre-authorized; merging needs the owner's "merge" per PR.
- tasks.md: sections 1, 2, 3.1-3.5 done. Remaining: 3.6, 4.1-4.4, 5.1-5.4.
- Engine: `packages/retrosheetpy/src/retrosheetpy/{state,outcome,fielding}.py`. `event_rows(records, strict=True)`
  yields one dict per play keyed by cwevent column names (+ `UNSUPPORTED`, `STATE_UNCERTAIN` extras; diagnostic
  mode = `strict=False`).
- Proven: **2019 full season = 0 mismatches, 0 misaligned over 192,025 plays on 99 columns**
  (`tests/implemented_fields.py` lists them). 8 fixtures also match (`tests/test_state.py`). 239 tests pass,
  ruff/format/mypy --strict clean. Rules learned are in `results.md` (keep adding to it).
- Owner direction/roadmap unchanged (see `proposal.md`): retrosheetpy = independent pure-Python replacement for
  all Chadwick tools, byte-identical; owner wants short plain replies, options + recommendation, and a
  reminder to clear context around 200k.

## Remaining: extended fields (task 3.6, `cwevent -x 0-66`), see `field-table.md`
All base fields (-f 0-96) now match, including text-derived ones (EVENT_CD, SB/CS/PK flags,
batted ball; merged into rows via `crosswalk.chadwick_fields`). Still to build, in one new
module fed by the per-game `pending` list in `event_rows` (many need look-ahead per half-inning):
team ids/BAT_LAST_ID, INN_NEW/END_FL, START_BAT/FLD_SCORE_CT, INN_RUNS_CT, GAME_PA_CT, INN_PA_CT,
PA_NEW/TRUNC_FL, START/END_BASES_CD, BAT/RESP_BAT/PIT/RESP_PIT_START_FL, BAT_ON_DECK/IN_HOLD_ID,
RUN1-3_FLD_CD/LINEUP_CD/ORIGIN_EVENT_ID/RESP_CAT_ID, pitch-count splits (33-44, from PITCH_SEQ_TX),
FLD_ID, BASE2-4_FORCE_FL, BAT_SAFE_ERR_FL, BAT/RUN1-3_FATE_ID, FATE_RUNS_CT, ASS6-10_FLD_CD,
UNKNOWN_OUT_EXC_FL, UNCERTAIN_PLAY_EXC_FL, COUNT_TX, RUN1-3_AUTO_FL (`radj` extra-inning runner is
not yet applied to the state: handle when a half-inning starts). Add each to
`tests/implemented_fields.py` only once it matches. Runner state: `Runner(player_id, resp_pit)`.

## How to work (what worked)
1. Add the new columns to the engine; run the season check; read the mismatches; find the rule; record it.
2. Season check (needs `cwevent` 0.10.0 at `~/.local/bin`, dev-only):
   `uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/season_report.py ZIP YEAR --out r.json [--fields A,B]`
   ZIP for 2010s (scratchpad cache is session-specific): re-download with
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
