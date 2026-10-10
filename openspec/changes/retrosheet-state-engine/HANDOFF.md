# Handoff — `retrosheetpy` / `chadwickpy` (2026-10-10, end of eighteenth session)

Written for another AI agent (Gemini/agy) taking over. Nothing is running in the background; the only
open work is listed under "What is open right now". The previous handoff (2026-10-05) is replaced by this
file; its still-useful rules are kept under "Rules".

## Where everything lives (do not confuse these)

| What | Where |
| --- | --- |
| **chadwickpy** (pure-Python port of the Chadwick C tools) | GitHub `cbwinslow/chadwickpy`. Local: `~/workspace/chadwickpy-openspec` (on `main`; use this one), `~/workspace/chadwickpy-build` (stale branch, ignore) |
| **retrosheetpy** (downloads Retrosheet seasons, runs chadwickpy, gives tables/CSV/SQLite/pandas) | GitHub `cbwinslow/retrosheetpy`. Local clones are git worktrees of `~/workspace/retrosheetpy-build`: `-accept` (branch `test/acceptance`, PR #12), `-readme` (branch `chore/chadwickpy-0-4`, PR #13), `-openspec` (branch `chore/openspec`, holds the OpenSpec change), `-rebase` (leftover, safe to remove), `-build` (branch `feat/kinds`, leftover) |
| **Old in-repo copy** | `~/workspace/mlb/packages/retrosheetpy/` inside the `mlb-baseball` repo. It is the version to be *replaced* by the published packages. Do not develop here. |
| OpenSpec change for the new repo | `~/workspace/retrosheetpy-openspec/openspec/changes/acceptance-and-release/` (`proposal.md`, `design.md`, `tasks.md`) |
| OpenSpec change in mlb-baseball | `~/workspace/mlb/openspec/changes/retrosheet-state-engine/` (this folder; merged, **not archived**) |
| Design/plan docs | `RETROSHEETPY-PLAN.md`, `RETROSHEETPY-DESIGN.md` in this folder |

Use `git worktree add ../<name> -b <branch> origin/main` for each new branch. Never switch branches inside
an existing clone while a test run reads it.

## State of the world

**chadwickpy — finished.** v0.4.0 on PyPI (follows Chadwick 0.11.0), docs at https://cbwinslow.github.io/chadwickpy/.
No open PRs, no open issues, no unchecked OpenSpec tasks (last change archived). Breaking change in 0.4.0:
the quiet switch is `-Q` (`-q` is rejected, like the C tools) and there is a new `-D dir` option. Tests there
need the real C tools (see Commands).

**retrosheetpy — functionally complete, not on PyPI.** GitHub release `v1.1.0` exists (tagged
2026-10-10) but PyPI returns 404: the `Release` workflow run is **waiting for the owner to approve the
`pypi` environment**. Do not approve it, do not use admin bypass, do not publish. Only the owner does that.
`main` has: downloader/cache, six tables (`events games daily subs comments boxscores`), CSV/JSONL/JSON/SQLite/pandas
output, several seasons in one call, six file kinds (`kind=` regular, postseason, allstar, negro, negro_box, box),
CLI. README currently (correctly) says "not released yet".

## What is open right now

1. **PR #13** `fix: follow chadwickpy 0.4.0 (Chadwick 0.11.0)` — `chore/chadwickpy-0-4`. **All checks green,
   mergeable (CLEAN).** retrosheetpy passed `-q` to chadwickpy, which 0.4.0 rejects (48 tests failed). The PR
   changes it to `-Q`, requires `chadwickpy>=0.4.0` (relocked), updates column counts (games 183, subs 26;
   events 164, daily 154 unchanged), makes the CI parity job build Chadwick `v0.11.0`, and removes a leftover
   CI pin to an old chadwickpy commit. **Merge it first.** I was blocked from merging it myself by the
   permission classifier ("merge without review"); the owner must merge it or allow `gh pr merge`.
2. **PR #12** `test: acceptance suite mapped to the project invariants` — `test/acceptance`. All checks
   green. Blocked only by a stale CodeRabbit `CHANGES_REQUESTED` review; all four of its comments are fixed in
   the last push (values compared per format, full kind x table x format matrix, `sys.executable`, repeat steps
   in `docs/live-check.md`). Its four review threads are still open: reply "fixed in <sha>" and resolve them
   (GraphQL `addPullRequestReviewThreadReply` + `resolveReviewThread`), then the owner dismisses the review and
   merges. Adds `tests/acceptance/` (traceability map invariants 1-7 -> tests, checked by a test),
   `docs/live-check.md` (live run of every kind plus the `gameinfo.csv` cross-check), and one real fix: a tool
   that cannot start now raises `ToolError` instead of a bare `FileNotFoundError` (`runner.py`).
   After #13 merges, check #12 for a conflict: both edit `src/retrosheetpy/runner.py` (#13 line 83, the `-Q`
   switch; #12 the `Popen` call further down), so expect none or a trivial one; rebase if GitHub reports it.
3. **The `Release` workflow run `38007548207`** is pending the owner's `pypi` approval (see above).

## Remaining plan (from `acceptance-and-release/tasks.md`, with status)

- 1.x Land the stack: #5, #6, #8 are merged. 1.3 "main passes parity + mypy + ruff": main CI was green on 2026-10-10.
- 2.1-2.3 Acceptance tests: **done in PR #12.**
- 3.1 One live run per file kind, recorded in `docs/`: **done in PR #12** (`docs/live-check.md`).
  Result: all kinds work; `box` 1901 `boxscores` fails because the C `cwbox` also crashes on 1901-1907
  (documented in README "Known problems"). 2010 and 1920 matched `gameinfo.csv` on 13 fields with no mismatch.
- 3.2 "Fix README status text": **deliberately not done.** It says "not released yet" which stays true until
  PyPI publishes. Change it in the same PR that follows the first PyPI publish; add a `pip install retrosheetpy`
  line then. Also tick the OpenSpec `tasks.md` boxes (they are all still `[ ]`) in the `chore/openspec` branch
  and then `/opsx:archive` the change.
- 3.3 Full suite, ruff, mypy, inspect diff: re-run after #12 and #13 are merged.

After that, in this order (nothing started):
1. **Docs site** for retrosheetpy (MkDocs Material, copy chadwickpy's setup: navy/red/cream baseball theme,
   `mkdocs build --strict`, `llms.txt`, sitemap; see `~/workspace/chadwickpy-openspec/docs` and `mkdocs.yml`).
2. **Verify Retrosheet's terms for automated downloads** (still unverified; the package prints the data-use
   notice on first download). Read https://www.retrosheet.org/notice.txt and their site's robots/terms and
   record the finding in the docs; do not assume.
3. **Independent review pass** (e.g. `/code-review`), fix findings.
4. **PyPI 0.1.0/1.1.0 publication**: the owner adds the PyPI pending publisher (project `retrosheetpy`, owner
   `cbwinslow`, repo `retrosheetpy`, workflow `release.yml`, environment `pypi`) and approves the `pypi` run.
   Check whether v1.1.0's publish step already has a pending approval before creating anything new.
5. **In `mlb-baseball`**: replace `packages/retrosheetpy` with the published dependencies, update the CI job
   `retrosheetpy (parity with Chadwick)` and `packages/retrosheetpy/AGENTS.md`, then `/opsx:archive`
   `retrosheet-state-engine` and record the move. Merging in that repo needs the owner's explicit say-so.
6. Later: issue `cbwinslow/retrosheetpy#7` (`team=` filter for either side, 0.2); Parquet and generic DB loader
   (0.2); chadwickpy speed work (profile first; it is ~25x slower than C per core, measure before changing);
   optional custom domain.

## Rules from the owner (keep following)

- **Plain, short replies.** Lead with one plain sentence; at most two options plus a recommendation; the owner
  is not a specialist. (Also in `/home/cbwinslow/workspace/mlb/CLAUDE.md`.)
- The Chadwick port stays a **function-by-function translation of the C**; never infer a rule from output.
- Never publish to PyPI, use admin bypass, or approve the `pypi` environment without the owner.
- The owner wants the agent to merge PRs (not GitHub auto-merge) once CI is green and review threads are
  resolved, but the permission classifier has blocked `gh pr merge` and other outward writes (force-push,
  thread replies) until the owner approved each in `/permissions`. If blocked, stop and ask; do not work around.
  A stale bot "changes requested" review blocks merging; never have a bot approve your own PR. Ask the owner
  to dismiss it.
- Never claim tests/lint/types passed unless they ran. Tests must not hit the live Retrosheet site (fakes in
  `tests/fake_season.py`; the live run is manual and recorded, not automated).
- Never add a Retrosheet data file to the repo (an acceptance test enforces it).
- Both package names stay: `chadwickpy`, `retrosheetpy` (a different, unrelated `retrosheetpy` exists on
  Codeberg; it is not on PyPI). Do not point users to pyretrosheet/pychadwick in docs.
- Licence GPL-3.0-or-later (derivative of Chadwick GPL-2.0-or-later); keep `NOTICE` and the Retrosheet credit.
- In `mlb-baseball`: OpenSpec workflow (`/opsx:*`), ADRs in `docs/DECISIONS.md`, changelog entry for
  infrastructure work. Remind the owner to clear context around ~200k tokens.

## Commands

- retrosheetpy tests (fast, uses fakes): `cd ~/workspace/retrosheetpy-accept && uv run --with pytest pytest -q -p no:cacheprovider`
  (≈ 190-240 pass, 56 skipped locally: the skipped ones compare with the real C tools).
- With the real C tools (parity; CI runs this and **fails the job on any skip**): build Chadwick `v0.11.0`
  (`git clone https://github.com/chadwickbureau/chadwick.git; git checkout v0.11.0; autoreconf -i; ./configure --prefix=$HOME/chadwick-parity-install; make; make install`),
  then `CHADWICK_BIN=$HOME/chadwick-parity-install/bin uv run --with pytest --with pandas pytest -q -rs -p no:cacheprovider`.
  The C tools in `~/.local/bin` and `~/workspace/tmp/chadwick` are the **old** commit `c685ab5` and will not
  match chadwickpy 0.4.0.
- Lint/types: `uvx ruff check .`, `uvx ruff format --check .`, `uv run --with mypy mypy --strict src`
  (plain `uvx mypy` fails with a missing-import note for chadwickpy: run it in the project env).
- Live check: see `docs/live-check.md` ("How to repeat it"); cache location override is `RETROSHEETPY_HOME`.
- Cross-check with Retrosheet's own CSV: `RETROSHEETPY_HOME=<cache> uv run python scripts/crosscheck.py 2010 1920`.
- Tests that need the shared fakes import `fake_season` (it lives in `tests/`; `tests/acceptance/conftest.py`
  adds the path).
- CI waits: a full run takes ~15 min for a docs-only PR. Use a background wait loop, not repeated polling.
- chadwickpy docs build: `DISABLE_MKDOCS_2_WARNING=true UV_LINK_MODE=copy uv run --group docs mkdocs build --strict`.

## Gotchas

- **Do not run bare `ls`** in the owner's environment (an RTK hook can make it hang or rewrite output); use
  `find`/`grep -n`/Read. `gh pr view --web` fails under the hook; use `xdg-open <url>`.
- zsh: an unquoted `$VAR` holding several words is not split. Do not `pkill -f` a pattern; do not kill pids you
  did not start. Never use bare `git stash`.
- The commit hook runs ruff-format: if a commit "fails", re-run `ruff format` and commit again.
- `gh pr edit` fails on a deprecated Projects-classic field: use `gh api -X PATCH repos/OWNER/REPO/pulls/N -f title=... -F body=@file`.
- Stacked PRs: a PR whose base was squash-merged and deleted needs its base changed to `main`. A rebase after a
  squash merge shows the already-merged commits; `git rebase --skip` drops them.
- Retrosheet's Chadwick-style outputs: the XML box output has no `<?xml` header; `cwbox -S` crashes on real
  data and `cwbox -X` prints a `pb` attribute from uninitialised memory (not compared with C; documented).
- `cwgame` and `cwsub` gained columns in Chadwick 0.11.0 (183 and 26); anything that hard-codes counts breaks
  when chadwickpy changes. The CI parity job will fail loudly if the C tools and chadwickpy disagree.
- The full mlb-baseball repo has unrelated uncommitted files (e.g. `openspec/changes/streamline-core-gold-direction/conform-design.md`).
  They are the owner's; do not touch or commit them.
- Speed (40 cores): 2010 `events` ≈ 5-8 s on default workers, ~90 s on one core; C is 8.7 s on one core. Say so
  honestly in docs; do not promise C speed.

## Decisions already made (do not reopen)

Keep Chadwick's names (events games daily subs comments boxscores); `home=` only in 0.1 (`team=` is issue #7);
several years give one combined Table (no year column; `GAME_ID` contains the year); values are plain strings;
default output encoding UTF-8 (`encoding="latin-1"` gives Chadwick's bytes); cache `~/.retrosheetpy`
(override `RETROSHEETPY_HOME`); parquet and generic DB loader are 0.2; legacy parser/validation stay in
mlb-baseball; separate docs site per repo.
