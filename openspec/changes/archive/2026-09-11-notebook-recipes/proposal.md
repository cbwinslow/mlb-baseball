## Why

`openspec/project.md`'s "v1 is done when" list requires **≥5 notebook recipes**.
The repository ships one (`notebooks/01-strikeout-rate-by-decade.py`). The
`delivery` capability's spec currently only requires "at least one notebook", so
the gap is invisible to `openspec validate`. Four more polished recipes, and a
spec that matches the v1 bar, close it.

## What Changes

- Add four marimo notebooks under `notebooks/`, each answering one concrete
  analyst question **only from the released delivery surface**
  (`mlb_research.load(...)` against the published Parquet), never a database:
  - `02-home-run-era.py` — league-wide HR per plate appearance by season, and
    the juiced-ball spikes.
  - `03-three-true-outcomes.py` — the share of plate appearances that end in a
    walk, strikeout, or home run, by season.
  - `04-babip-is-mostly-luck.py` — year-over-year correlation of a qualified
    batter's BABIP versus their strikeout rate, showing which is signal and
    which is noise.
  - `05-strikeouts-and-scoring.py` — league strikeout rate versus runs per game
    by season: do more strikeouts mean fewer runs?
- Each notebook: runs top to bottom with no Postgres connection; recomputes
  rates from summed numerators/denominators (never averages rates); states its
  source table(s) and the "regular season, event-derived" provenance; ends with
  a one-sentence finding.
- Raise the `delivery` capability's notebook requirement from "at least one" to
  **a set of at least five**, each meeting the same released-data-only contract.

Out of scope: notebooks that need player/team names (the published tables carry
only surrogate keys); any new column, table, or loader change.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `delivery`: the "A runnable example notebook" requirement becomes "A set of
  runnable example notebooks" — at least five, each answering a distinct analyst
  question using only the released delivery surface and running end to end with
  no database connection.

## Impact

- **New:** `notebooks/02-home-run-era.py`, `notebooks/03-three-true-outcomes.py`,
  `notebooks/04-babip-is-mostly-luck.py`, `notebooks/05-strikeouts-and-scoring.py`.
- **Changed:** `openspec/specs/delivery/spec.md` (via the delta),
  `openspec/project.md` (NOW #7 / v1 criterion note), possibly a
  `tests/` guard that every `notebooks/*.py` imports only `mlb_research` +
  plotting/stdlib, not `mlb_baseball` or `psycopg`.
- **No** production code, connector, database, or model change. `marimo` is
  already in the `dev` extra.
- Notebooks execute network I/O to Hugging Face at runtime (dataset download) —
  same as the existing notebook; no new dependency.
