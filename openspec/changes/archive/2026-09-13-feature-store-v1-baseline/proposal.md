## Why

The `delivery` capability's "research platform" surface ships a point-in-time
feature store (slice 1) and a model-agnostic backtest harness (slice 2), but
no model. An installing analyst can build features and run a backtest against
their own callback, but has nothing to compare a new idea to, and the
project itself has no baseline number to say a fancier model actually helps.
`openspec/project.md`'s v1.1 scope calls for "one reference baseline model
(Elo v2) + model card" — this change ships exactly that, reusing the harness
slice 2 built rather than inventing a new evaluation path.

This is a **narrowed** slice 3 of the `feature-store-v1` roadmap. The
roadmap's original slice 3 sketch also included a probable-starter swap in
`feat.game`, a leakage-diagnostic notebook, and Hugging Face publish wiring.
Investigating those this session found `raw.mlb_probable` (the only source of
probable-starter identity) has roughly five weeks of history — nowhere near
enough to backtest on — so the probable-starter swap cannot honestly ship
yet. Scoping decisions (probable-starter deferred; notebook/publish deferred;
market/odds comparison deferred; the model card compares Elo v2 against
itself with the starter adjustment off, not against production Elo v1 or a
market) were made via brainstorming with the owner before this proposal was
written; each is recorded below and in `design.md`.

## What Changes

- **New `mlb_research.elo` module** — pure numpy, no database, no
  `sklearn`/`xgboost` import (matches `mlb_research.backtest`'s own
  dependency discipline). Implements Elo v2:
  - The existing Elo v1 math unchanged: home-field advantage, the
    margin-of-victory multiplier, the K-factor update
    (`mlb_baseball/model/elo.py` is the reference implementation; this is a
    relocation into the shipped package, not a rewrite of the formula).
  - **A preseason prior that fades**, replacing v1's one-time reversion jump
    at a season boundary with a smooth blend over a team's first
    `FADE_GAMES` games of a new season.
  - **A starter-quality adjustment**: each team's effective rating is
    nudged by its starter's entering form (`feat.game`'s
    `home_starter_fip_like_30d` / `away_starter_fip_like_30d`), z-scored
    against that fold's own training data (no leakage), with missing
    starter data treated as neutral, never a fabricated average.
  - Runs through `mlb_research.backtest.run_backtest` (slice 2) as a
    `fit_fn`/`predict_fn` pair — Elo is exactly the sequential,
    predict-before-update model that seam was built for.
- **A model card**: `build_model_card()` backtests Elo v2 twice — starter
  adjustment on vs. off (`STARTER_WEIGHT=0`, the "home-field baseline") —
  and reports both models' log loss / Brier / calibration plus a
  `paired_comparison` (slice 2, previously unused by any caller) between
  them on identical held-out games. `render_model_card()` renders the result
  to markdown, with a limitations section. No database, no market data —
  reproducible by anyone with the public `feat.game` dataset.

Out of scope (deferred to their own future changes, not pulled forward):

- Swapping `feat.game`'s starter identity from actual to probable
  (`raw.mlb_probable` has ~5 weeks of history; the historical rows this
  model card backtests against can never have probable-starter data, so
  wiring it in now would not change what the card can honestly report).
- The leakage-diagnostic notebook recipe (label-shuffle, injected-outcome).
- Hugging Face publish wiring for the card.
- Comparing Elo v2 against betting-market odds, or against production Elo
  v1's `gold.game_feature` ratings (a database dependency the model card
  deliberately avoids).
- Any change to `mlb_baseball/model/elo.py` (v1, Postgres-writing, feeds
  `gold.game_feature.home_elo`) — a separate, already-shipped thing.
- Any change to `mlb_baseball/model/experiment.py`'s `compare()` or the
  `mlb experiment compare` CLI command (resolved separately in
  `feature-store-v1-harness`; `paired_comparison` is called directly by the
  new model-card code here, not through that CLI).

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `delivery`: add one requirement to the "research platform" surface — **a
  shipped reference baseline model and its model card**. `mlb_research.elo`
  ships in the installable `mlb-research` package; model evaluation runs
  through the already-shipped `mlb_research.backtest` harness; the model
  card is reproducible with the public dataset alone (no database, no
  market data, no paid source).

## Impact

- **New:** `packages/mlb-research/mlb_research/elo.py`;
  `packages/mlb-research/tests/test_elo.py`.
- **Changed:** `packages/mlb-research/README.md` (a model-card usage
  section); `docs/PUBLIC_API.md` / `docs/RESEARCH.md` /
  `mlb_baseball/model/AGENTS.md` (the reference baseline now ships, pointer
  to it); `openspec/project.md` (`NOW/NEXT/LATER`, slice 3 marked done);
  `openspec/changes/feature-store-v1/proposal.md` (Roadmap: slice 3 done,
  narrowed scope noted).
- **Unchanged:** `mlb_baseball/model/elo.py` (v1); `mlb_baseball/model/
  experiment.py`'s public API including `compare()`; `feat.game`'s starter
  identity (`starter_is_actual` stays `TRUE`); `mlb_research.backtest`
  (consumed as-is, no signature changes); every migration, connector,
  conform, and ingestion path.
