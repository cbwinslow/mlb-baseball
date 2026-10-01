# Handoff — `retrosheet-state-engine` (2026-10-01)

Start with: "Read openspec/changes/retrosheet-state-engine/HANDOFF.md and start."

## State
- `pure-python-retrosheet` (Slice A) is MERGED (PR #269). Package: `packages/retrosheetpy/`.
- `retrosheet-state-engine` plan is MERGED (PR #270): proposal, spec, design, tasks. 0 of its tasks done.
- Work in `/home/cbwinslow/workspace/mlb-pure-python` on branch `feat/retrosheet-state-engine-impl`
  (from main). Do not touch `/home/cbwinslow/workspace/mlb`. Pushing a branch and opening a PR is
  pre-authorized; merging was authorized by the owner per PR (ask again for new PRs; owner said "merge" for 269/270).

## Owner direction (the big goal)
`retrosheetpy` = free, pip-installable, pure-Python, independent replacement for ALL Chadwick tools
with byte-identical output (cwevent first, then cwgame/cwbox/cwdaily/cwcomp/cwsub), usable by other
researchers with no mlb_baseball/DB dependency; also a one-stop shop: download, organize into a
default (overridable) cache folder, parse, return plain data (pandas only as optional extra);
CLI namespace later; PyPI release last. Roadmap (4 steps) is in `proposal.md`. Step 1 = this change.
Owner wants short, plain-language replies; give options + a recommendation; remind to clear context ~200k.

## What exists
- `catalog/client/artifact` (download, SHA-256 cache; no default cache dir yet), `records.py` (reader),
  `play.py` (play parser, no game state), `coverage.py`, `crosswalk.py` + `validation.py` + `report.py`
  (text-derived fields; 0 Chadwick mismatches on 7 seasons), dev adapter `tests/chadwick_reference.py`,
  captured refs `tests/reference/{chadwick,retrosheet_csv}` with hashes. 210 package tests, ruff/format/mypy clean.
- Boundary test `tests/unit/test_retrosheetpy_boundary.py` loads the package from the tree via sys.path
  (root CI does not install it).
- Review lessons: validation must never skip a missing column (now raises); compare whole rows; report
  three-way disagreements, never pick a winner. Independent reviewers CAN run code if given Bash
  (use general-purpose agent), verify their claims.

## Next: tasks.md section 1 (scope and harness)
1.1 field table for cwevent `-f 0-96`, `-x 0-66` (from `cwevent -d`, binary at `~/.local/bin/cwevent` 0.10.0).
1.2 exclusion list. 1.3 whole-row compare in validation.py. 1.4 captures for the 8 fixtures.
Then sections 2-5 per tasks.md. 2019 first, then widen; stop and report any season that can't reach 0.
Local data: only 1950 files in `~/.pyretrosheet/data`; 2019 must be downloaded via `Client`.
`B`/`B1S` modifier (48 plays, 1976) still open (task 4.3).

## Clean-room rule (owner decision)
Reading Chadwick source (github.com/chadwickbureau/chadwick; local copy maybe at
`/home/cbwinslow/workspace/infra/chadwick`) for understanding is ALLOWED. Copying/line-by-line translating
is NOT (GPL-2.0 vs our AGPL-3.0). Write own code; prove equality by output. Record each rule learned.

## Commands
- Tests: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests -q -p no:cacheprovider`
- Lint/type: `uvx ruff check packages/retrosheetpy`, `uvx ruff format --check packages/retrosheetpy`, `uvx mypy --strict packages/retrosheetpy/src`
- OpenSpec: `export PATH=$HOME/.nvm/versions/node/v24.16.0/bin:$PATH; openspec validate retrosheet-state-engine --strict`
- Use `find`, not `ls` (RTK hook rewrites it). Never claim checks passed unless run. Delete this file before the PR.
