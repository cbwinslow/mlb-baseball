# Project constitution

The single source of truth for what this project is, who it's for, and how
work happens. **Read this first.** Full rationale:
`docs/superpowers/specs/2026-09-02-project-restructure-design.md`.
Last set: 2026-09-02.

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

**Primary:** the serious analyst (Tango / Retrosheet / FanGraphs /
academic / r/Sabermetrics tier). Knows the domain, writes SQL or Python,
values correctness and history over polish.
**Design test:** could a data journalist answer a question, with a
citation, in 5 minutes?
**Secondary:** the data scientist who clones the repo for their own
models (revenue bridge, later phase).

## The three differentiators

1. **Commercially usable** — AGPL vs baseball.computer's CC-NC.
2. **Honesty baked in** — chronological (never random) folds, documented
   leakage modes, calibration reporting, cited formulas.
3. **Full history, one query** — 1910+ at every grain, materialized.

## Delivery ($0 hosting)

Parquet on Hugging Face (+ GitHub Releases mirror) → pybaseball-style
Python loader on PyPI → DuckDB-WASM browser query page → Docker image →
Marimo notebooks + a MkDocs Material docs site. Coverage target: match
`pybaseball` / `baseballr`. No hosted DB, no hosted REST API (defer —
needs revenue). Publishing the backbone dataset:
[`docs/PUBLIC_API.md`](../docs/PUBLIC_API.md#publishing-the-backbone-dataset-to-hugging-face).

---

## Current phase — "research database leads" (set 2026-09-02, ~3 months)

The prediction site and models are **frozen** (see Frozen list). Phase is
done when: backbone relations 1–6 tied out to Baseball-Reference within a
documented tolerance; every metric cites its source and has a tie-out
test; published to Hugging Face; Python loader on PyPI; DuckDB-WASM page
live; a MkDocs Material docs site published (data dictionary, grain-ladder diagram,
formula citations, honest-limitations page); ≥5 notebook recipes;
announced to r/Sabermetrics.

### Frozen — no work until the phase milestone is met

Prediction models (new `model/*.py` work), the consumer site, new data
sources not in `docs/DATA_SOURCES.md`, the ~110 "Engine" composite
packages, markov-v2 / #88, prediction ladder wave 2, SQLMesh
incrementality. Bug fixes to frozen areas only when they block the
milestone or break `main`.

### Longer vision (recorded, not scheduled)

Phase 2 prediction ladder (pitch→season, real-time) · Phase 3 exploratory
ML (ensembles/voting/DNNs; publish only what clears the bar) · Phase 4
subscriber betting-advice product (needs legal homework — regulated per
US state) · DuckDB as a build engine, not just an export format.

---

## Database engineering standards

- All build logic in **versioned `.sql` files** run by `mlb report` /
  `mlb conform`. **No triggers, no stored procedures** for pipeline
  logic.
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
addressed; not touching a frozen area; it is Claude's own PR or one the
owner asked Claude to land. Force-push, closing issues, deleting others'
branches, or merging into a frozen area still need an explicit ask.

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

**NOW** — restructure execution (spec §10):
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
5. MkDocs Material docs site + `understand-anything` knowledge graph
6. ✅ Delivery surface first cut (`openspec/changes/delivery-surface/`) —
   `mlb export --preset backbone` (8 of 10 candidate tables; `player_season`/
   `team_season` excluded on source-rights grounds, see `rights-review.md`),
   HF publish step, `mlb-research` PyPI loader package, the DuckDB-WASM
   query page (`docs/site/query/`), and one example notebook
   (`notebooks/01-strikeout-rate-by-decade.py`). Published:
   [huggingface.co/datasets/cbwinslow/mlb-research](https://huggingface.co/datasets/cbwinslow/mlb-research),
   tag `v0.1.0`. Production `mlb` needed migrations 0094-0099 applied and its
   first-ever `mlb report` backbone build (12.9M rows, 16.4M source events)
   before the export had anything to publish — both done as part of this
   step.

**NEXT** — the milestone proper: capture the grain backbone as
`openspec/specs/statistic-backbone/spec.md`; ✅ Baseball-Reference tie-out
tests (2023 Judge / Cole) — `scripts/verify_baseball_reference_tie_out.py`,
run against production: both cases match exactly (rate stats to
Baseball-Reference's own 3-decimal display precision); expand coverage
beyond these two seasons as a follow-up; `gold.player_season` two-writer
ADR (ADR-278 relation-6, options A/B/C — recommend A).

**LATER** — Phase 2 (prediction ladder) and beyond. See Longer vision.
