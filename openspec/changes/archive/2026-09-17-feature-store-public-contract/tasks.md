## 1. `mlb_baseball/public.py` labeling

- [x] 1.1 Update `build_features()`'s docstring (currently *"Rebuild
  point-in-time game features in the configured database."*) to state it
  rebuilds the legacy `gold.game_feature` relation (internal Engine/prediction
  pipeline stage), not the point-in-time research feature store, and points to
  `mlb build` / `docs/FEATURE_STORE.md` for the actual research feature store.
  No change to the function body or its call to `model.run_features()`.
  Verify: `git diff` shows only the docstring changed; `uv run mlb predict`
  (or the existing test covering `run_predictions()`/`build_features()`)
  still passes unchanged.
- [x] 1.2 Check `mlb_baseball/__init__.py`'s re-export of `build_features` for
  any docstring/comment that also needs the same correction. Verify: grep for
  `build_features` in `__init__.py` shows either no docstring duplication, or
  the same corrected wording if one exists.

## 2. `docs/PUBLIC_API.md`

- [x] 2.1 Change the `build_features()` table row (currently *"Rebuild
  point-in-time `gold.game_feature` rows."*) to state it is the legacy
  Engine/prediction-pipeline feature rebuild, not the point-in-time research
  feature store. Verify: the row no longer uses the phrase "point-in-time" to
  describe `gold.game_feature`.
- [x] 2.2 Add one sentence directly below the API table pointing readers to
  `docs/FEATURE_STORE.md` / `mlb build` for the actual point-in-time research
  feature store. Verify: a reader scanning the table top-to-bottom hits this
  pointer before or at the `build_features()` row.

## 3. `docs/ARCHITECTURE.md`

- [x] 3.1 Add one sentence to the `gold` bullet (currently ends "...`gold.game_feature`
  serves as the primary completed-and-scheduled consumer-demand relation.")
  naming the DuckDB `feat.*` boundary (ADR-287) and stating `gold.game_feature`
  is internal/Engine scope, not the public feature surface. Leave the rest of
  the bullet (reporting surface, `gold.player_season` etc.) unchanged — it is
  accurate. Verify: `grep -n "feat\." docs/ARCHITECTURE.md` finds the new
  reference; the bullet's other claims are untouched in the diff.

## 4. Spec

- [x] 4.1 `openspec validate feature-store-public-contract --strict` passes
  for the new `feature-store-boundary` capability delta.

## 5. Verification

- [x] 5.1 Fresh read-through: `docs/PUBLIC_API.md`, `docs/ARCHITECTURE.md`,
  and `mlb_baseball/public.py`'s `build_features()` docstring are internally
  consistent with `docs/FEATURE_STORE.md` and `openspec/specs/delivery/spec.md`
  — no remaining passage describes `gold.game_feature` as the point-in-time
  research feature store. Verify: `grep -rn "point-in-time" docs/PUBLIC_API.md
  docs/ARCHITECTURE.md mlb_baseball/public.py` — every match is either about
  the DuckDB `feat.*` store or absent from the legacy-path descriptions.
- [x] 5.2 `uv run pytest` targeted at any existing test asserting
  `build_features()`'s docstring or behavior (if one exists) still passes;
  `ruff check .` / `ruff format --check` clean on touched files.
