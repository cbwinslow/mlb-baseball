## Why

The project currently ships two things that both look like "the point-in-time
feature store," and code plus docs disagree about which one is canonical.
`mlb_baseball/public.py::build_features()` (re-exported from
`mlb_baseball/__init__.py`) calls `model.run_features()`, which rebuilds the
legacy `gold.game_feature` — the ~178-family, Phase-B/Engine-territory
relation `openspec/project.md` explicitly marks SPECULATIVE and never part of
the public surface. `docs/PUBLIC_API.md` still documents root
`build_features()` exactly that way. Meanwhile `docs/FEATURE_STORE.md` and
`mlb_baseball/feat.py` establish DuckDB `feat.*` (built by `mlb build`) as the
actual canonical point-in-time research feature surface for the public
`mlb-research` package — and `feat.py` explicitly never touches
`gold.game_feature`. `docs/ARCHITECTURE.md` still describes `gold` as owning
the feature/model surface in language that predates the DuckDB boundary ADR
(ADR-287).

This was flagged as the highest-confidence finding in a project re-review
(`docs/archive/CHATGPT_AUDIT_2026-09.md`, finding #1) and independently
verified against the current repository: the contradiction is real and live,
not stale. An analyst or contributor reading `docs/PUBLIC_API.md` today would
reasonably conclude `build_features()` is the point-in-time research feature
store; it is not, and using it that way would silently pull in Phase-B/Engine
data with no point-in-time guarantees.

## What Changes

- **No removal of working legacy behavior.** `build_features()` /
  `model.run_features()` keep working exactly as they do today — this is a
  labeling and documentation fix, not a functional change to either path.
- `mlb_baseball/public.py::build_features()` and its docstring are labeled
  explicitly as the legacy/internal Engine feature rebuild (rebuilds
  `gold.game_feature`), not a point-in-time research feature store.
- `docs/PUBLIC_API.md` is corrected: the entry for `build_features()` states
  plainly that it is the legacy `gold.game_feature` rebuild and points readers
  to the actual point-in-time research feature store (`mlb build` /
  `mlb_research.get_historical_features`, per `docs/FEATURE_STORE.md`).
- `docs/ARCHITECTURE.md` is updated so its description of `gold`'s role no
  longer implies it owns the canonical feature/model surface; it references
  the DuckDB `feat.*` boundary (ADR-287) instead.
- If, once the docs are reconciled, there turns out to be a real need for a
  programmatic (non-CLI) way to trigger the canonical DuckDB `feat.*` build,
  it is exposed under an unambiguous new name — never by overloading
  `build_features()`. (Design decision: confirm during `design.md` whether
  this is actually needed now, or deferred until a real caller asks for it.)
- New standing rule, recorded as a spec requirement (see Capabilities below):
  the root package's public API and docs must not present two functions that
  both plausibly claim to be "the" point-in-time feature store without
  unambiguous, co-located labeling of which is legacy and which is canonical.

## Capabilities

### New Capabilities

- `feature-store-boundary`: the root `mlb_baseball` package's public API
  surface and documentation SHALL unambiguously distinguish the legacy
  Engine/`gold.game_feature` feature path from the canonical DuckDB `feat.*`
  point-in-time research feature store, so a reader of the public API docs
  cannot reasonably mistake one for the other.

### Modified Capabilities

- None. `delivery`'s existing point-in-time feature store requirements
  (`openspec/specs/delivery/spec.md`) already describe the DuckDB `feat.*`
  path correctly and are not changing — this change brings the rest of the
  codebase and docs into line with what `delivery` already states, it does
  not change `delivery`'s own requirements.

## Impact

- **Docs:** `docs/PUBLIC_API.md`, `docs/ARCHITECTURE.md`.
- **Code:** `mlb_baseball/public.py` (docstring/labeling only, unless design
  finds a real need for a new programmatic entry point — see above),
  `mlb_baseball/__init__.py` (re-export docstring only).
- **No schema, migration, or CLI change.** `mlb build`, `mlb features`,
  `mlb predict` and every existing CLI subcommand keep their current names and
  behavior.
- **No new dependency, no new source, no rights change.**
