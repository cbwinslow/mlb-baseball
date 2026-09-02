# Project restructure — constitution, workflow, knowledge architecture

Date: 2026-09-02
Status: DRAFT — awaiting owner review
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

The fix is **one canonical source of truth that every session is
required to read first**, plus **one workflow**, plus **one cleanup
pass**. Not a new tool bolted onto the pile.

## 2. Goals

1. A single **constitution** file: what the product is, who it's for, what
   makes it different, what's in scope now, what's frozen.
2. **One** spec/plan workflow, working across Claude Code, Codex, and
   Grok.
3. A **knowledge architecture** with two clean trees: one for agents +
   owner, one published for users.
4. **AI operating rules**: model roles, context hygiene, collision
   prevention, cross-tool shared state.
5. A **one-time cleanup**: stale worktrees/branches, the doc pile, the
   bot stack.

## 3. Non-goals

- No production code rewrite. This is docs + workflow + cleanup.
- No change to the two-database rule, the layered schema, or any ADR
  that records a real technical decision. ADRs are historical record and
  stay as-is.
- No paid tooling. $0/month budget holds (OpenSpec is MIT/free; Hugging
  Face, GitHub Pages, DuckDB-WASM are free).
- Not unfreezing the models or the site (see the frozen list, §4.6).
- Scope is **~1 week of sessions.** If it sprawls past that, we have
  recreated the problem — stop and reassess.

---

## 4. Part 1 — Product definition (the constitution's core)

### 4.1 What it is

A free, **commercially-usable** (AGPL-3.0), **honest** MLB research
database: a clean grain ladder of every standard and advanced statistic,
event-derived back to 1910, with every formula cited to its source and
every accuracy/leakage limitation documented.

### 4.2 Who it's for

**Primary:** the serious analyst — the Tom Tango / Retrosheet
contributor / FanGraphs writer / academic-researcher / r/Sabermetrics
power-user tier. Knows the domain cold, writes SQL or Python, values
correctness and historical depth over polish.

**Design test (not the primary user, but a forcing function):** could a
data journalist answer a specific question, with a citation, in 5
minutes?

**Secondary:** the data scientist who clones the repo to build their own
predictive models — needs a baseline model + example workflows + a clean
feature-ready schema. This is the bridge to the revenue and personal-edge
wins, addressed in a later phase.

### 4.3 The three differentiators

1. **Commercially usable.** The closest existing thing,
   baseball.computer, is CC BY-NC-SA — nobody can build a product on it.
   AGPL means they can build on this.
2. **Honesty baked in.** Chronological (never random) validation folds,
   documented leakage failure modes, calibration/uncertainty reporting,
   every formula cited. No one else publishes the honest accuracy
   ceiling and the reasons for it.
3. **Full history, one query.** 1910+ at every grain (game → season →
   career, player and team), materialized — not assembled from a dozen
   raw/core tables at request time, and not limited to the Statcast era.

### 4.4 Delivery surface ($0 hosting)

| Layer | What | Host |
|---|---|---|
| Canonical data | Versioned Parquet / DuckDB files | Hugging Face Datasets (primary), GitHub Releases (mirror) |
| Query UI | DuckDB-WASM static page: type SQL, runs entirely in the visitor's browser against the Parquet files, no server | GitHub Pages |
| Power users | Docker image: one command stands up full Postgres with data loaded | GitHub Container Registry |
| On-ramps | Example notebooks (Marimo/Jupyter) answering real questions; MkDocs docs site (data dictionary, grain-ladder diagram, formula citations, getting started) | repo + GitHub Pages |

Deferred (YAGNI): a `pip install`-able loader package. Notebooks show
`duckdb.read_parquet(url)` until someone asks for the package.

The hosted-read-only-DB option is **rejected** — it costs money to run
and invites abuse.

### 4.5 Phase milestone — "research database leads" is done when

*Proposed — open to adjustment during review:*

- Grain backbone relations 1–6 tied out to Baseball-Reference within a
  documented tolerance (counting stats exact or a named delta; rate
  stats within a few thousandths).
- Published to Hugging Face as versioned Parquet, with a schema card.
- DuckDB-WASM query page live and linked from the README.
- Docs site published: data dictionary for every `gold` table, grain
  ladder diagram, every formula with its citation, "getting started".
- At least 5 notebook recipes covering real analyst questions.
- Announced to r/Sabermetrics / the SABR community.

Revenue and the prediction site get re-evaluated **after** this
milestone, not before.

### 4.6 Frozen list — no session works these until the milestone is met

- Prediction models (`model/*.py` new work; existing stays as-is)
- The consumer prediction site
- New data sources not already in `docs/DATA_SOURCES.md`
- The ~110 invented "Engine" composite packages
- markov-v2 / matchup model (#88)
- Prediction ladder wave 2 (#79, #67, #81, #57, #58)
- SQLMesh incrementality (Phase 3) unless it directly blocks the
  milestone

Bug fixes to frozen areas are allowed only when they block the
milestone or break `main`.

---

## 5. Part 2 — Methodology

### 5.1 Decision: adopt OpenSpec as the single workflow

`@fission-ai/openspec` (MIT, v1.11+, Node ≥20.19 — satisfied).

**Why OpenSpec over the alternatives:**

- **vs. superpowers-plans:** superpowers is Claude-only. OpenSpec's
  slash commands work across Claude Code, Codex (`$openspec-propose`),
  Cursor, Copilot, and 30+ tools — matching the multi-tool reality.
  Keep superpowers `brainstorming` and `test-driven-development` as
  *skills* invoked inside an OpenSpec change; retire `writing-plans` +
  `plans/` as the plan home.
- **vs. conductor `/spec` `/build` `/prd`:** same Claude-only limitation;
  also a heavier phase-gated flow. Retire as a workflow.
- **vs. GitHub spec-kit:** heavyweight, rigid phase gates, Python setup.
  Explicitly rejected by OpenSpec's own comparison and by us — too much
  ceremony for a solo project.
- **vs. nothing:** "requirements live only in chat history" is precisely
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
      YYYY-MM-DD-<change-name>/   # completed changes
```

### 5.3 Migration (part of execution)

1. `openspec init` (targets: Claude Code + Codex).
2. Write `openspec/project.md` from §4 of this doc + the still-true parts
   of `docs/NORTH_STAR.md`.
3. In-flight `plans/` and `docs/superpowers/plans/` items → become
   `openspec/changes/<name>/` if active, else archived to `docs/archive/`.
4. The grain backbone (relations 1–6, already built) → its current state
   captured as `openspec/specs/statistic-backbone/spec.md`.
5. ADRs (`docs/DECISIONS.md`) — untouched. They are historical record.
   New architectural decisions still get an ADR *and* live in an
   OpenSpec change.
6. `docs/ROADMAP.md` prose → the `NOW / NEXT / LATER` block in
   `project.md` + open `changes/`.

### 5.4 Work queue

The queue is: **open `openspec/changes/` folders + a `NOW / NEXT /
LATER` block in `project.md`.** No Linear, no GitKraken, no separate
board. A GitHub Projects board is optional later if multiple people
contribute; not now.

### 5.5 One-agent-per-change rule

- A `changes/<name>/` folder is a **lock**. One tool works one change at
  a time.
- Each change gets its own `git worktree`, created at proposal, removed
  at archive.
- No parallel work on the same change or the same files. If two changes
  would touch the same module, they are sequenced, not parallelized.
- Cross-tool: before starting, an agent checks for an existing
  `changes/<name>/` and an existing worktree. If present and not theirs,
  they stop.

---

## 6. Part 3 — Knowledge architecture

### 6.1 Two trees, two audiences

| Tree | Audience | Contents |
|---|---|---|
| `openspec/` | agents + owner | `project.md` (constitution), `specs/` (what the system does), `changes/` (active work) |
| `docs/` → published via MkDocs to GitHub Pages | end users | getting started, grain-ladder diagram, data dictionary, formula citations + sources, notebook index, honest-limitations page |

`docs/DECISIONS.md` (ADRs) and `docs/archive/` are repo-only, not
published.

### 6.2 Progressive disclosure

- Root `AGENTS.md` / `CLAUDE.md` stay lean routers (the #128 DOX work
  already did this). They point to `openspec/project.md` as the first
  read.
- `openspec/project.md` is itself short — it routes to `specs/` and the
  `NOW/NEXT/LATER` queue.

### 6.3 Consolidation pass (the cleanup)

Every current `.md` outside `openspec/` and `docs/DECISIONS.md` gets
triaged into exactly one of:

- **Keep & move** → into `openspec/` or `docs/` (user-facing).
- **Archive** → `docs/archive/<original-path>` with a one-line note in
  `docs/archive/README.md` saying what it was and why it's frozen.
- **Delete** → git history retains it.

**Who does the work:** a cheap model (Grok first — SuperGrok auth
present, `grok-build` inherits Claude's config/skills; Gemini via
antigravity as fallback) does the mechanical triage + first-pass
rewrites into a proposed structure. **Claude reviews every move and
every rewrite before it's committed.** No unreviewed doc changes.

### 6.4 Knowledge graph + diagrams

Use the already-installed `understand-anything` plugin:

- One-time: generate an architecture/knowledge graph of the codebase and
  the `gold` schema; generate the grain-ladder diagram (Mermaid) for the
  docs site.
- Regenerate on demand (e.g. after a schema change), not as a live
  build-time dependency.
- Output lives in `docs/` (published) and is linked from
  `openspec/project.md`.

### 6.5 Vector DB / reranker over docs — deferred

A reranker reorders retrieved chunks; it does not fix contradiction or
sprawl. A pgvector table over the docs (Postgres is already
pgvector-capable) is worth revisiting **only if**, after consolidation,
the doc set is still large enough that grep/read retrieval is genuinely
failing agents. Decision recorded so it isn't re-litigated: **consolidate
first, measure, then decide.**

---

## 7. Part 4 — AI operations

### 7.1 Model roles

| Model | Use for |
|---|---|
| Claude (Sonnet 5 / Opus) | Architecture, spec authoring, code review, correctness-critical code, anything touching the pipeline or schema |
| Codex | Second-opinion implementation, deep root-cause debugging (`codex-rescue` already wired) |
| Grok / Gemini (antigravity) / opencode / kilo | Supervised grunt work: doc triage, boilerplate, first-pass rewrites, bulk mechanical edits, fixture generation |

Rule: a cheap model never merges. Its output is a diff Claude (or the
owner) reviews.

### 7.2 Cross-tool shared state (the hard problem)

`openspec/project.md` + `openspec/specs/` **is** the shared memory —
plain markdown, every tool reads it. `openspec/changes/<name>/tasks.md`
is the shared per-change state.

- Claude's `.claude/.../memory/` stays for **Claude-only working
  notes**. Anything that matters to another tool goes in `openspec/`.
- No custom sync layer is built unless the markdown-as-shared-state
  discipline is shown to fail in practice.

### 7.3 Context hygiene

- **One change = one session = one PR**, then `/clear`.
- The resume point after a `/clear` is `openspec/changes/<name>/tasks.md`
  + `proposal.md`, never chat scrollback.
- `/compact` only mid-change when a single change genuinely needs a long
  session. Never as a substitute for writing state to `tasks.md`.
- Start each change from a clean context with the proposal + tasks as
  the brief.

### 7.4 Collision prevention

- The `changes/<name>/` folder + its worktree is the lock (§5.5).
- Stale worktree sweep is part of the one-time cleanup (§8) and becomes a
  standing check: a worktree with no matching open change is removed.
- Only one AI tool runs against the repo at a time on a given change.
  Parallelism is across *different* changes with non-overlapping files,
  or not at all.

---

## 8. Part 5 — Repo & CI hygiene

### 8.1 One-time cleanup

- Remove all `git worktree` entries with no matching open OpenSpec change
  (~15 currently).
- Delete local + remote branches already merged or dead.
- Triage open PRs: merge if ready, close with a reason if stale.

### 8.2 Bot stack prune

Current PR bots: CodeRabbit, Kilo Code, Codex (chatgpt-codex-connector),
CodeAnt, Macroscope, Mergify, GitGuardian, Guardrails, Scorecard,
pre-commit.ci, plus the `ci` workflow.

- **Keep:** `ci` (`test` + `secrets` required), gitleaks/secrets,
  **one** AI reviewer — CodeRabbit (most established, inline
  suggestions).
- **Turn off:** Codex auto-review (owner already requested — see the
  Codex settings steps), and any of Kilo / CodeAnt / Macroscope /
  Scorecard / Guardrails / Mergify that have never produced a finding
  that led to a real fix. Audit the last ~20 PRs to decide each.
- GitGuardian / pre-commit.ci: keep (low noise, real value).

### 8.3 CI gates — documented

`test` and `secrets` are the **only** merge-blocking checks (branch
protection already enforces exactly these). Everything else is advisory.
This is written into `openspec/project.md` so no session treats an
advisory bot's red X as a blocker.

---

## 9. Execution plan (≈1 week, sequenced)

Each step is its own OpenSpec change once OpenSpec is initialized; step 1
bootstraps it.

1. **Bootstrap OpenSpec.** `npm i -g @fission-ai/openspec`; `openspec
   init` (Claude Code + Codex); write `openspec/project.md` from §4;
   capture the grain backbone's current state as
   `openspec/specs/statistic-backbone/spec.md`. Commit.
2. **Repo hygiene.** Stale worktree + branch sweep; open-PR triage.
   (Fast, unblocks everything.)
3. **Doc consolidation.** Cheap model triages every `.md`; Claude
   reviews; land the `openspec/` + `docs/` + `docs/archive/` split.
   Retire `plans/`, `docs/superpowers/plans/`, `scratchpad/*.md`.
4. **Bot prune.** Audit last ~20 PRs; turn off the dead-weight bots;
   document the real gates in `project.md`.
5. **Docs site + knowledge graph.** MkDocs scaffold; `understand-anything`
   generates the architecture graph + grain-ladder diagram; publish to
   GitHub Pages.
6. **Delivery surface (first cut).** Parquet export of the `gold` tables
   to Hugging Face; DuckDB-WASM query page; one notebook recipe. (The
   rest of the milestone in §4.5 follows as normal feature changes.)

Steps 1–4 are the "stop the bleeding" week. 5–6 begin the milestone
proper.

## 10. Risks

- **OpenSpec is young (v1.11).** Mitigation: it's MIT and plain
  markdown — if it doesn't work out, the `openspec/` folder is still
  readable docs and we've lost only the CLI, not the content.
- **Cheap-model doc rewrites introduce errors.** Mitigation: Claude
  reviews every move and rewrite; ADRs are never touched by a cheap
  model.
- **The restructure itself sprawls.** Mitigation: the ~1-week bound in
  §3; steps 1–4 are the hard stop; if step 3 alone takes a week, we ship
  the split and defer polish.
- **Three-workflow retirement leaves dangling skill references.**
  Mitigation: `CLAUDE.md` / `AGENTS.md` updated in step 1 to name
  OpenSpec as the workflow; other skills stay available but
  non-default.
- **Cross-tool markdown-as-memory discipline fails.** Mitigation: §7.2
  says we build a sync layer only if it's *shown* to fail — not
  preemptively.

## 11. Open questions for owner review

1. **Milestone (§4.5)** — is the proposed "done when" list right? Too
   much / too little?
2. **Frozen list (§4.6)** — anything to add or release?
3. **AI reviewer (§8.2)** — CodeRabbit is the proposed keeper. Prefer a
   different one, or keep two?
4. **Docs site generator** — MkDocs Material is proposed. Any preference
   (Docusaurus, mdBook, Quarto — Quarto is notebook-native and could be
   relevant given the notebook recipes)?
5. **Notebook tool** — Marimo (reactive, git-friendly) vs. classic
   Jupyter for the recipes?
