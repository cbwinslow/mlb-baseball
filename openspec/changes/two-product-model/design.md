## Context

See `proposal.md` — Why. The constitution (`openspec/project.md`) currently has a
binary "Frozen list" that blocks all model work until one milestone is met, and a
"Current phase" done-criteria list that ends in "announced to r/Sabermetrics".
The owner has approved the two-product frame and a phased ladder. This change is
docs + spec-delta only; every implementation piece it references (feature store,
harness, baseline, Engine triage, codebase-quality review) is a separate later
change.

## Goals / Non-Goals

**Goals:**
- Write the two-product model into `project.md` as the definition of the product,
  not a footnote.
- Replace the binary freeze with a Phase A / B / C ladder, each phase carrying an
  explicit entry criterion, so nothing is "frozen" — only "not yet in its phase".
- Redefine the v1 milestone to include the feature store + one reference baseline.
- Remove "announced to r/Sabermetrics" from the done-criteria with no replacement.
- State the SQL-vs-Python layer split for model code.
- Keep every previously-listed ambition (the ~110 Engine packages, prediction
  ladder, live betting, subscriber site) present in the document with a home.

**Non-Goals:**
- No implementation. No feature store, no harness, no baseline model, no Engine
  triage in this change.
- No change to the database engineering standards, CI gates, merge protocol, or
  model-roles sections of `project.md`.
- No new capability spec — `delivery` is the only capability touched.
- Not deciding the codebase-quality bar here (that is the review change's job).

## Decisions

### D1 — The ship / internal line is a single test, stated once

Rule of thumb written into `project.md` and `model/AGENTS.md`:
> Does this help a stranger build their own research database and their own
> models? → **ships in `mlb-research`.**
> Is it our specific answer, edge, or published content? → **internal Engine.**

Concretely: all code and SQL ship (a reproducible harness is a credibility signal,
not a giveaway); trained artifacts, tuned configs, and non-baseline backtest
results never ship; metrics ship once the owner chooses to publish them (with
formula + citation), and are `candidate`/private until then.

Alternative considered: a per-directory allow/deny list. Rejected — it rots; the
one-sentence test scales to new files without maintenance.

### D2 — Phased ladder replaces the Frozen list

`project.md`'s "Frozen — no work until the phase milestone is met" section becomes
"Phased ladder". Phases and entry criteria:

- **Phase A — public platform.** Entry: now. Contents: finish the queued
  milestone work (MkDocs site, `statistic-backbone/spec.md`, expand the
  Baseball-Reference tie-out, the `gold.player_season` two-writer ADR); the
  point-in-time feature store; the walk-forward backtest harness + one reference
  baseline (Elo v2) + model card. Exit: all of that shipped and versioned in a
  public release.
- **Phase B — the Engine (internal).** Entry: Phase A's feature store is stable
  and versioned. Contents: Engine triage + a `meta.metric` registry table; the
  model ladder through the harness (elastic-net → negative-binomial team runs →
  Monte Carlo market calculator → CatBoost challenger); hierarchical-Bayes player
  layer; plate-appearance multinomial + simulation; market time-series schema +
  model-vs-market disagreement research; the novel-metric discovery program.
- **Phase C — live + subscriber product.** Entry: Phase B has at least one
  calibrated model beating the baseline on a chronological hold-out. Contents:
  live event log + state reducer + replay; the subscriber website. The
  paid-betting-advice piece is additionally gated on the Phase-4 legal homework
  (regulated per US state) — that gate is unchanged.

The `~110 "Engine" composite packages` line moves from "Frozen" into Phase B item
1 (triage), so it has a home and an owner instead of a freeze.

Alternative considered: keep "Frozen" and just add exceptions. Rejected — that is
the current friction; every expansion becomes an argument about the freeze.

### D3 — v1 milestone gains two line items, loses one

"Current phase … Phase is done when:" list — remove `announced to r/Sabermetrics`;
add `point-in-time feature store shipped in a public release` and `one reference
baseline model (Elo v2) + model card shipped`. The other criteria (backbone
tie-out, cited metrics, HF publish, PyPI loader, DuckDB-WASM page, MkDocs site,
≥5 notebooks) are unchanged.

### D4 — SQL vs Python layer split

Add a short subsection (under "Database engineering standards" or a new
"Modeling layer" note): deterministic aggregation over events that a researcher
would recompute → versioned `.sql`, ships in Parquet. Iterative fit / simulation
/ stochastic → Python, reads the feature tables, writes predictions back to
Postgres (`gold.prediction`). This is the existing "no SQL strings in Python" +
versioned-`.sql` rule applied to model code, not a new rule.

### D5 — "Longer vision" section folds into the ladder

The four "Longer vision (recorded, not scheduled)" bullets map onto Phase B/C
items. Keep a one-line pointer ("Phase 4 subscriber betting-advice needs legal
homework — regulated per US state") since that gate is real and separate; drop
the rest as now-scheduled.

## Risks / Trade-offs

- **v1 timeline slips** by the feature-store + baseline build → Mitigation: that
  work was already the immediate next step; the ladder just names it as part of
  v1 instead of a vague "later". The stats dump (`v0.1.0`) is already public, so
  there is a usable artifact in the meantime.
- **The phased ladder is read as permission to start Phase B early** → Mitigation:
  each phase's entry criterion is written as a hard gate, and the
  one-change-at-a-time lock still applies.
- **`model/AGENTS.md` and `project.md` drift** → Mitigation: the ship/internal
  test is stated once in `project.md` and referenced (not restated) from
  `model/AGENTS.md`.

## Open Questions

None that block this change. The exact contents of the feature store, the
harness, and the Engine triage are settled in their own later proposals.
