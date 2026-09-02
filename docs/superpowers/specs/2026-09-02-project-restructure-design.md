# Project restructure — constitution, workflow, knowledge architecture

Date: 2026-09-02
Status: v3 — owner reviewed 2026-09-02; Marimo + Kilo chosen, docs site
revised Quarto → MkDocs Material. Steps 1–4 executed and merged
(#139–#146). Step 5–6 open; delivery-surface (Step 6) planned as an
OpenSpec change (#145). Live state: `openspec/project.md`.
Supersedes: the "Track C" framing in `scratchpad/forward-plan.md`; reframes
`docs/NORTH_STAR.md` as an input to a single canonical constitution.

---

## 1. Problem

The project keeps circling the same strategic questions ("what are we
building", "what's next", "why is this a mess") without an answer that
sticks. Concretely:

- **No constitution.** "What this is, who it's for, how we work" lives
  nowhere canonical. It's spread across `docs/NORTH_STAR.md`,
  `docs/RESEARCH.md`, `docs/ROADMAP.md`, `docs/CODE_REVIEW_2026-09.md`,
  ~279 ADRs, `plans/`, `docs/superpowers/plans/`, and `scratchpad/*.md`.
- **Three competing spec workflows.** superpowers (`brainstorming` →
  `writing-plans` → `plans/`), the conductor plugin (`/spec`, `/build`,
  `/prd`, `/fix`), and OpenSpec is installable but unused. Each session
  picks a different one.
- **Agents collide.** Claude, ChatGPT, Grok, and subagent batches work
  the same repo in parallel with no lock. This session alone: a parallel
  ChatGPT session force-pushed over an in-progress branch; ~15 stale
  worktrees exist; subagent PR batches left half-finished branches.
- **Doc sprawl.** Too many markdown files, too long, contradictory in
  places (e.g. two "player season" products with no documented
  relationship — see ADR-278 relation-6).
- **CI/review noise.** ~10 bots comment on every PR.
- **Scope creep in conversation.** Strategy sessions turn into fifteen
  "I also want" items with no ranking — the meta-cause of all of the
  above.

The fix is **one canonical source of truth that every session is
required to read first**, plus **one workflow**, plus **one cleanup
pass**, plus **a hard line between the vision and the next 3 months**.

## 2. Goals

1. A single **constitution** file: what the product is, who it's for, what
   makes it different, what's in scope now, what's the longer vision,
   what's frozen.
2. **One** spec/plan workflow, working across Claude Code, Codex, and
   Grok.
3. A **knowledge architecture** with two clean trees: one for agents +
   owner, one published for users.
4. **AI operating rules**: model roles, context hygiene, collision
   prevention, cross-tool shared state, a bounded merge protocol.
5. A **one-time cleanup**: stale worktrees/branches, the doc pile, the
   bot stack, a dependency + Postgres-extension audit.

## 3. Non-goals

- No production code rewrite. This is docs + workflow + cleanup. Library
  swaps are opportunistic, evidence-driven, and never a rewrite of
  working tested code (CLAUDE.md: "Don't propose a rewrite or
  optimization on a hunch").
- No change to the two-database rule, the layered schema, or any ADR
  that records a real technical decision. ADRs are historical record.
- No paid tooling. $0/month holds (OpenSpec MIT; Hugging Face, GitHub
  Pages, DuckDB-WASM free).
- Not unfreezing the models or the site (§4.7 frozen list).
- **Not building** the near-term milestone in this restructure — the
  restructure is steps 1–4 of §9. The milestone (§4.6) is normal feature
  work that follows.
- Scope is **~1 week of sessions.** If it sprawls past that, stop and
  reassess.

---

## 4. Part 1 — Product definition (the constitution's core)

### 4.1 What it is

A free, **commercially-usable** (AGPL-3.0), **honest** MLB research
database: a clean grain ladder of every standard and advanced statistic,
event-derived back to 1910, with every formula cited to its source and
every accuracy/leakage limitation documented.

The benchmark is **baseball.computer** — the closest existing thing. The
goal is to build something **better**: equivalent capability plus more,
innovating on top of what it demonstrated. This is a vision statement,
**not a table-count contest** — "more tables" is an arms race the serious
analyst does not care about. baseball.computer is CC BY-NC-SA: study it
for ideas, **never copy its SQL verbatim** (see memory
`baseball_computer_license`).

### 4.2 Who it's for

**Primary:** the serious analyst — the Tom Tango / Retrosheet
contributor / FanGraphs writer / academic researcher / r/Sabermetrics
power-user tier. Knows the domain cold, writes SQL or Python, values
correctness and historical depth over polish.

**Design test (a forcing function, not the primary user):** could a data
journalist answer a specific question, with a citation, in 5 minutes?

**Secondary:** the data scientist who clones the repo to build their own
predictive models — needs a baseline model + example workflows + a
feature-ready schema. This is the bridge to the revenue and
personal-edge wins (§4.7).

### 4.3 The three differentiators

1. **Commercially usable.** baseball.computer is CC BY-NC-SA — nobody
   can build a product on it. AGPL means they can build on this.
2. **Honesty baked in.** Chronological (never random) validation folds,
   documented leakage failure modes, calibration/uncertainty reporting,
   every formula cited. No one publishes the honest accuracy ceiling and
   the reasons for it.
3. **Full history, one query.** 1910+ at every grain (game → season →
   career, player and team), materialized — not assembled from a dozen
   raw/core tables at request time, and not limited to the Statcast era.

### 4.4 Delivery surface ($0 hosting)

| Layer | What | Host |
|---|---|---|
| Canonical data | Versioned Parquet / DuckDB files | Hugging Face Datasets (primary), GitHub Releases (mirror) |
| Python package | pybaseball-style loader — reads the released Parquet, caches locally, documented API | PyPI (pure-Python, no server) |
| Query UI | DuckDB-WASM static page: SQL runs entirely in the visitor's browser against the Parquet, no server | GitHub Pages |
| Power users | Docker image: one command stands up full Postgres with data loaded | GitHub Container Registry |
| On-ramps | Example notebooks answering real questions; docs site (data dictionary, grain-ladder diagram, formula citations, getting started, honest-limitations page) | repo + GitHub Pages |

**Coverage target:** match what `pybaseball` and `baseballr` expose —
that is the measurable completeness bar for "as much data as the
established libraries."

**Rejected:** a hosted read-only Postgres endpoint — costs money, invites
abuse. Revisit only with revenue.

**Deferred (YAGNI):** a hosted REST API. The Python package + DuckDB-WASM
page + documented SQL cover the "structured, documented way to access the
data" need at $0.

### 4.5 Database engineering standards (near-term rules, not aspirational)

- **All build logic stays in versioned `.sql` files** run by `mlb
  report` / `mlb conform`. **No triggers, no stored procedures** for
  pipeline logic — hidden, hard to test, hard to version, against
  CLAUDE.md's "explicit, boring code" and one-writer-per-table.
- **No SQL strings embedded in Python.** `scripts/lint_sql_ownership.py`
  + the pre-commit hook already enforce this; finish migrating the
  remaining offenders (`_build_games`, ~160 lines — flagged in
  `docs/CODE_REVIEW_2026-09.md`).
- **Normalization by layer:** `core` normalized (dimensions + facts at
  natural grain); `gold` deliberately denormalized flat tables for query
  speed (ADR-057). Do not "fix" `gold` toward normal form.
- **Indices / PK / FK / data types** reviewed for every `gold` table as
  part of publishing it.
- **EXPLAIN / ANALYZE** run on every new or changed `gold` view/query
  before it ships — part of the definition of done.
- **Run tracking + benchmarking** extends the existing `meta.*` tables
  (`ingestion_run`, `model_run`, `experiment`) and `pg_stat_statements`
  (already enabled) — not a new subsystem.
- **Optimize for a target**, not "all hardware": a 16 GB laptop running
  DuckDB on the Parquet, or the Docker Postgres.

### 4.6 Phase milestone — "research database leads" is done when

*Proposed — open to adjustment:*

- Grain backbone relations 1–6 tied out to Baseball-Reference within a
  documented tolerance (counting stats exact or a named delta; rates
  within a few thousandths).
- **Every metric in the catalog cites its source** (a Tango book, an
  academic paper, a Retrosheet analysis, the MLB/FanGraphs glossary) and
  **has a tie-out test**.
- Published to Hugging Face as versioned Parquet with a schema card;
  coverage compared against `pybaseball`/`baseballr` and the gaps
  documented.
- DuckDB-WASM query page live and linked from the README.
- Python loader package published to PyPI.
- Docs site published: data dictionary for every `gold` table, grain
  ladder diagram, every formula with its citation, getting started,
  honest-limitations page.
- At least 5 notebook recipes covering real analyst questions.
- Announced to r/Sabermetrics / the SABR community.

Revenue and the prediction site are re-evaluated **after** this
milestone.

### 4.7 Longer vision (recorded so we stop re-deriving it — NOT near-term)

- **Phase 2 — the prediction ladder.** Real-time predictions at every
  grain: pitch → play → half-inning → inning → game → season, and
  related markets. The grain backbone built now is its foundation.
  (`plans/` had this as markov-v2 / #88 / ladder wave 2.)
- **Phase 3 — exploratory ML program.** Broad technique search:
  ensembles, voting/stacking, parallel/democratic combinations, ANNs /
  deep nets. Publish only what clears the CLAUDE.md bar (chronological
  folds, baselines beaten first, honest calibration); keep the rest as
  documented negative results. Goal: find a real market edge (props,
  totals, CLV — not beating the ~58% game-winner ceiling).
- **Phase 4 — subscriber product.** Betting advice, parlay structuring,
  arbitrage / price-discrepancy alerts. **Legal note:** paid betting
  advice is regulated and varies by US state — real legal homework
  before any of this ships, not a code problem.

### 4.8 Frozen list — no session works these until §4.6 is met

- Prediction models (`model/*.py` new work; existing stays as-is)
- The consumer prediction site
- New data sources not already in `docs/DATA_SOURCES.md`
- The ~110 invented "Engine" composite packages
- markov-v2 / matchup model (#88); prediction ladder wave 2 (#79, #67,
  #81, #57, #58)
- SQLMesh incrementality (Phase 3 of the pipeline plan) unless it
  directly blocks the milestone

Bug fixes to frozen areas are allowed only when they block the milestone
or break `main`.

---

## 5. Part 2 — Methodology

### 5.1 Decision: adopt OpenSpec as the single workflow

`@fission-ai/openspec` (MIT, v1.11+, Node ≥20.19 — satisfied).

**Why OpenSpec over the alternatives:**

- **vs. superpowers-plans:** Claude-only. OpenSpec's slash commands work
  across Claude Code, Codex (`$openspec-propose`), Cursor, Copilot, 30+
  tools — matching the multi-tool reality. Keep superpowers
  `brainstorming` and `test-driven-development` as *skills* invoked
  inside a change; retire `writing-plans` + `plans/` as the plan home.
- **vs. conductor `/spec` `/build` `/prd`:** same Claude-only limit;
  heavier phase gates. Retire as a workflow.
- **vs. GitHub spec-kit:** heavyweight, rigid, Python setup — too much
  ceremony for a solo project.
- **vs. nothing:** "requirements live only in chat history" is exactly
  the circling problem.

### 5.2 Structure OpenSpec creates

```
openspec/
  project.md            # the constitution — §4 of this doc lives here
  specs/                # living source of truth: what the system does today
    <capability>/spec.md
  changes/
    <change-name>/
      proposal.md       # why, what's changing
      specs/            # deltas: ADDED / MODIFIED / REMOVED Requirements
      design.md         # technical approach
      tasks.md          # implementation checklist — THE resume point
    archive/
      YYYY-MM-DD-<change-name>/
```

### 5.3 Migration (part of execution)

1. `openspec init` (targets: Claude Code + Codex).
2. Write `openspec/project.md` from §4 + the still-true parts of
   `docs/NORTH_STAR.md`.
3. In-flight `plans/` and `docs/superpowers/plans/` items → become
   `openspec/changes/<name>/` if active, else archived to `docs/archive/`.
4. Grain backbone (relations 1–6, built) → current state captured as
   `openspec/specs/statistic-backbone/spec.md`.
5. ADRs (`docs/DECISIONS.md`) — untouched. New architectural decisions
   still get an ADR *and* live in an OpenSpec change.
6. `docs/ROADMAP.md` prose → `NOW / NEXT / LATER` in `project.md` + open
   `changes/`.

### 5.4 Work queue

The queue is **open `openspec/changes/` folders + a `NOW / NEXT / LATER`
block in `project.md`.** No Linear, no GitKraken, no separate board. A
GitHub Projects board is optional later if others contribute.

### 5.5 One-agent-per-change rule

- A `changes/<name>/` folder is a **lock**. One tool works one change at
  a time.
- Each change gets its own `git worktree`, created at proposal, removed
  at archive.
- No parallel work on the same change or overlapping files. Two changes
  touching the same module are sequenced, not parallelized.
- Before starting, an agent checks for an existing `changes/<name>/` and
  worktree. If present and not theirs, they stop.

---

## 6. Part 3 — Knowledge architecture

### 6.1 Two trees, two audiences

| Tree | Audience | Contents |
|---|---|---|
| `openspec/` | agents + owner | `project.md`, `specs/`, `changes/` |
| `docs/` → MkDocs Material → GitHub Pages | end users | getting started, grain-ladder diagram, data dictionary, formula citations + sources, notebook index, honest-limitations page |

`docs/DECISIONS.md` (ADRs) and `docs/archive/` are repo-only, unpublished.

### 6.2 Progressive disclosure

- Root `AGENTS.md` / `CLAUDE.md` stay lean routers (the #128 DOX work),
  pointing to `openspec/project.md` as the first read.
- `openspec/project.md` is itself short — routes to `specs/` and the
  `NOW/NEXT/LATER` queue.

### 6.3 Consolidation pass (the cleanup)

Every current `.md` outside `openspec/` and `docs/DECISIONS.md` is
triaged into exactly one of: **keep & move** (into `openspec/` or
`docs/`), **archive** (`docs/archive/<original-path>` + a line in
`docs/archive/README.md`), **delete** (git history retains it).

**Who:** a cheap model (Grok first — SuperGrok auth present; Gemini via
antigravity fallback) does the mechanical triage + first-pass rewrites.
**Claude reviews every move and rewrite before commit.** ADRs never
touched by a cheap model.

### 6.4 Knowledge graph + diagrams

Use the already-installed `understand-anything` plugin: one-time generate
an architecture/knowledge graph + the grain-ladder Mermaid diagram for
the docs site; regenerate on demand, not a live build dependency. Output
lives in `docs/` and is linked from `project.md`.

### 6.5 Vector DB / reranker over docs — deferred

A reranker reorders retrieved chunks; it does not fix contradiction or
sprawl. pgvector over the docs is worth revisiting **only if**, after
consolidation, grep/read retrieval is genuinely failing agents.
Recorded so it isn't re-litigated: **consolidate first, measure, then
decide.**

---

## 7. Part 4 — AI operations

### 7.1 Model roles

| Model | Use for |
|---|---|
| Claude (Sonnet 5 / Opus) | Architecture, spec authoring, code review, correctness-critical code, anything touching the pipeline or schema, all merges |
| Codex | Second-opinion implementation, deep root-cause debugging (`codex-rescue` wired) |
| Grok / Gemini (antigravity) / opencode / kilo | Supervised grunt work: doc triage, boilerplate, first-pass rewrites, bulk mechanical edits, fixture generation |

A cheap model never merges. Its output is a diff Claude or the owner
reviews.

### 7.2 Merge protocol (bounded — replaces "owner merges everything")

Once the owner grants `Bash(gh pr merge:*)` (via `/permissions` or
`.claude/settings.json`), Claude may merge a PR when **all** hold:

- `test` and `secrets` checks are green (the only real gates — §8.3);
- every human review comment and every **Kilo** review comment is
  addressed (CodeRabbit is advisory, not blocking — §8.2);
- the change does not touch a §4.8 frozen area;
- it is Claude's own PR or one the owner asked Claude to land.

Anything outside that (force-push, closing issues, deleting others'
branches, merging into a frozen area) still needs an explicit ask.

### 7.3 Cross-tool shared state (the hard problem)

`openspec/project.md` + `openspec/specs/` **is** the shared memory —
plain markdown, every tool reads it. `changes/<name>/tasks.md` is the
shared per-change state. Claude's `.claude/.../memory/` stays for
Claude-only working notes; anything cross-tool goes in `openspec/`. No
custom sync layer unless the markdown discipline is *shown* to fail.

### 7.4 Context hygiene

- **One change = one session = one PR**, then `/clear`.
- Resume point after `/clear` is `changes/<name>/tasks.md` +
  `proposal.md`, never chat scrollback.
- `/compact` only mid-change when one change needs a long session. Never
  a substitute for writing state to `tasks.md`.

### 7.5 Collision prevention

- The `changes/<name>/` folder + its worktree is the lock (§5.5).
- Stale-worktree sweep is one-time cleanup (§8) and a standing check: a
  worktree with no matching open change is removed.
- One AI tool per change; parallelism is across different changes with
  non-overlapping files, or not at all.

---

## 8. Part 5 — Repo & CI hygiene

### 8.1 One-time cleanup

- Remove all `git worktree` entries with no matching open change (~15).
- Delete local + remote branches already merged or dead.
- Triage open PRs: merge if ready, close with a reason if stale.

### 8.2 Bot stack prune

Current PR bots: CodeRabbit, Kilo Code, Codex, CodeAnt, Macroscope,
Mergify, GitGuardian, Guardrails, Scorecard, pre-commit.ci, plus `ci`.

- **Keep:** `ci` (`test` + `secrets` required), gitleaks/secrets,
  **Kilo Code** as the kept AI reviewer.
- **CodeRabbit:** advisory only — do not wait on it, do not block on it.
- **Turn off:** Codex auto-review (owner already requested); and any of
  CodeAnt / Macroscope / Scorecard / Guardrails / Mergify that have not
  produced a finding leading to a real fix — audit the last ~20 PRs.
- GitGuardian / pre-commit.ci: keep (low noise, real value).

### 8.3 CI gates — documented

`test` and `secrets` are the **only** merge-blocking checks (branch
protection already enforces exactly these). Everything else is advisory.
Written into `project.md` so no session treats an advisory bot's red X
as a blocker.

### 8.4 Dependency + Postgres-extension audit (one-time)

List where the codebase hand-rolls something an actively-maintained
library or a Postgres extension already does well. Swap **only** where
it's a clear win on tested code paths; never a rewrite on a hunch
(CLAUDE.md). Record candidates not taken, with the reason, in an ADR.

---

## 9. Part 6 — Tooling

### 9.1 Adopt now (serves the milestone, low risk)

| Tool | Role | Cost |
|---|---|---|
| **DuckDB** (Python lib + CLI) | Parquet export, local analytics, testing the exact SQL a user runs. Already half the delivery surface. | $0 |
| **`exa` MCP (authenticate it)** | Restores web search/fetch — currently blocked in this environment. | free tier |
| **`postgres-mcp` (installed — formalize use)** | `explain_query`, `analyze_workload_indexes`, `get_top_queries`, `analyze_db_health` — this *is* the EXPLAIN/ANALYZE + index-tuning discipline of §4.5. | $0 |
| **`pandera`** | Dataframe schema validation at pipeline boundaries — serves definition-of-done #4 (schema drift explicit, not swallowed). | $0 |
| **Project skill `add-gold-metric`** | Codifies the repeated 7-step definition-of-done for a new `gold` metric so no step is skipped. Built during execution. | $0 |

### 9.2 Audit candidates (evaluate in §8.4 — do not adopt on faith)

- **Polars** vs pandas — needs a measurement first.
- **pg_partman** vs the hand-rolled ~316 season partitions (already a test-DB pain point).
- **pg_duckdb / duckdb_fdw** — query the Parquet directly from the Docker Postgres.
- **sqlglot** — transpile Postgres ↔ DuckDB SQL for dual-backend delivery.
- **pg_trgm** — fuzzy player-name crosswalk (~0.5% unresolved IDs + mojibake).
- **actionlint**, **hyperfine** — small dev-tooling adds (CI-yaml lint; benchmark timing).

### 9.3 Phase 2+ (real, not now)

- **pgvector** — player/pitch similarity search ("find comparable pitchers").
- **great-expectations / soda-core** — only if the pytest tie-outs outgrow themselves.
- **HuggingFace MCP** — when actively managing the published dataset.

### 9.4 Not adopting

- **pg_cron** — system cron + `mlb` CLI works; no in-DB scheduling.
- **PL/pgSQL / PL/Python for pipeline logic** — §4.5: SQL in `.sql`, Python in Python.
- **More skill/plugin packs** — fragmentation is what we are fixing.
- **TimescaleDB** — already declined (ADR).
- **A baseball-stats MCP** — the data is already ingested.
- **GitHub / filesystem MCP** — `gh` + native tools cover it.

### 9.5 On record for the vision, not now

**DuckDB as a build engine, not just an export format.** The transform
layer (pandas + Postgres SQL today) could become DuckDB-centric —
columnar, free, embeddable, native Parquet, near-Postgres SQL — with
Postgres staying the canonical serving store. A Phase 2 architecture
question; recorded here so it is not re-derived.

---

## 10. Execution plan (≈1 week, sequenced)

Each step is its own OpenSpec change once OpenSpec is initialized; step 1
bootstraps it.

1. **Bootstrap OpenSpec.** `npm i -g @fission-ai/openspec`; `openspec
   init` (Claude Code + Codex); write `openspec/project.md` from §4;
   capture the grain backbone state as
   `openspec/specs/statistic-backbone/spec.md`; update `CLAUDE.md` /
   `AGENTS.md` to name OpenSpec as the workflow and point to
   `project.md`. Commit.
2. **Repo hygiene.** Stale worktree + branch sweep; open-PR triage.
3. **Doc consolidation.** Cheap model triages every `.md`; Claude
   reviews; land the `openspec/` + `docs/` + `docs/archive/` split;
   retire `plans/`, `docs/superpowers/plans/`, `scratchpad/*.md`.
4. **Bot prune + dependency audit.** Audit last ~20 PRs; turn off
   dead-weight bots; document the real gates; produce the dependency +
   extension candidate list.
5. **Docs site + knowledge graph.** MkDocs Material scaffold; `understand-anything`
   generates the architecture graph + grain-ladder diagram; publish to
   GitHub Pages.
6. **Delivery surface (first cut).** DuckDB-based Parquet export of the
   `gold` tables to Hugging Face; DuckDB-WASM query page; Python loader
   package skeleton; one Marimo notebook recipe.

Tooling adoptions from §9.1 land alongside the steps that need them:
DuckDB + `add-gold-metric` skill in step 1's wake, `exa` MCP auth in
step 2, `pandera` at the first pipeline-boundary change, `postgres-mcp`
formalized in step 4's audit.

Steps 1–4 are the "stop the bleeding" week. 5–6 begin the milestone
proper; the rest of §4.6 follows as normal changes.

## 11. Risks

- **OpenSpec is young (v1.11).** MIT + plain markdown — if it fails, the
  `openspec/` folder is still readable docs; we lose the CLI, not the
  content.
- **Cheap-model doc rewrites introduce errors.** Claude reviews every
  move/rewrite; ADRs never touched by a cheap model.
- **The restructure sprawls.** ~1-week bound (§3); steps 1–4 are the
  hard stop; if step 3 alone takes a week, ship the split and defer
  polish.
- **Merge protocol too loose.** §7.2 is bounded to green gates + comments
  addressed + not frozen + Claude's own PRs; anything else still asks.
- **Cross-tool markdown-as-memory fails.** §7.3 builds a sync layer only
  if *shown* to fail, not preemptively.
- **Scope creep returns in conversation.** The vision/milestone/frozen
  split (§4.6–4.8) is the guardrail; every new "I also want" gets sorted
  into a phase before it becomes work.

## 12. Open questions for owner review

1. **Milestone (§4.6)** — enriched with citations + tie-outs + PyPI
   package + coverage-vs-pybaseball. Still the right scope? *(Only open
   question remaining.)*

(Resolved 2026-09-02: docs site → **MkDocs Material** (revised from Quarto
— Quarto needs a ~100 MB binary and the docs are already Markdown; MkDocs
is `uv`-installable and serves Markdown as-is); notebooks → **Marimo**;
AI reviewer → **Kilo**; frozen list → confirmed; all §"push back" items
→ accepted; tooling list §9 → accepted.)

(Prior open questions resolved: AI reviewer → Kilo; frozen list →
confirmed; all §"push back" items → accepted by owner.)
