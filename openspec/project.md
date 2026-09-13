# Project constitution

The single source of truth for what this project is, who it's for, and how
work happens. **Read this first.** Full rationale:
`docs/superpowers/specs/2026-09-02-project-restructure-design.md`.
Last set: 2026-09-02; two-product model + phased ladder 2026-09-07
(`openspec/changes/archive/…-two-product-model/`).

---

## What it is

A free, **commercially-usable** (AGPL-3.0), **honest** MLB research
database: a clean grain ladder of every standard and advanced statistic,
event-derived back to 1910, every formula cited to its source, every
accuracy/leakage limitation documented.

Benchmark: **baseball.computer** — build something better (equivalent
capability plus more, innovating on top). Not a table-count contest.
baseball.computer is CC BY-NC-SA — study for ideas, **never copy its SQL
verbatim**.

## Who it's for

This repo is **two products, one database** — "ship the machine, keep the
output":

**`mlb-research` (public).** The reproducible toolkit an outside analyst
downloads: the data, the `raw`/`core`/`gold` build SQL, the metric
definitions + tie-out tests, the point-in-time feature store, the
walk-forward backtest harness, one reference baseline model, the
Markov/sim engine, notebooks, data dictionary.
**Audience:** the serious analyst (Tango / Retrosheet / FanGraphs /
academic / r/Sabermetrics tier) — knows the domain, writes SQL or Python,
values correctness and history over polish.
**Design test:** could a data journalist answer a question, with a
citation, in 5 minutes?

**The Engine (internal).** What we build *with* the toolkit and do not
give away: tuned models and their configs, novel metrics still in
validation, market-disagreement / parlay research, the subscriber
website and its content.
**Audience:** us — and later, the paying subscriber.

**The line between them — one test:** does this help a stranger build
their own research database and their own models? → **ships in
`mlb-research`.** Is it our specific answer, edge, or published content?
→ **internal Engine.** Code and SQL almost always ship (a reproducible
harness is a credibility signal, not a giveaway); trained artifacts,
tuned configs, and backtest results for any model other than the
reference baseline never ship; a metric ships once we choose to publish
it (formula + citation), and is private until then.

## The three differentiators

1. **Commercially usable** — AGPL vs baseball.computer's CC-NC.
2. **Honesty baked in** — chronological (never random) folds, documented
   leakage modes, calibration reporting, cited formulas.
3. **Full history, one query** — 1910+ at every grain, materialized.

## Delivery ($0 hosting)

Parquet on Hugging Face (+ GitHub Releases mirror) → pybaseball-style
Python loader on PyPI → DuckDB-WASM browser query page → Docker image →
Marimo notebooks + a MkDocs Material docs site. **v1.1 adds** the
point-in-time feature store (DuckDB `feat.*` relations, windows as columns,
a Feast-shaped `get_historical_features` retrieval function, two
store-level leakage checks — ADR-287, `openspec/changes/feature-store-v1/`),
the walk-forward backtest harness, and one reference baseline model
(Elo v2) + its model card — the pieces that make this a research
*platform*, not just a download. Built in three slices: the feature layer,
the harness, then Elo v2. Coverage
target: match `pybaseball` / `baseballr`. No hosted DB, no hosted REST
API (defer — needs revenue). Publishing the backbone dataset:
[`docs/PUBLIC_API.md`](../docs/PUBLIC_API.md#publishing-the-backbone-dataset-to-hugging-face).

---

## Current phase — "research database leads" (set 2026-09-02; updated 2026-09-07)

Phase A of the ladder below. Prediction models and the consumer site are
Phase B/C — not started; see the ladder.

**v1 is done when:** backbone relations 1–6 tied out to Baseball-Reference
within a documented tolerance; every metric cites its source and has a
tie-out test; published to Hugging Face; Python loader on PyPI;
DuckDB-WASM page live; a MkDocs Material docs site published (data
dictionary, grain-ladder diagram, formula citations, honest-limitations
page); ≥5 notebook recipes. (`v0.1.0` is public; the rest is finishing
work.)

**v1.1 is done when:** the point-in-time feature store is shipped in a
public release; one reference baseline model (Elo v2) + its model card is
shipped.

### Phased ladder

**Phase A — public platform.** Entry: now.
- **v1** — the stats download, finished (criteria above). Nearly there.
- **v1.1** — the platform: point-in-time feature store, walk-forward
  backtest harness, one reference baseline (Elo v2) + model card. Also
  finish the queued item: `openspec/specs/statistic-backbone/spec.md`.
  (The Baseball-Reference tie-out and the `gold.player_season` two-writer
  question — ADR-281, option A — are both done; see NEXT.)
- Exit Phase A: v1.1 shipped and versioned in a public release.

**Phase B — the Engine (internal). SPECULATIVE.** Entry: Phase A's
feature store is stable and versioned.
1. Engine triage + a `meta.metric` registry table — classify the ~110
   "Engine" composite packages into keep / add-harness / rebuild-on-demand
   / archive-as-negative-result.
2. Model ladder through the harness: elastic-net logistic →
   negative-binomial team runs → Monte Carlo market calculator → CatBoost
   challenger. Ensembles / DNNs only after tabular models are shown to
   leave signal on the table.
3. Hierarchical-Bayes player layer (PyMC).
4. Plate-appearance multinomial + simulation, feeding the Markov engine
   (supersedes markov-v2 / #88).
5. Market time-series schema (`quote_ts` / `suspended` / vig-aware) +
   model-vs-market disagreement research.
6. Novel-metric discovery program: constrained-discovery ladder →
   candidate registry → validation protocol.

Also Phase B: new data sources not in `docs/DATA_SOURCES.md` (with
source-rights docs), SQLMesh incrementality, DuckDB as a build engine.

**Phase C — live + subscriber product. SPECULATIVE.** Entry: Phase B has
at least one calibrated model beating the reference baseline on a
chronological hold-out.
- Live event log + pure state reducer + replay (`live.event`,
  `live.prediction`, market replay with latency/fill simulation).
- The subscriber website. The paid betting-advice piece is additionally
  gated on the Phase-4 legal homework — regulated per US state.

**SPECULATIVE** means: Phase A (a trustworthy research database) has a
proven audience — `pybaseball` / `baseballr`. Phases B and C rest on an
unproven premise: that this operation can produce model / betting
research people pay for. They stay on the ladder so the ambitions have a
home and a gate, but the plan does not commit to building them —
re-evaluate once Phase A has shipped and there is evidence someone wants
them. **Do not start Phase B work because the ladder lists it**; start it
because Phase A is done and the re-evaluation said go.

Bug fixes to Phase B/C areas only when they block Phase A or break `main`.

### Longer vision

Everything once recorded here — a real-time prediction ladder,
ensembles/DNNs, DuckDB as a build engine — is now sequenced into Phases
B–C above. The one standing gate: Phase C paid betting-advice needs the
per-US-state legal homework before any of it ships.

---

## Database engineering standards

- **The boundary is at `core`.** PostgreSQL is the authoritative system of
  record for `raw` and `core` — ingestion, identity reconciliation,
  provenance, constraints. The **derived feature and model layer is
  DuckDB-only**: `mlb build` reads PostgreSQL and writes the `feat.*`
  relations into one local DuckDB file; features are built there and models
  read only from there. A `feat.*` row is a reproducible artifact, not source
  data — deleting the file loses nothing. See **ADR-287**.
- All build logic in **versioned `.sql` files** run by `mlb report` /
  `mlb conform` / `mlb build`. **No triggers, no stored procedures** for
  pipeline logic (DuckDB feature SQL follows the same rule — no macros
  standing in for pipeline logic).
- **No SQL strings embedded in Python** — `scripts/lint_sql_ownership.py`
  + pre-commit hook enforce it.
- Normalization by layer: `core` normalized, `gold` deliberately
  denormalized for query speed (ADR-057) — do not "fix" `gold`.
- **EXPLAIN / ANALYZE** on every new/changed `gold` view or query before
  it ships — part of definition of done. Use the `postgres-mcp` tools.
- Indices / PK / FK / data types reviewed per `gold` table at publish.
- Run tracking + benchmarking extends the existing `meta.*` tables and
  `pg_stat_statements` — not a new subsystem.
- Optimize for a target (16 GB laptop + DuckDB on Parquet, or the Docker
  Postgres), not "all hardware".

### Modeling layer (SQL vs Python)

Deterministic aggregation over events that a researcher would recompute
→ **versioned `.sql`** run by `mlb report` / `mlb conform`, ships in
Parquet (wOBA, FIP, RE24, WPA, park factors, rolling rates, `feat.*`
snapshots). Iterative fit, simulation, or stochastic work → **Python**,
reads the feature tables, writes predictions to `gold.prediction`. This
is the existing "no SQL strings in Python" + versioned-`.sql` rule
applied to model code, not a new rule.

## How work happens

- **Workflow: OpenSpec.** Every non-trivial change is an `openspec/
  changes/<name>/` (`/opsx:propose` → `/opsx:apply` → `/opsx:archive`).
  Superpowers `brainstorming` + `test-driven-development` are skills used
  *inside* a change. The old `plans/` (now `docs/archive/plans/`) and conductor `/spec`
  workflows are retired.
- **Queue:** open `openspec/changes/` folders + the `NOW / NEXT / LATER`
  block below.
- **One-agent-per-change lock:** a `changes/<name>/` folder + its git
  worktree is a lock. One tool, one change at a time. Before starting,
  check for an existing change/worktree; if it's not yours, stop. No
  parallel work on overlapping files.
- **Context hygiene:** one change = one session = one PR, then `/clear`.
  Resume from `changes/<name>/tasks.md`, never chat scrollback.
- **Cross-tool memory:** this file + `openspec/specs/` is the shared
  state all tools read. Claude's `.claude/.../memory/` is Claude-only.
- **Definition of done includes code quality.** Every change leaves the
  code it writes or touches at standard: lean and single-purpose, no
  duplication of an existing helper, within the file-size guide
  (`development-practices.md`), no dead scaffolding or speculative
  abstraction, `SHORTCUT:` markers carrying a ceiling + trigger. The
  `changes-review` step checks this per change — a gate, not an
  aspiration. A one-time full-codebase quality pass is a separate LATER
  item, run after Phase A.

## Model roles

Claude → architecture, specs, review, correctness-critical code, all
merges. Codex → second-opinion implementation, deep debugging. Grok /
Gemini / opencode / kilo → supervised grunt work (never merges; output is
a reviewed diff).

## CI gates & review

- **Only `test` and `secrets` block a merge.** Every other bot is
  advisory — never treat its red X as a blocker.
- **Kilo Code** is the kept AI reviewer; address its WARNING/CRITICAL
  comments. CodeRabbit is advisory (CHILL profile, `.coderabbit.yaml`),
  do not wait on it. Codex auto-review is off (owner: on-demand only via
  `@codex review`). Bot audit + kill list: `openspec/changes/step4-audits/
  bot-audit.md` (owner to uninstall Qodo, Macroscope, CodeAnt, Mergify,
  Guardrails via GitHub App settings).

## Merge protocol (Claude)

Once the owner grants `Bash(gh pr merge:*)`, Claude may merge a PR when
**all** hold: `test` + `secrets` green; every human and Kilo comment
addressed; not touching a Phase B/C (SPECULATIVE) area without the owner
asking; it is Claude's own PR or one the owner asked Claude to land.
Force-push, closing issues, deleting others' branches, or landing work in
a Phase B/C area still need an explicit ask.

## Tooling

**Adopted:** DuckDB, `postgres-mcp` (formalized), MkDocs Material, Marimo, the
`add-gold-metric` project skill (to build).
**Audit done (ADR-279, 2026-09-02):** no library/extension adopted — prior
reviews hold. One follow-up filed (issue #142: stdlib `logging` for
ingestion errors). Gated for later: `requests.Session` reuse, `ftfy`,
`pandera`, `pg_duckdb`, `pg_partman`, `pgvector`, Polars, sqlglot, pg_trgm
— each has a documented trigger (see ADR-279).
**Not adopting:** pg_cron, PL/pgSQL for pipeline logic, more skill packs,
TimescaleDB, a baseball-stats MCP, GitHub/filesystem MCP.

---

## NOW / NEXT / LATER

**NOW** — finish v1 (Phase A):
1. ✅ Bootstrap OpenSpec (#139/#140)
2. ✅ Repo hygiene — worktrees 14→3, ~16 dead branches deleted, PR queue empty
3. ✅ Doc consolidation — status banners on 15 superseded / historical docs
   (part 1), then physically moved the superseded docs, the retired `plans/`
   tree, and the Superpowers plan archive into `docs/archive/` with a
   reference map in `docs/archive/README.md` and cross-references rewritten
   (part 2). `docs/DECISIONS.md` and `docs/superpowers/specs/` are never
   rewritten (historical record).
4. ✅ Bot prune + dependency/PG-extension audit — ADR-279; issue #142
   (logging); `.coderabbit.yaml`; dependency-review comment fix; owner uninstalls pending
5. MkDocs Material docs site (built in `openspec/changes/mkdocs-docs-site/`
   — index, data dictionary, grain ladder, formulas + citations, honest
   limitations; deploys through `pages.yml`; PR open) + `understand-anything`
   knowledge graph (still open)
6. ✅ Delivery surface first cut (`openspec/changes/delivery-surface/`) —
   `mlb export --preset backbone` (8 of 10 candidate tables; `player_season`/
   `team_season` excluded on source-rights grounds, see `rights-review.md`),
   HF publish step, `mlb-research` PyPI loader package, the DuckDB-WASM
   query page (`docs/site/query/`), and the example notebooks
   (`notebooks/01`..`05` — K% by decade, the HR era, three true outcomes,
   BABIP-vs-K% reliability, strikeouts-and-scoring; the ≥5-recipe v1 criterion
   is met via `openspec/changes/notebook-recipes/`, PR open). Published:
   [huggingface.co/datasets/cbwinslow/mlb-research](https://huggingface.co/datasets/cbwinslow/mlb-research),
   tag `v0.1.0`. Production `mlb` needed migrations 0094-0099 applied and its
   first-ever `mlb report` backbone build (12.9M rows, 16.4M source events)
   before the export had anything to publish — both done as part of this
   step.

7. Postseason separation (`openspec/changes/separate-postseason-stats/`,
   ADR-282 / ADR-283) — `bref.py` pulls a regular-season-only window;
   `gold.batting_postseason` / `gold.pitching_postseason` built from Lahman
   `BattingPost` / `PitchingPost`; `mlb doctor` envelope + purity guards;
   model/ML game-type audit. baseball.computer adopted as the game-type
   reference (regular-season-only aggregates everywhere). **Owner step
   outstanding:** re-ingest `raw.bref_*` for 2008–2026 and re-run `mlb report`
   (`reingest-runbook.md`).

**NEXT** — finish v1's remaining milestone work, then v1.1:
- v1 finishing work: `openspec/specs/statistic-backbone/spec.md`.
  - Baseball-Reference tie-out gate ✅ — `scripts/verify_baseball_reference_tie_out.py`:
    Judge 2022 + Cole 2023 cited cases match to Baseball-Reference's 3-decimal
    display precision; the bulk cross-check runs 2008–2025 and passed against
    the re-ingested `raw.bref_*` (`separate-postseason-stats`, 2026-09-07).
    Adding more cited cases at other grains stays open, low priority.
  - `gold.player_season` two-writer question ✅ — **ADR-281** (option A):
    `gold.player_season` (BRef/Lahman, 2008+) and the event-derived
    `gold.batting_season` / `gold.pitching_season` (Retrosheet, 1910+) are
    parallel lines, one writer each, neither a view or second writer into
    the other. Implemented and on `main` (PR #158).
- **v1.1 (the platform):** point-in-time feature store, walk-forward
  backtest harness, one reference baseline model (Elo v2) + model card.
  Sliced in `openspec/changes/feature-store-v1/` (slice 1 = DuckDB `feat.*`
  layer + `get_historical_features` + leakage checks + `mlb build` /
  `mlb verify` ✅; slice 2 = harness extraction into `mlb_research` ✅
  (`mlb_research.backtest`: `time_ordered_folds`/`run_backtest`/
  `paired_comparison`, numpy-only metrics/calibration, `experiment.py` now a
  thin adapter — `feature-store-v1-harness`; `compare()` stays unchanged,
  owner decision 2026-09-13, that change's `tasks.md` task 5.5);
  slice 3 = Elo v2 + model card, planning done, not yet implemented --
  `feature-store-v1-baseline`, narrowed from the original slice 3 sketch:
  probable-starter identity, the leakage notebook, HF publish wiring, and
  any market/production-Elo comparison are deferred to their own later
  changes; see that change's `proposal.md`). Design input:
  `docs/research/2026-09-04-modeling-and-realtime-plan.md` and two Opus
  design reviews (`feature-store-v1/DESIGN_REVIEW.md`); ADR-287 for the
  Postgres/DuckDB boundary. **feat.* is DuckDB-only — no Postgres `feat`
  schema, no Feast.**

**LATER**
- Phase B — the Engine (SPECULATIVE; re-evaluate after Phase A ships).
  See the phased ladder.
- A one-time full-codebase quality review ("vibe-code proof" pass), run
  after Phase A's v1 + v1.1 work.
