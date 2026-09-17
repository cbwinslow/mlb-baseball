## Context

See `proposal.md` for the motivating contradiction. The concrete current text:

- `mlb_baseball/public.py:74-76`: `build_features()`'s docstring reads
  *"Rebuild point-in-time game features in the configured database."* and
  calls `model.run_features()` (rebuilds `gold.game_feature`).
- `docs/PUBLIC_API.md:15`: `| build_features() | Rebuild point-in-time
  gold.game_feature rows. |`
- `docs/ARCHITECTURE.md:25`: describes `gold` as holding "feature families,
  immutable feature snapshots, baseline/model tables" with `gold.game_feature`
  as "the primary completed-and-scheduled consumer-demand relation" — no
  mention of the DuckDB `feat.*` boundary (ADR-287) or that this relation is
  Phase-B/Engine-scoped, not the public research feature store.
- `docs/FEATURE_STORE.md` (feature-store-v1) already correctly documents
  `feat.*` as the canonical point-in-time research feature store and states
  `feat.py` never reads `gold.game_feature`.
- `openspec/specs/delivery/spec.md` already correctly describes the public
  point-in-time feature store in terms of the DuckDB path — it needs no
  change.

## Goals / Non-Goals

**Goals:**
- Make it impossible for a reader of the public docs to mistake the legacy
  `gold.game_feature` rebuild for the point-in-time research feature store.
- Fix the three concrete stale passages named above.
- Add a spec requirement so a future change re-introducing this ambiguity is
  a spec violation, not just a docs oversight.

**Non-Goals:**
- Renaming, removing, or deprecating `build_features()` / `model.run_features()`.
  It is real, working, in-use legacy behavior (the daily `mlb predict` pipeline
  depends on it via `model.run()` → feature stage). Removing or renaming it is
  Phase-B/Engine-triage territory (`openspec/project.md`'s "Engine triage"
  item), explicitly out of scope here.
- Building a new programmatic (non-CLI) entry point for the DuckDB `feat.*`
  build. `mlb build` already exists as the CLI entry point; nothing in this
  change's research found an existing caller that needs a programmatic one
  instead of shelling out. See Open Questions.
- Touching `mlb_baseball/feat.py`, `mlb_baseball/model/__init__.py`, or any
  other runtime code path. This change is documentation- and docstring-only.

## Decisions

**1. Rename the docstring/label, not the function.** `build_features()` keeps
its name (it's re-exported from `mlb_baseball/__init__.py` and used by
`run_predictions()`'s own docstring reference-chain). Its docstring changes to
name what it actually does and where it fits:
*"Rebuild the legacy `gold.game_feature` relation (the internal
prediction-pipeline feature stage) — not the point-in-time research feature
store. For that, see `mlb build` / `docs/FEATURE_STORE.md`."*
Alternative considered: rename to something like `build_engine_features()`
with `build_features` as a deprecated alias. Rejected — this is a docs/labeling
fix per the proposal, not a breaking API change; a rename is exactly the kind
of "silently repoint" scope the proposal explicitly rules out. If Engine
triage later decides to rename it, that's a separate, explicit change.

**2. `docs/PUBLIC_API.md` table row gets the same two-sentence treatment**,
plus one added row/pointer to `docs/FEATURE_STORE.md` right below the table so
a reader scanning the table doesn't miss the actual point-in-time store.

**3. `docs/ARCHITECTURE.md`'s `gold` bullet gets one added sentence** naming
the DuckDB `feat.*` boundary and stating `gold.game_feature` is internal/Engine
scope, not the public feature surface — not a rewrite of the whole bullet
(the rest of it, about `gold`'s reporting surface / `gold.player_season` etc.,
is accurate and unrelated).

**4. New capability `feature-store-boundary`, not a `delivery` modification.**
`delivery`'s spec already correctly describes the canonical feature store; it
doesn't need to change. The new requirement is about the *root package's*
public-facing surface not contradicting `delivery`'s existing contract — a
distinct, narrower concern that belongs in its own capability rather than
bolted onto `delivery`.

## Risks / Trade-offs

- **[Risk]** A future contributor still adds a new feature-building function
  without reading this spec, reintroducing the ambiguity in a different form.
  → **Mitigation:** the spec requirement is scenario-testable (docstring/doc
  text can be grepped for the labeling pattern in a lint/CI check later if this
  recurs) — not attempted in this change, but the spec gives a change reviewer
  a concrete standard to hold a future PR to.
- **[Risk]** Someone is relying on `docs/PUBLIC_API.md`'s current (wrong)
  description and has built tooling assuming `build_features()` is
  point-in-time-safe. → Low likelihood (the project has one operator, and the
  daily pipeline's own use of `build_features()` is exactly the legacy
  Engine use this change is naming correctly) — no migration needed, this
  makes the docs match reality, it doesn't change reality.

## Migration Plan

No migration. Docs and docstrings only; deploy is "merge the PR." No rollback
concern beyond a normal revert.

## Open Questions

- Does anything actually need a programmatic (non-CLI) trigger for the
  DuckDB `feat.*` build, or is `mlb build` (shelled out, or called via
  `subprocess`/CI step) sufficient for every current and near-term caller?
  Deferred: no current caller was found needing this; if one shows up, expose
  it under a new name then (per proposal, not by overloading
  `build_features()`). Doesn't change this change's specs, approach, or
  tasks — it's a "build it when something asks for it" deferral, not a gap
  in this change's design.
