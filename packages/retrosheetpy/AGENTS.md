# retrosheetpy — DOX contract

## Purpose

Standalone, Python-only Retrosheet package inside the uv workspace. Owning
change: `openspec/changes/pure-python-retrosheet/`.

- Never import `mlb_baseball`, pandas, psycopg, or any native/compiled
  dependency. Core dependencies stay standard-library only.
- Chadwick is a test-time reference only. Do not copy or transliterate its
  source; implement from Retrosheet documentation.
- Unknown record or play syntax must raise (strict) or surface as an explicit
  unsupported node. Never skip silently.
- Tests must not hit the live Retrosheet site; use small captured fixtures.
- Run: `uv run --package retrosheetpy --with pytest pytest packages/retrosheetpy/tests`

## Child DOX Index

None yet.
