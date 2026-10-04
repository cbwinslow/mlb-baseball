# retrosheetpy — DOX contract

## Purpose

Standalone, Python-only Retrosheet package inside the uv workspace. Owning
change: `openspec/changes/retrosheet-state-engine/` (earlier: `pure-python-retrosheet`).

- Never import `mlb_baseball`, pandas, psycopg, or any native/compiled
  dependency. Core dependencies stay standard-library only.
- The Chadwick tools' rules live in Chadwick's C source. `retrosheetpy.cw` is a
  function-by-function Python port of it (owner decision, 2026-10-01; GPL-2.0-or-later
  source, so every ported module keeps Chadwick's copyright/licence notice). Port
  from the C; never infer a rule from output. The `cwevent` binary is a test-time
  reference only: prove equality by comparing whole seasons of output.
- Unknown record or play syntax must raise (strict) or surface as an explicit
  unsupported node. Never skip silently.
- Tests must not hit the live Retrosheet site; use small captured fixtures.
- `src/retrosheetpy/cw/` is the port, one module per C file: `parse` (parse.c), `game`/`file`/`book`/`write`
  (game.c, file.c, book.c, write side), `roster` (roster.c, league.c), `gameiter` (gameiter.c), `box`, `lint`,
  `tools` (cwtools.c), `events`/`cwgame`/`daily`/`sub`/`comment`/`cwbox`/`cwboxxml`/`cwboxsml`/`xmlwrite` (the six
  tools), `cli` (`main`, option parsing, help), `guard` (new-season guard). Console scripts `cwevent`, `cwgame`,
  `cwdaily`, `cwsub`, `cwcomment`, `cwbox`, `retrosheetpy` use Chadwick's names, so inside the venv they shadow the
  C tools: tests find the real C ones with `tests/chadwick_tool.real_tool` (never `shutil.which`; `CHADWICK_BIN`
  overrides).
- Tests: `tests/chadwick_tool.py` runs the real tools or builds them from the Chadwick sources under ASAN/UBSAN
  (inputs where the C has undefined behaviour are skipped, not compared). `tests/reference/` holds season drivers
  (`*_season.py`, `all_years.py`, `cli_*.py`), C dump programs (`*_dump.c`), and generators (`parse_grammar.py`,
  `synth_games.py`). Season drivers need the Retrosheet decade zips. CI (`retrosheetpy (parity with Chadwick)`)
  builds Chadwick at the pinned commit and runs the whole suite.
- Legacy, not part of the port: `records.py`, `play.py`, `validation.py`, `report.py`, `crosswalk.py`.
- Run: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests`

## Child DOX Index

None yet.
