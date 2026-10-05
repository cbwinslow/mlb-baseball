# Handoff — `chadwickpy` is published; next is `retrosheetpy` (2026-10-05, end of sixteenth session)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start." Then read
`RETROSHEETPY-PLAN.md` in this folder (the draft plan the owner has not yet answered).

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

## Next steps (in order)
1. Get the owner's answers to the 5 decisions in `RETROSHEETPY-PLAN.md` (all have recommendations).
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
