# Handoff — `retrosheet-state-engine` (updated 2026-10-01, sixth session)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start."

## State
- Branch `feat/retrosheet-state-engine-impl` (worktree `/home/cbwinslow/workspace/mlb-pure-python`;
  never touch `/home/cbwinslow/workspace/mlb`). Not pushed yet, no PR yet. Pushing a branch and opening
  a PR is pre-authorized; merging needs the owner's "merge" per PR.
- tasks.md: sections 1, 2, 3.1-3.6 done. 4.1-4.2 done (2019-2025 = 0 mismatches). Remaining: 4.3, 4.4, 5.1-5.4.
- Engine: `packages/retrosheetpy/src/retrosheetpy/{state,outcome,fielding}.py`. `event_rows(records, strict=True)`
  yields one dict per play keyed by cwevent column names (+ `UNSUPPORTED`, `STATE_UNCERTAIN` extras; diagnostic
  mode = `strict=False`).
- Proven: **2019 full season = 0 mismatches, 0 misaligned over 192,025 plays on 99 columns**
  (`tests/implemented_fields.py` lists them). 8 fixtures also match (`tests/test_state.py`). 239 tests pass,
  ruff/format/mypy --strict clean. Rules learned are in `results.md` (keep adding to it).
- Owner direction/roadmap unchanged (see `proposal.md`): retrosheetpy = independent pure-Python replacement for
  all Chadwick tools, byte-identical; owner wants short plain replies, options + recommendation, and a
  reminder to clear context around 200k.

## Next: older decades (tasks 4.3, 4.4)
2019-2025 = 0 mismatches (2025: 189,311 plays). All seven seasons are now tuned (none held out); rules in
`results.md`. Chadwick source (`~/workspace/tmp/chadwick/src/cwlib/{gameiter,parse}.c`) may be read for understanding:
it explained the runner/pitcher handoff exactly (`_advance_runners`, `_charged_base`) and two parse quirks.
Next: run the older decades (`2010seve.zip` 2010-2018, `2000seve.zip`, ... back to 1910s and earlier files; zips are
public Retrosheet `Product.EVENTS_DECADE`) with `season_report.py ZIP YEAR`; fix by rule; known open `B`/`B1S` (1976).
Still unproven: `BAT_LAST_ID` when home bats first (`htbf`), pitch chars `I Q R Y K`. Expect old-file oddities
(deduced games, `ladj`/`presadj`, `99` plays, 1-line files, missing info records). Stop and report any season that
cannot reach 0. After the decades: 4.4 report, then 5.1-5.4 (below).

## How to work (what worked)
1. Add the new columns to the engine; run the season check; read the mismatches; find the rule; record it.
2. Season check (needs `cwevent` 0.10.0 at `~/.local/bin`, dev-only):
   `uv run --package retrosheetpy python packages/retrosheetpy/tests/reference/season_report.py ZIP YEAR --out r.json [--fields A,B]`
   ZIP (scratchpad cache is session-specific): re-download with
   `Client(cache).download(resolve(Product.EVENTS_DECADE, YEAR))` (public Retrosheet, `2010seve.zip`, `2020seve.zip`, ...).
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
