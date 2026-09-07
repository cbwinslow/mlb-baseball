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
- Keep v1 small (the stats download, near done) and name v1.1 (feature store +
  baseline) as the next milestone — so there is a closed milestone soon.
- Remove "announced to r/Sabermetrics" from the done-criteria with no replacement.
- State the SQL-vs-Python layer split for model code.
- Add a standing per-change code-quality rule to the definition of done, and a
  tracked LATER item for a one-time full-codebase review.
- Keep every previously-listed ambition (the ~110 Engine packages, prediction
  ladder, live betting, subscriber site) present in the document with a home,
  while marking the model/betting back half speculative.

**Non-Goals:**
- No implementation. No feature store, no harness, no baseline model, no Engine
  triage, no codebase cleanup in this change.
- No change to the database engineering standards, CI gates, merge protocol, or
  model-roles sections of `project.md`.
- No new capability spec — `delivery` is the only capability touched.

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

- **Phase A — public platform.** Entry: now. Two milestones:
  - **v1** — the stats download, finished: backbone tie-out, cited metrics, HF
    publish, PyPI loader, DuckDB-WASM page, MkDocs site, ≥5 notebooks. Nearly
    done (`v0.1.0` is public). This is the milestone that closes soon.
  - **v1.1** — the platform: the point-in-time feature store, the walk-forward
    backtest harness, one reference baseline (Elo v2) + model card. The
    differentiator; the next milestone after v1. Also finish the queued items
    (`statistic-backbone/spec.md`, expand the Baseball-Reference tie-out, the
    `gold.player_season` two-writer ADR).
  - Exit Phase A: v1.1 shipped and versioned in a public release.
- **Phase B — the Engine (internal). SPECULATIVE.** Entry: Phase A's feature
  store is stable and versioned. Contents: Engine triage + a `meta.metric`
  registry table; the model ladder through the harness (elastic-net →
  negative-binomial team runs → Monte Carlo market calculator → CatBoost
  challenger); hierarchical-Bayes player layer; plate-appearance multinomial +
  simulation; market time-series schema + model-vs-market disagreement research;
  the novel-metric discovery program.
- **Phase C — live + subscriber product. SPECULATIVE.** Entry: Phase B has at
  least one calibrated model beating the baseline on a chronological hold-out.
  Contents: live event log + state reducer + replay; the subscriber website. The
  paid-betting-advice piece is additionally gated on the Phase-4 legal homework
  (regulated per US state) — that gate is unchanged.

**Speculative** means: Phase A (a trustworthy research database) has demonstrated
demand — pybaseball / baseballr prove the audience. Phases B and C rest on an
unproven premise (that this operation can produce model/betting research people
pay for). They stay on the ladder so the ambitions have a home and a gate, but
the plan does not commit to building them — they are re-evaluated once Phase A
has shipped and there is evidence someone wants them. Do not start Phase B work
because the ladder lists it; start it because Phase A is done and the
re-evaluation said go.

The `~110 "Engine" composite packages` line moves from "Frozen" into Phase B item
1 (triage), so it has a home and an owner instead of a freeze.

Alternative considered: keep "Frozen" and just add exceptions. Rejected — that is
the current friction; every expansion becomes an argument about the freeze.

### D3 — v1 done-criteria: remove one line, add none

"Current phase … Phase is done when:" list — remove `announced to
r/Sabermetrics`. Do **not** add the feature store or baseline to v1's criteria;
those are v1.1 (see D2). The other v1 criteria (backbone tie-out, cited metrics,
HF publish, PyPI loader, DuckDB-WASM page, MkDocs site, ≥5 notebooks) are
unchanged. Add a short "v1.1" criteria block right after: feature store shipped
in a public release; one reference baseline model (Elo v2) + model card shipped.

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

### D6 — Code quality: a standing per-change rule, not a one-time sweep

Add to the definition of done (in `project.md`'s "How work happens", extending
the config.yaml definition-of-done line): **every OpenSpec change leaves the code
it writes or touches at standard** — lean and single-purpose, no duplication of
an existing helper, within the file-size guide (`development-practices.md`), no
dead scaffolding or speculative abstraction, `SHORTCUT:` markers carry a ceiling
+ trigger. This is the bar `/code-review` and `/simplify` already apply; the rule
makes it a per-change gate the `changes-review` step checks, not an aspiration.

A one-time full-codebase review (the "vibe-code proof" pass the owner asked for)
is recorded as a **LATER** item, run after Phase A's v1 + v1.1 work is executed —
by then the standing rule has already lifted the parts of the tree that got
touched, so the sweep is smaller.

Alternative considered: a dedicated codebase-cleanup change now, before the
contract revision. Rejected by the owner — a standing rule improves quality on
every change from here forward, and the big sweep lands when there is bandwidth
rather than blocking the roadmap.

## Risks / Trade-offs

- **v1.1 (feature store + harness + baseline) is 2–3 months** and PIT correctness
  is genuinely hard → Mitigation: v1 (the stats download) closes first and is a
  real, usable public artifact; v1.1 is scoped in its own proposal with the
  leakage-test battery as a first-class deliverable, not an afterthought.
- **The phased ladder is read as permission to start Phase B early** → Mitigation:
  each phase's entry criterion is a hard gate, Phases B/C are marked SPECULATIVE
  with an explicit "do not start because the ladder lists it" note, and the
  one-change-at-a-time lock still applies.
- **The standing code-quality rule becomes a rubber stamp** → Mitigation: it maps
  to concrete checks the `changes-review` step already runs (file size,
  duplication, dead scaffolding, `SHORTCUT:` ledger); it is not a new subjective
  bar.
- **`model/AGENTS.md` and `project.md` drift** → Mitigation: the ship/internal
  test is stated once in `project.md` and referenced (not restated) from
  `model/AGENTS.md`.

## Open Questions

None that block this change. The exact contents of the feature store, the
harness, and the Engine triage are settled in their own later proposals.
