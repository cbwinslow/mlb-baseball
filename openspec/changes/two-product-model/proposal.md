## Why

`openspec/project.md` freezes all prediction-model work, the consumer site, and
the ~110 "Engine" composite packages until one milestone (a Hugging Face stats
dump + docs) is met. Three planning sessions (`expansion-plan.md`, Sept 4 + Sept
6) landed on a cleaner frame the owner has approved: **ship the machine, keep the
output** — one public reproducible toolkit (`mlb-research`) and one internal
"Engine" that stands on it to produce the research and predictions we publish for
revenue. The blanket freeze exists so Engine work does not starve the public
product; a clean two-product split with the Engine reading a stable public
interface removes that risk, so the freeze can become a **phased ladder with
entry criteria** instead. Expansions get scheduled, not shot down.

## What Changes

- **Two-product model, written into the constitution.** `mlb-research` (public):
  connectors, migrations, `raw/core/gold` build SQL, bootstrap + daily +
  live-upkeep tooling, cited metric definitions + their SQL + tie-out tests, the
  point-in-time feature store, the walk-forward backtest harness, the Markov/sim
  engine, **one** reference baseline model + its model card, notebooks, data
  dictionary. The Engine (internal): tuned model weights/configs, backtest
  results for tuned models, market-disagreement / parlay / CLV research, candidate
  metrics still in validation, the model ladder above the baseline, the
  subscriber website and its posts.
- **v1 redefined.** The first public release is a *research platform*, not a
  stats dump: it also includes the point-in-time feature store and one reference
  baseline model (Elo v2) with a model card. The milestone is not "done" until
  those ship.
- **`Frozen` list → phased ladder.** Phase A (public platform) → Phase B (Engine,
  internal) → Phase C (live + subscriber product), each with an explicit entry
  criterion (phase N starts when phase N−1's public deliverable is stable and
  versioned). Nothing is deleted — the ~110 Engine packages, the prediction
  ladder, live betting, and the subscriber site each get a home and a gate.
- **`announced to r/Sabermetrics` removed** from the phase done-criteria. Not
  replaced — announcement is a separate later decision, gated on the codebase
  being tightened first.
- **SQL vs Python layer split, stated.** Deterministic aggregation over events
  that a researcher would recompute → SQL, and it ships. Iterative fit /
  simulation / stochastic → Python, reads the feature tables, writes predictions
  back to Postgres. (Already implied by the "no SQL strings in Python" +
  versioned `.sql` rules; this makes it explicit for model code.)
- **`model/AGENTS.md` updated** to state the ship-vs-internal line for model
  code.

Docs and contract only. No code changes. The feature store, the backtest
harness, the reference baseline, the Engine triage / `meta.metric` registry, and
the codebase-quality ("vibe-code proof") review are each **separate later
changes** — this one only makes them sanctioned lanes.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `delivery`: add requirements defining (a) the public distribution's scope — it
  includes a point-in-time feature store and one reference baseline model, not
  only Parquet tables — and (b) the ship-vs-internal boundary — trained model
  artifacts, tuned hyperparameters, and backtest results for tuned models are
  never published.

## Impact

- `openspec/project.md` — "Who it's for", "Delivery", "Current phase"
  done-criteria, "Frozen" → phased ladder, "Longer vision", + a layer-split note.
- `openspec/specs/delivery/spec.md` — via the delta above.
- `mlb_baseball/model/AGENTS.md` — ship-vs-internal line for model code.
- No source code, no migrations, no dependencies. Downstream changes it unblocks:
  the feature store, the backtest harness + reference baseline, the Engine
  triage + `meta.metric` registry, and the codebase-quality review.
