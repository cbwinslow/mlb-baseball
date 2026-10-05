# Handoff — `retrosheetpy` build in progress (2026-10-05, end of seventeenth session; see RETROSHEETPY-DESIGN.md)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start." Then read
`RETROSHEETPY-PLAN.md` in this folder (owner APPROVED it on 2026-10-05, all five decisions as recommended: GPL-3.0-or-later, legacy parser/validation stay in mlb-baseball, cache `~/.retrosheetpy`, 0.1.0 = seasons 1910+, separate docs site per repo).

## Seventeenth session in one screen (read this first)
- **retrosheetpy is functionally built** (PR cbwinslow/retrosheetpy#6, stacked on #5; nothing merged). `Table`/`BoxScores`, shared options
  (`home game start end fields extended jobs`), several years in one Table, csv/jsonl/json/sqlite/pandas output, `fields()`, new CLI,
  README, `scripts/parity.py`, CI parity job. 187 tests pass; 288/288 outputs identical to the real C tools on 24 seasons 1910-2025;
  24 seasons combined = 3,441,587 events rows equal to C. Agreed shape: `rs.season(2010).events(...)` and `rs.events(years, ...)`.
- **chadwickpy 0.2.0 (the owner's speed-up) has real bugs**; fixes are open PRs cbwinslow/chadwickpy **#17, #18, #19** (not merged; 0.2.0 stays published):
  #17 last line of a file lost (fgets EOF), tokenizer/atoi/play-line fast paths differ from the original on odd input (44 of the differential
  tests failed on 0.2.0, 0.1.1 passed all; with the fixes 627 pass); #18 a dead worker made the parallel run print files twice with exit 0;
  #19 automatic worker count ignored CPU limits on Python 3.11/3.12 (39 workers on a 2-core limit). Owner has not yet seen/approved merging them.
- Measured speed (40 cores): 2010 `events` ~5-8 s default workers, ~90 s one core, C one core 8.7 s, C on 40 cores 0.47 s. chadwickpy is **not** faster than C per core.
- Decisions this session: keep Chadwick's names (events games daily subs comments boxscores); `home=` only in 0.1 (`team=` for either side is issue
  cbwinslow/retrosheetpy#7, 0.2); combined Table for several years (no year column; GAME_ID has it); values are plain strings (cwgame prints some
  text columns unquoted, so quoting cannot give types); default output encoding UTF-8 (`encoding="latin-1"` for Chadwick's bytes).
- Not comparable with C (documented in the README): `cwbox -S` crashes on real data; `cwbox -X` prints a `pb` attribute from uninitialised memory.
- **Next:** (1) show the owner the three chadwickpy PRs, merge on their say-so, owner approves a 0.2.1 release (release PR needs their admin bypass;
  `pypi` environment needs their click); (2) set retrosheetpy to `chadwickpy>=0.2.1`; (3) owner merges retrosheetpy #5 (blocked by a stale
  CodeRabbit CHANGES_REQUESTED review, fix already confirmed by the bot) then re-base #6 onto main; (4) docs site (MkDocs, same theme) + Retrosheet
  terms check (still unverified) + independent review pass; (5) 0.1.0 on PyPI (owner adds pending publisher + approves); (6) then in mlb-baseball
  replace `packages/retrosheetpy`, update the CI job and `/opsx:archive` this change.

## Owner direction (keep following)
- Plain, short replies. Lead with one plain sentence; options plus a recommendation; remind owner to clear context around ~200k.
- The Chadwick port stays a **function-by-function translation of the C**; never infer rules from output.
- Owner wants things automated and proper/professional: first publication, public, others may contribute, code must be safe from hostile PRs.
- Owner wants **Claude to merge PRs** (not GitHub auto-merge; that was tried and removed). Owner added `Bash(gh pr merge:*)` and `Bash(gh *)` allow rules via `/permissions`.
- Never publish to PyPI, or use admin bypass, without the owner's say-so. The `pypi` environment needs the owner's click; keep it that way.
- Both package names are kept: `chadwickpy` and `retrosheetpy` (a different, unrelated `retrosheetpy` exists on Codeberg; not on PyPI).

## State: `chadwickpy` (DONE, live)
- Repo `cbwinslow/chadwickpy` (public). Local build clone: `~/workspace/chadwickpy-build` (branch main tracks origin).
- PyPI: https://pypi.org/project/chadwickpy/ , **0.1.1** published 2026-10-05 (0.1.0 the day before). Licence **GPL-3.0-or-later** (derivative of Chadwick GPL-2.0-or-later; `NOTICE`, `COPYING-chadwick`).
- Layout mirrors Chadwick: `src/chadwickpy/` = cwlib parts (parse, game, gameiter, roster, box, book, file, write, lint, guard, xmlwrite); `src/chadwickpy/tools/` = cwtools (events, cwgame, daily, sub, comment, cwbox, cwboxsml, cwboxxml, tools, cli). Commands `cwevent cwgame cwdaily cwsub cwcomment cwbox chadwickpy`; `python -m chadwickpy TOOL`.
- Tests: 600 passed vs the real Chadwick (c685ab5), none skipped. CI: lint+types, parity on Python 3.11/3.12/3.13, clean-install check, aggregator check named `test`.
- Releases: release-please (Conventional Commit PR titles) opens a release PR; merging it tags `vX.Y.Z`; workflow builds, attaches files, then **publish waits for the owner's approval** on the `pypi` environment (PyPI trusted publishing, no token; pending publisher already registered). Versions come from tags (hatch-vcs). The release PR is bot-made and has no CI, so merging it needs the owner's admin bypass (or the owner merges it).
- Docs: https://cbwinslow.github.io/chadwickpy/ (MkDocs Material, navy/red/cream baseball theme, light+dark, logo/favicon/social card, generated tool reference from each tool's `-h`/`-d`, `llms.txt`, `llms-full.txt`, sitemap, robots.txt, last-updated dates, changelog pulled from `CHANGELOG.md`). Google Search Console verified; sitemap submitted (22 pages).
- Protections: ruleset on `main` (PR required, `test` check, linear history, squash only, thread resolution, no force-push/deletion; owner bypass), tag ruleset for `v*`, fork PRs need approval, actions allow-listed and SHA-pinned, secret scanning + push protection, Dependabot, CodeQL, private vuln reporting, Discussions on, issue templates, CODEOWNERS. CodeRabbit reviews PRs.
- Open items for the owner: delete the old PyPI API token and confirm 2FA/password; optional custom domain `chadwickpy.cloudcurio.cc` (would put robots.txt/llms.txt at the host root).
- Known small follow-ups (not blocking): the review items in the old handoff (damaged-file tests swallow errors silently; `State.copy()` copies uninitialised C fields; `qlty` dashboard issues; reviewer did not compare box/events/cwgame/daily/cwboxsml/game/file/roster/write to the C by eye); speed work (profile first, ~25x slower than C; mypyc/parallelism later; measure before changing).

## State: `mlb-baseball` repo (this worktree `/home/cbwinslow/workspace/mlb-pure-python`; never touch `/home/cbwinslow/workspace/mlb`)
- PR #282 merged earlier. `packages/retrosheetpy/` (the port + legacy client/parser) is **still there** and the CI job `retrosheetpy (parity with Chadwick)` still runs it.
- OpenSpec change `retrosheet-state-engine` is merged but **not archived**. Do `/opsx:archive` after the packages have moved out; record the move.
- A PR on branch `docs/retrosheetpy-plan` adds `RETROSHEETPY-PLAN.md` and this file (docs only). Merging in this repo needs the owner's explicit say-so (project rule).

## retrosheetpy progress (repo `cbwinslow/retrosheetpy`, local clone `~/workspace/retrosheetpy-build`)
- Done: scaffold + protections (same as chadwickpy; `pypi`/`testpypi` environments need owner approval), PR #1 downloader moved (merged), PR #5 hardening (zip caps, https-only, stricter ruff) opened.
- Owner decisions this session: do NOT point users to pyretrosheet/pychadwick in docs (facts-only comparison at most); support rows/CSV/SQLite/pandas in 0.1, Parquet + generic DB loader in 0.2; keep scope "season in, verified tables out". See RETROSHEETPY-DESIGN.md "Review additions".
- Next: cache.py + season.py + get/seasons/cache commands, then tables.py adapter (only module importing chadwickpy), export, CLI, docs site, review, 0.1.0. Still to verify before release: Retrosheet's automated-download terms.

## Next steps (in order)
1. (Done) Owner approved the plan and the 5 decisions.
2. Build `retrosheetpy` in `cbwinslow/retrosheetpy` (empty, public): copy the chadwickpy repo setup (pyproject/hatch-vcs, rulesets, workflows, docs theme, templates), move `client.py`/`catalog.py`/`artifact.py`/`errors.py` + tests, then get/cache/run-tools/export, docs, review pass, PyPI 0.1.0 (owner adds the PyPI pending publisher: project `retrosheetpy`, owner `cbwinslow`, repo `retrosheetpy`, workflow `release.yml`, environment `pypi`).
3. Then in `mlb-baseball`: replace `packages/retrosheetpy` with the published dependency(ies), update the CI job and `packages/retrosheetpy/AGENTS.md`, archive the OpenSpec change.
4. Later: profile and optimise `chadwickpy` (cheap local fixes first, parity sweep as safety net; optional mypyc wheel), custom domain.

## How merging works now (learned this session)
- `gh pr merge N -R cbwinslow/chadwickpy --squash --delete-branch` works once CI is green, `mergeStateStatus` is CLEAN and no review thread is unresolved. Check threads with GraphQL `reviewThreads`.
- CodeRabbit comments are usually worth fixing (it caught a real doc error: Chadwick reads `TEAMyyyy`/`.ROS` from the **current folder**, not the event file's folder). Fix, reply in each thread, resolve. A stale "changes requested" review can keep the PR BLOCKED; do **not** have the bot approve your own PR and then merge on it (the permission classifier rejects this as self-approval, correctly). Ask the owner to merge if blocked that way.
- Stacked PRs: a PR whose base branch gets squash-merged and deleted needs its base changed to `main` first.
- Full CI takes ~15 minutes even for docs-only PRs (the parity suite runs). Use a background wait loop (`until ...; do sleep 30; done` with `run_in_background`).
- Docs build locally: `DISABLE_MKDOCS_2_WARNING=true UV_LINK_MODE=copy uv run --group docs mkdocs build --strict` (in `~/workspace/chadwickpy-build`). Screenshots: `uvx --from playwright python shot.py` (chromium is installed in `~/.cache/ms-playwright`).

## Commands
- chadwickpy tests: `cd ~/workspace/chadwickpy-build && CHADWICK_BIN=~/.local/bin CHADWICK_SRC=~/workspace/tmp/chadwick/src uv run --with pytest pytest -q -rs -p no:cacheprovider` (~11 min). Lint/type: `uvx ruff check .`, `uvx ruff format --check .`, `uvx mypy --strict src`.
- Real Chadwick tools: `~/.local/bin` (dev commit c685ab5, reports 0.10.0); source `~/workspace/tmp/chadwick/src`. Tests find the real C tools with `tests/chadwick_tool.real_tool` (never `shutil.which`).
- Retrosheet decade zips for the season drivers: `tests/_zips.decade_zip(year, cache_dir)` (downloads `https://www.retrosheet.org/events/<decade>seve.zip`).
- OpenSpec (mlb-baseball): `export PATH=$HOME/.nvm/versions/node/v24.16.0/bin:$PATH; openspec validate retrosheet-state-engine --strict`.

## Gotchas
- **Do not run `ls`** in this environment (an RTK hook makes it hang for minutes); use `find`/`grep -n`/Read. Do not `pkill -f` a pattern that matches your own shell command (it kills the shell). Never use bare `git stash`.
- The commit hook runs ruff-format: if a commit "fails", re-run `ruff format` and commit again.
- Never claim checks passed unless they ran. Tests must not hit the live Retrosheet site (use captured fixtures or a fake `fetch`).
- The browser-use MCP tool did not work in this session; Playwright via `uvx` did.
- (17th session) The shell is **zsh**: an unquoted `$VAR` holding several words is NOT split (use a function or `${=VAR}`); this silently broke a comparison once.
- Never switch git branches in a clone while a background test/sweep reads it (it invalidated two runs). Use `git worktree add` per branch.
- Never `pkill -f` and never kill a pid you have not tied to your own process (a wrong guess killed an unrelated child of this session). Capture `$!`.
- `gh pr edit` fails on the deprecated Projects-classic GraphQL field: use `gh api -X PATCH repos/OWNER/REPO/pulls/N -f title=... -F body=@file`.
- A `kill -9` of one chadwickpy worker is the reliable way to test the pool fallback; compare the whole output with C afterwards.
