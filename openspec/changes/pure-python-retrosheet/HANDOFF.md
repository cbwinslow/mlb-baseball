# Handoff — start of `pure-python-retrosheet` (2026-10-01)

Nothing is built yet. This note gets a fresh session started fast.

## Where to work
- **Worktree:** `/home/cbwinslow/workspace/mlb-pure-python`
  (branch `feat/pure-python-retrosheet`, cut from `origin/main`).
  Work ONLY here. Do not touch `/home/cbwinslow/workspace/mlb`: another
  session is using it for the `raw-source-tieout` change (uncommitted edits
  to `mlb_baseball/tieout*.py` and related SQL/tests).
- **Same repo, separate package.** The new code lives in a new folder under
  `packages/` (like the existing `packages/mlb-research`) and is added to the
  existing uv workspace in the root `pyproject.toml` (`[tool.uv.workspace]`).
  It must never import `mlb_baseball` and must not need PostgreSQL, pandas,
  a compiler, or the Chadwick programs. It can be published on its own later.

## What to read first (in this order)
1. `openspec/project.md` (constitution), root `AGENTS.md`, `CLAUDE.md`
   (owner wants short, plain-language replies).
2. This change: `proposal.md`, `design.md`, `research.md`, `tasks.md`
   (all in this folder), then `specs/`.
3. `packages/mlb-research/pyproject.toml` as the model for a workspace
   package; `mlb_baseball/connectors/` Retrosheet connector and its DOX
   sidecars for how the current code uses Chadwick (read, don't edit).

## The task, in plain words
Today our raw-event and box-score loading needs the Chadwick C programs
(`cwevent`, `cwgame`, `cwbox`) installed on the computer. This change builds
a Python-only package that can find and download official Retrosheet files,
read their lines without losing any text, and break each play description
into parts. It also builds a test harness that compares its answers with
Chadwick 0.10.0 and with Retrosheet's own parsed CSVs. This slice does NOT
switch the production connectors away from Chadwick.

## Order of work (from `tasks.md`, 29 tasks, none done)
1. Section 1: pick the package name (check PyPI; do not reuse `pyretrosheet`),
   scaffold it, README/attribution, small public API note.
2. Section 2: official file client (typed Artifact model, safe cached
   download, zip handling; tests use tiny captured archives, never live web).
3. Section 3: lossless record reader (id/info/start/sub/play/data/com...).
   Unknown record types must fail loudly in strict mode, never be skipped.
4. Section 4: play-syntax parser, no game-state logic, raw tokens preserved.
   Do not copy Chadwick code (4.4).
5. Section 5: comparison harness vs Chadwick 0.10.0 and Retrosheet CSVs.
6. Sections 6-7: boundary proof, checks, Slice B go/no-go note.
Use test-first for behaviour (the tasks say so). Tick `tasks.md` as you go.

## Rules that matter here
- One change = one branch = one PR. Commit on `feat/pure-python-retrosheet`;
  pushing the branch and opening the PR is pre-authorized. Do not merge,
  force-push, or delete branches.
- Chadwick on this machine is 0.10.0 (read-only use for reference output).
- Never claim tests/lint/type checks passed unless they actually ran.
- Don't use the shared production database for this change; it needs none.
- Update the nearest DOX/AGENTS file if you add a new directory with its own
  contract (the new package folder should get a short `AGENTS.md`).

## Suggested first step
Section 1.1 and 1.2: decide the package name, scaffold the empty package,
confirm `uv sync` and a trivial import test work in the worktree, commit.
