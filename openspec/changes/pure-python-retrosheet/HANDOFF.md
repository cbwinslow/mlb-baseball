# Handoff — `pure-python-retrosheet` (updated 2026-10-01, after section 3)

12 of 29 tasks done (sections 1-3). Next: finish review round 2, then section 4.

## Where to work
- **Worktree:** `/home/cbwinslow/workspace/mlb-pure-python`, branch
  `feat/pure-python-retrosheet`. Work ONLY here. Do not touch
  `/home/cbwinslow/workspace/mlb` (another session, `raw-source-tieout`).
- **Nothing is pushed yet.** Pushing the branch and opening the PR is
  pre-authorized; merging, force-push, branch deletion are not.
- Owner wants short, plain-language replies (see `CLAUDE.md`).

## What exists (package `retrosheetpy`, `packages/retrosheetpy/`)
- Name decided: distribution and import `retrosheetpy` (free on PyPI; `retropy`
  and `pyretrosheet` are taken). Recorded in `design.md` D9.
- `catalog.py`: `Product`, `Resource`, `resolve()` — official URLs.
- `client.py`: `Client` (cached, SHA-256 verified download, injectable `fetch`),
  `iter_zip_members` (rejects traversal/corrupt data, guarded streams).
- `records.py`: lossless line reader `iter_records` / `read_event_file` /
  `iter_event_zip`; typed records; strict vs diagnostic mode; `RecordStats`.
  `com`/`info` use a free-text fallback because ~27 real lines have irregular
  quoting; structured records (play/start/sub/id/data) stay strict.
- `errors.py`, `artifact.py`, `py.typed`, README (Retrosheet attribution),
  `API.md`, `AGENTS.md` (listed in root `AGENTS.md`).
- Tests: 77 pass; fixtures are one real game per era in `tests/fixtures/events/`.

## Evidence so far
- Real corpus (postseason, All-Star, Negro League, 1910s zips): 2,882,270 lines
  parse in STRICT mode with zero unsupported. Record types seen: id, version,
  info, start, sub, play, data, com, badj, ladj, presadj.
- Live download verified against retrosheet.org (4 files, cache reuse works).
- Wheel builds, installs with zero dependencies, tests pass on Python 3.11.
- `ruff`, `ruff format`, `mypy --strict` clean on the package.
- `openspec validate pure-python-retrosheet --strict` passes. The CLI is at
  `~/.nvm/versions/node/v24.16.0/bin/openspec` (put it on PATH).
- Root unit suite: 1034 pass; 2 unrelated failures (`openpyxl` not installed
  here: `test_export_health_check`, `test_excel_row_limit_guard`).
- Review round 1 (independent agent) found 7 real issues; all fixed in
  `34d922e`.

## Commands
- Package tests: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests -q -p no:cacheprovider`
- Root tests need dev extra: `uv run --extra dev python -m pytest tests/unit packages -q -p no:cacheprovider`
- Lint/type: `uvx ruff check packages/retrosheetpy`, `uvx ruff format --check packages/retrosheetpy`, `uvx mypy --strict packages/retrosheetpy/src`
- NOTE: in this shell `ls` is rewritten by an RTK hook and can print wrong
  counts; use `find` for file counts.
- Downloaded real archives for local experiments are in the session scratchpad
  (`.../scratchpad/dl`, may be gone); re-download with `Client` if needed.
  Also real event files exist at `~/.pyretrosheet/data` (1950) and
  `/tmp/retrosheet_event_pbp_*` (2000s).

## Next steps
1. **Review round 2** (agreed in principle, not yet run): independent read-only
   review of ONLY commit `34d922e`'s changes (client.py, records.py). Fix real
   findings, then continue.
2. **Section 4** (tasks 4.1-4.5): play-syntax parser, no game-state logic, raw
   tokens preserved, structured `ParseError` with stage/location. Write from
   Retrosheet docs (retrosheet.org/eventfile.htm); do NOT copy Chadwick code.
   Test first. 4.5 needs a parse-coverage run over: modern season, early/dead-ball
   season, deduced season, postseason, Negro League; record every unsupported
   syntax family. Reader speed is ~70k lines/s (measure before optimizing).
3. Sections 5-7: Chadwick 0.10.0 differential harness (dev/test only, skip if
   absent; Chadwick is at `~/.local/bin/cwevent`), Retrosheet CSV crosswalk,
   coverage report, boundary proof (no production change), final verification,
   Slice B go/no-go note.

## Rules to keep
- Never claim tests/lint/type checks passed unless they actually ran.
- Package must never import `mlb_baseball`, pandas, psycopg, or native code.
- Unknown record/play syntax must raise (strict) or surface as an explicit
  unsupported node; never skipped.
- Tick `tasks.md` boxes only when behavior is fully done.
- Known, accepted limits: a bad HTML response for a plain-text product would be
  cached (hash recorded); no download size cap.
- This handoff file is a one-off note; consider deleting it before the PR.
