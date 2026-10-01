# Handoff — `pure-python-retrosheet` (updated 2026-10-01, after section 4)

17 of 29 tasks done (sections 1-4). Next: section 5.
Start with: "Read openspec/changes/pure-python-retrosheet/HANDOFF.md and start."

## Where to work
- **Worktree:** `/home/cbwinslow/workspace/mlb-pure-python`, branch
  `feat/pure-python-retrosheet`. Work ONLY here. Do not touch
  `/home/cbwinslow/workspace/mlb` (another session, `raw-source-tieout`).
- **Nothing is pushed yet.** Pushing the branch and opening the PR is
  pre-authorized; merging, force-push, branch deletion are not.
- Owner wants short, plain-language replies (see `CLAUDE.md`). Remind the owner
  to clear context at about 200k tokens used.

## What exists (package `retrosheetpy`, `packages/retrosheetpy/`)
- Name: distribution and import `retrosheetpy` (design.md D9).
- `catalog.py`, `client.py`, `artifact.py`: official URL resolution, cached
  SHA-256 verified download (`Client`, injectable `fetch`), safe zip reading.
- `records.py`: lossless line reader (`iter_records`, `read_event_file`,
  `iter_event_zip`), typed records, strict vs diagnostic mode, `RecordStats`.
  `com`/`info` use a free-text fallback (27 real lines have odd quoting).
- `play.py`: play-syntax parser `parse_play(event, strict=True)` ->
  `Play(events, modifiers, advances, markers)`; `rebuild()` equals input;
  `ParseError` has stage/token/offset (real positions). No game state.
  Built from retrosheet.org/eventfile.htm; no Chadwick code copied.
- `coverage.py`: `PlayCoverage` (counts plays, groups unsupported by family;
  `to_dict()` is the base for the task 5.4 report).
- 168 tests pass. `ruff`, `ruff format`, `mypy --strict` clean.
- `parse-coverage.md` (this folder) records task 4.5: 2,001,711 real plays,
  36 unsupported (all rare modifier oddities), modern season measured = 2019.

## Reviews done
- Round 1 (client/records): 7 issues fixed. Round 2 (fixes): 1 bug + 2 minor
  fixed. Play-parser review: offsets, recursion, permissive regexes fixed, fuzz
  test added. Independent reviewer agents could NOT run code (read-only);
  verify their claims by running inputs before fixing.

## Known limits (accepted)
- Bad HTML response for a plain-text product would be cached (hash recorded).
- No download size cap. Reader speed about 70k lines/s (not optimized).
- Modern-era coverage is one season (2019). 1950 sample was 17 local files.
- `BF` modifier and `(n/TH)` params are supported though not in Retrosheet's
  published list (observed in source; meaning not interpreted).

## Commands
- Package tests: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests -q -p no:cacheprovider`
- Root tests: `uv run --extra dev python -m pytest tests/unit packages -q -p no:cacheprovider`
  (2 unrelated failures here: `openpyxl` not installed.)
- Lint/type: `uvx ruff check packages/retrosheetpy`, `uvx ruff format --check packages/retrosheetpy`, `uvx mypy --strict packages/retrosheetpy/src`
- OpenSpec: `export PATH=$HOME/.nvm/versions/node/v24.16.0/bin:$PATH; openspec validate pure-python-retrosheet --strict`
- `ls` is rewritten by an RTK hook and can print wrong counts; use `find`.
- Local real data may be gone (temp dirs get cleaned). Re-download with
  `Client(...).download(resolve(Product.X, season))`. Official docs copy:
  retrosheet.org/eventfile.htm. Chadwick 0.10.0 is at `~/.local/bin/cwevent`.

## Next steps (tasks.md section 5-7)
5.1 Dev/test-only `ChadwickReference` adapter: find `cwevent`/`cwgame` on PATH,
    record exact version, skip cleanly if absent (not a runtime requirement).
5.2 Capture Chadwick 0.10.0 reference output for a small fixture set so normal
    CI needs no native tools. Reuse the fixture games in `tests/fixtures/events/`
    (Chadwick needs a TEAMyyyy file + roster alongside; check how the existing
    `mlb_baseball/connectors/retrosheet_event.py` and its `.dox.md` call it; read
    only, do not edit).
5.3 Add Retrosheet's official parsed-play crosswalk as test metadata and compare
    fields derivable without a state engine (e.g. event type, hit location,
    modifiers) against the yearly CSV `plays` file. Official crosswalk is on
    retrosheet.org (find it; do not guess field mappings).
5.4 Machine-readable coverage report (records parsed, plays parsed,
    unsupported families, reference mismatches). Consider a small CLI/function.
6.1-6.3 Boundary proof: no production dependency or connector switch; write a
    contract test or documented spike showing mlb_baseball could consume
    Artifact metadata + parsed record streams; confirm current connectors
    unchanged (`git diff origin/main -- mlb_baseball` should be empty).
7.1-7.5 Final verification: package tests/ruff/format/mypy, root tests, strict
    OpenSpec validate for the change and all specs, final diff review for native
    deps / copied Chadwick text / silent unsupported handling / mlb_baseball
    coupling, and the Slice B go/no-go note (based on parse coverage and the
    measured effort left for the state engine).
Then: push branch, open PR (pre-authorized), run an independent review of
section 5 code before the PR if budget allows.

## Rules to keep
- Never claim tests/lint/type checks passed unless they actually ran.
- Package must never import `mlb_baseball`, pandas, psycopg, or native code.
- Unknown record/play syntax must raise (strict) or surface as explicit
  unsupported nodes; never skipped.
- Tick `tasks.md` only when behavior is fully done. If three sources disagree
  (Chadwick, CSV, our parser) report the discrepancy; never silently pick one.
- This handoff file is a one-off note; consider deleting it before the PR.
