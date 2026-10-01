# Handoff — `retrosheet-state-engine` (updated 2026-10-01, fifth session)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start."

## State
- Branch `feat/retrosheet-state-engine-impl` (worktree `/home/cbwinslow/workspace/mlb-pure-python`;
  never touch `/home/cbwinslow/workspace/mlb`). Not pushed yet, no PR yet. Pushing a branch and opening
  a PR is pre-authorized; merging needs the owner's "merge" per PR.
- tasks.md: sections 1, 2, 3.1-3.6 done (2019 all 164 columns match). Remaining: 4.1-4.4, 5.1-5.4.
- Engine: `packages/retrosheetpy/src/retrosheetpy/{state,outcome,fielding}.py`. `event_rows(records, strict=True)`
  yields one dict per play keyed by cwevent column names (+ `UNSUPPORTED`, `STATE_UNCERTAIN` extras; diagnostic
  mode = `strict=False`).
- Proven: **2019 full season = 0 mismatches, 0 misaligned over 192,025 plays on 99 columns**
  (`tests/implemented_fields.py` lists them). 8 fixtures also match (`tests/test_state.py`). 239 tests pass,
  ruff/format/mypy --strict clean. Rules learned are in `results.md` (keep adding to it).
- Owner direction/roadmap unchanged (see `proposal.md`): retrosheetpy = independent pure-Python replacement for
  all Chadwick tools, byte-identical; owner wants short plain replies, options + recommendation, and a
  reminder to clear context around 200k.

## Next: 2021-2025 and older decades (tasks 4.3, 4.4)
2019 and 2020 = 0 mismatches (rules in `results.md`; fixtures `auto_runner`, `auto_runner_pr`).
First held-out run of the rest (2020seve.zip holds 2020-2025; `season_report.py ZIP YEAR`):
2021 = 11 mismatches (all single odd plays: CHN202104250 `43/GDP.1X2(364)` BASE2_FORCE_FL;
CHA202108270 fate ids; SLN202104080 `PO2(E1/TH).2-H(E8)(NR)` ERR2_CD; MIN202107110 resp batter;
PHI202104040 resp pitcher after IW; MIN202108160 RUN2_AUTO_FL), 2022 = 161 (+7 errors),
2023 = 345 (+7), 2024 = 148, 2025 = 302 (+6). Errors are two-way player (Ohtani) "batter is not
in the lineup": the 2022+ rule lets the DH stay when the pitcher leaves; needs a rule + fixture.
Do 2021 first, then the Ohtani errors, then 2022-2025, then older decades. Still unproven: `BAT_LAST_ID`
when home bats first (`htbf`), pitch chars `I Q R Y K`; known open `B`/`B1S` (1976, 4.3).
Fix by rule; any rule tuned on a year means that year is no longer held out (say so in results.md).

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
