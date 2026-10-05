Yes. After looking at the governing files you already have, I would **not create a separate “10 Laws” document beside everything else**. That would eventually become another competing source of truth.

The better approach is to turn the review into a **governance hierarchy** where each piece of information has exactly one authoritative home, and everything else points to it.

The core principle should be:

> **One idea → one authoritative owner → references everywhere else → executable verification whenever possible.**

That fits the philosophy of the project itself.

## I would organize the repository like this

| Level | Purpose | Authoritative home | What from our review belongs there |
|---|---|---|---|
| **Mission / Constitution** | What the project is and what must always remain true | `openspec/project.md` | Project North Star, engineering laws/invariants, phase gates, Platform Convergence milestone |
| **Agent operating contract** | How AI/dev tools behave while working | `AGENTS.md` + child `AGENTS.md` | Fix-at-source, evidence-before-rewrite, read owning contracts, never bypass gates |
| **Architecture** | What components exist and their boundaries | `docs/ARCHITECTURE.md` | PostgreSQL/raw/core/gold/DuckDB/ML/markets/research flow |
| **Table/data contracts** | Exact semantics of data structures | `docs/TABLE_CONTRACTS.md` | grain, keys, stable identity, null policy, mutation/replacement behavior |
| **Transformation ownership** | Who calculates what | `docs/SQL_OWNERSHIP.md` | single writer, SQLMesh promotion rules, canonical formula owner |
| **Feature contract** | What models may know and when | `docs/FEATURE_STORE.md` | PIT clocks, availability, readiness, immutable artifacts |
| **Metric contract** | What a statistic means and whether it is trusted | metric YAML + generated docs | citation, formula, status, validation, admission |
| **Target contract** | Exactly what is being predicted | new/expanded OpenSpec spec | `game.home_win:v1`, `player.exact_3_for_3:v1`, cutoff, censoring |
| **Market contract** | What a market quote/contract means | OpenSpec spec + table contracts | contracts, quotes, settlements, target mapping |
| **Research contract** | What makes a result reproducible | `docs/RESEARCH.md` | run IDs, artifact hashes, model version, market timestamp |
| **Decisions** | Why architecture choices were made | `docs/DECISIONS.md` | ADRs such as SQLMesh boundary, stable IDs, framing withheld |
| **Work specification** | What we are changing now | `openspec/changes/<change>/` | proposal/design/tasks/acceptance criteria |
| **Execution tracking** | Discoverability and project management | GitHub Issues/Milestones | links to OpenSpec changes, status, blockers |
| **Proof** | Whether the rule is actually satisfied | tests, SQLMesh audits, CI, doctor, audit, readiness | machine-enforced completion |
| **Evidence log** | What happened during implementation | change `results.md` / research metadata | measurements, tie-outs, migration results |

That gives us a very clean chain:

**North Star → Law → Contract → Change → Task → Test/Gate → Evidence → Done.**

That should become the mental model for the entire repository.

---

# What I would do with the “10 laws”

Keep them.

But put them **inside `openspec/project.md`**, not in a new standalone file.

I would rename them slightly from “laws” to something like:

### Project invariants — the engineering laws

And keep them concise.

Your constitution already contains many of them, but they are currently scattered between `project.md`, `AGENTS.md`, `TABLE_CONTRACTS.md`, `FEATURE_STORE.md`, and various ADRs.

The ten ideas are strong enough to deserve a permanent constitutional section:

**Raw preserves evidence. Core establishes identity. Gold contains deterministic baseball knowledge. Features preserve point-in-time truth. Targets define prediction questions. Models estimate rather than redefine facts. Numbers require evidence before trust. Every derived output has one canonical owner. Build → validate → publish. Failures must be actionable.**

I would not paste the several-paragraph version of each law into `project.md`. Put the short normative rule there, followed by links to the owning contract.

For example:

> **Raw preserves evidence.** Raw data remains source-faithful and is never modified merely to satisfy downstream expectations. Parsing, reconciliation, and interpretation happen downstream. See `TABLE_CONTRACTS.md` and `DATA_SOURCES.md`.

Then the detailed rules remain in those owning documents.

That prevents duplication.

---

# There is one important cleanup we should do at the same time

Our review exposed some **documentation drift**.

For example, `TABLE_CONTRACTS.md` currently says `gold` contains:

> “Derived statistics, point-in-time feature families, and predictions”

while the newer constitution and `FEATURE_STORE.md` say the authoritative model-ready feature layer is DuckDB `feat.*`.

Those two statements are not fully aligned.

That is precisely why this consolidation is valuable.

I would make one OpenSpec change called something like:

**`governance-convergence`**

Its purpose should **not** be to redesign the architecture.

Its purpose should be:

> Reconcile all governing documentation against the current architecture and the holistic review, eliminate contradictory rules, assign every durable rule to one authoritative owner, and convert remaining findings into executable changes.

This should be documentation/governance work first.

---

# The North Stars should exist at two levels

You need **one project North Star**, plus small subsystem North Stars.

The big project North Star belongs in `openspec/project.md`.

I would condense what we wrote to something close to:

> **North Star:** Build a trustworthy, reproducible MLB research and forecasting platform where every published statistic, feature, prediction, and market comparison can be traced from source evidence through canonical facts, validated transformations, point-in-time inputs, model artifacts, and timestamp-matched market observations.

Then each major subsystem gets one sentence at the top of its owning document.

For example, `TABLE_CONTRACTS.md`:

> **Database North Star:** Every stored row has an unambiguous grain, identity, provenance, lifecycle, and interpretation.

`FEATURE_STORE.md`:

> **Feature North Star:** A historical model receives exactly the information that would have been available at its declared prediction time—nothing from the future.

`SQL_OWNERSHIP.md`:

> **Transformation North Star:** Every derived relation and formula has exactly one canonical production owner.

`RESEARCH.md`:

> **Research North Star:** Every published experimental result can be reproduced from immutable inputs, code, features, targets, and model artifacts.

And eventually the market contract:

> **Market North Star:** Every comparison uses the exact contract semantics and executable market observation available at the prediction timestamp.

These are useful because an agent can immediately answer:

> “What is this subsystem trying to guarantee?”

without rereading thirty pages.

---

# Completion criteria should not live only in prose

This is one of the biggest upgrades I recommend.

Every important goal should eventually have **three forms**:

**Human rule:** what must be true.

**Machine check:** how we test it.

**Evidence:** what proves it happened.

For stable IDs, for example:

Human contract:

> Canonical entity IDs remain stable across equivalent conform runs.

Machine check:

```text
test_incremental_full_equivalence
test_game_ids_stable_across_conform
test_player_ids_stable_across_conform
```

Operational check:

```text
mlb audit identity
```

Evidence:

```text
openspec/changes/stable-ids-incremental-conform/results.md
```

Then “done” becomes objective.

The same pattern works everywhere.

For wOBA:

> **Rule:** weights are season-correct and the formula has one owner.
> **Machine proof:** fixture + external tie-out + SQLMesh audit.
> **Evidence:** metric catalog + test reference.
> **Done:** legacy writer deleted and SQLMesh owns the relation.

For framing:

> **Rule:** unsupported framing estimates cannot enter approved models.
> **Machine proof:** readiness rejects disabled metric.
> **Evidence:** failed external tie-out recorded.
> **Done:** either validated replacement exists or feature stays disabled.

That is much stronger than a checklist in a Markdown file.

---

# How the large review should become actual work

Do **not** create 60 unrelated GitHub issues from the 60 implementation steps I gave you.

That would turn the review into noise.

Instead, use about **7–10 capability-level OpenSpec changes**, each with its own detailed task list.

I would organize the major work approximately as:

1. **`governance-convergence`** — integrate North Star/laws, reconcile stale governing docs, establish definitions of done and ownership.
2. **`pipeline-recovery`** — already active; finish it rather than duplicate it.
3. **`stable-ids-incremental-conform`** — already exists; strengthen fingerprinting, staging, equivalence criteria and execute it.
4. **`gold-transformation-convergence`** — single writers, SQLMesh promotion, era-specific wOBA, audits, freeze `game_feature`.
5. **`canonical-event-contract`** — research/design `core.event` and remove repeated raw Retrosheet interpretation.
6. **`metric-admission-contract`** — asset type, trust state, model admission, disabled metrics and Gemini backlog policy.
7. **`target-registry`** — formal prediction-target definitions.
8. **`market-contracts-v1`** — normalized contract/quote/settlement/target mapping.
9. **`research-lineage-v1`** — immutable artifacts and reproducible research runs.
10. **`model-promotion-v1`** — chronological evaluation, calibration, baseline/champion promotion.

Some of those may already overlap existing changes/specs. **Before creating any of them, we should inventory existing OpenSpec changes and merge into existing scopes wherever possible.**

That is important. We should favor consolidation over new folders.

---

# GitHub Issues should be the index, not the specification

This is where I think GitHub can help without becoming another bureaucracy.

Use one GitHub issue for each significant OpenSpec change.

The GitHub issue should be short:

> **Goal:** Stable canonical IDs and incremental conform.
> **Spec:** `openspec/changes/stable-ids-incremental-conform/`
> **Done when:** link to acceptance section.
> **Status:** active / blocked / done.
> **Dependencies:** pipeline-recovery.

Do **not** duplicate all 40 tasks into the GitHub issue.

The tasks stay in:

```text
openspec/changes/<change>/tasks.md
```

That file is already explicitly defined by your repository as the resumable work queue.

GitHub gives us visibility.

OpenSpec gives us precision.

Tests give us truth.

That separation is excellent.

---

# I would introduce one milestone: Platform Convergence

This concept from the review is important enough to become a real project milestone.

It belongs in `openspec/project.md` immediately before aggressive Engine/model expansion.

I would define it approximately as:

> **Platform Convergence is complete when:** pipeline recovery is complete; normal doctor has zero required errors; canonical IDs are stable; incremental and full conform are equivalent; derived relations have declared ownership; known invalid metrics cannot enter approved models; the feature artifact/readiness path is reliable; ingestion provenance is complete enough to identify individual failures; backups are verifiable; and at least one representative deterministic gold model has completed the full SQLMesh promotion/parity/audit/legacy-removal lifecycle.

Notice something important:

This milestone is **not a release number**.

It is an architectural readiness gate.

That gives you a way to say:

> “We are not adding twenty new metrics yet because Platform Convergence isn't green.”

That will protect this project from feature creep.

---

# The Definition of Done should become shared infrastructure

The detailed DoD from the review is too useful to leave buried in a chat.

But again, I would not create `DEFINITION_OF_DONE_2.md`.

You already have a DoD concept in `project.md` and tool-specific one in `CLAUDE.md`.

I would enhance the shared `project.md` definition of done with a concise **contract-impact checklist**.

For every substantial change, ask:

**Did this change alter a grain, identity, source, formula, point-in-time rule, null meaning, ownership, rights classification, public interface, failure mode, or research result?**

If yes, the owning contract must be updated in the same change.

Then require whatever subset applies:

```text
tests
external tie-out
SQLMesh audit
doctor check
audit check
readiness check
EXPLAIN/ANALYZE
docs/contract update
source-rights update
artifact/version bump
```

Not every change needs every check.

The owning spec says which ones apply.

This turns documentation into part of the software rather than an afterthought.

---

# I would also formalize “rule strength”

This will help both humans and AI agents enormously.

Right now the repo has instructions, docs, ADRs, historical plans and implementation notes, and it can be difficult to know which one wins.

I recommend establishing this precedence explicitly in `project.md`:

```text
Project constitution / current OpenSpec specs
        ↓
Accepted ADRs and subsystem contracts
        ↓
Active OpenSpec change design
        ↓
AGENTS operational instructions
        ↓
implementation/docs
        ↓
archived plans and historical notes
```

But with one caveat:

**Reality wins over stale documentation.**

If code/data proves a contract is no longer true, the correct response is not silently ignore the contract. It is:

> identify the discrepancy → determine which behavior is correct → repair the owning contract and implementation together.

Your `CLAUDE.md` already says something very close to this. I would make it a shared project principle rather than only Claude behavior.

---

# `mlb doctor`, `audit`, and `readiness` should encode different contracts

This distinction from our review is important enough to formalize in documentation.

I would define:

**Doctor asks:** “Is the installation operational?”

Examples: database reachable, migrations current, required artifacts exist, ingestion job healthy, backup evidence recent.

**Audit asks:** “Is the data internally correct according to its contracts?”

Examples: duplicates, FKs, impossible values, source coverage, identity inconsistencies, formula/domain invariants.

**Readiness asks:** “Can this dataset legitimately answer this research/model question?”

Examples: PIT leakage, required feature coverage, null explanations, target compatibility, source/rights eligibility.

That gives every check an obvious home.

It also solves the current problem where optional GBM models and experimental metrics can make the whole installation look unhealthy.

---

# We should add one more concept: contract IDs

Not immediately everywhere, but I think this will eventually be very valuable.

Important invariants could receive stable identifiers such as:

```text
ID-01 Stable canonical identity
PIT-01 No future information
SQL-01 Single production writer
MET-01 Cited formula
MET-02 Production admission requires validation
SRC-01 Raw source fidelity
OPS-01 Build-validate-publish
RES-01 Reproducible research run
MKT-01 Timestamp-aligned executable quote
```

Then tests, doctor output, specs and issues can reference them.

For example:

```text
FAIL PIT-01:
feat.game.home_starter_xxx became available after prediction cutoff.
```

Or:

```text
Gold model promotion satisfies SQL-01 and MET-01.
```

This would make the platform easier for both humans and agents to reason about.

I would introduce the scheme slowly rather than renumbering the entire repository now.

---

# The final governance flow I want for this project

When somebody proposes something like:

> “Let's add a pitcher fatigue metric.”

The project should naturally force this sequence:

**Goal:** Why do we need it?

**North Star:** Which project capability does it advance?

**Contract:** What exactly is fatigue? What is the grain? What time is it available? What is NULL?

**Evidence:** Is it a published statistic, a project-derived feature, or an experimental hypothesis?

**Ownership:** What one implementation calculates it?

**OpenSpec:** What change introduces it?

**Tasks:** What must be implemented?

**Tests:** What would prove the calculation is correct?

**Readiness:** Is it allowed in a prediction?

**Research:** Does it improve chronological out-of-sample performance?

**Promotion:** If useful, approve it. If not, preserve the negative result.

That is the process that will stop another “135 Gemini metrics” situation from ever happening again.

---

## What I recommend we do next

I think we should now perform a **governance-convergence pass on the repository**.

Specifically, I would take the holistic review and the North Star blueprint we just produced, compare each important statement against `openspec/project.md`, `AGENTS.md`, `TABLE_CONTRACTS.md`, `SQL_OWNERSHIP.md`, `FEATURE_STORE.md`, `RESEARCH.md`, `DECISIONS.md`, the existing OpenSpec specs, and active changes, and produce a concrete disposition for every finding:

**already governed → strengthen existing wording → move to correct owner → contradiction to resolve → create/change OpenSpec work → turn into automated gate → archive as historical rationale.**

That would give us a **zero-loss migration of the review into the repository** rather than merely pasting another giant document into it.

And there are three improvements I would prioritize during that pass: reconcile the old `gold`/DuckDB feature contract contradiction, establish the Platform Convergence gate in the constitution, and make every remaining review finding traceable to either an existing OpenSpec change or a named future change. Once that mapping exists, essentially nothing from these reviews can fall through the cracks.Yes. After looking at the governing files you already have, I would **not create a separate “10 Laws” document beside everything else**. That would eventually become another competing source of truth.

The better approach is to turn the review into a **governance hierarchy** where each piece of information has exactly one authoritative home, and everything else points to it.

The core principle should be:

> **One idea → one authoritative owner → references everywhere else → executable verification whenever possible.**

That fits the philosophy of the project itself.

## I would organize the repository like this

| Level | Purpose | Authoritative home | What from our review belongs there |
|---|---|---|---|
| **Mission / Constitution** | What the project is and what must always remain true | `openspec/project.md` | Project North Star, engineering laws/invariants, phase gates, Platform Convergence milestone |
| **Agent operating contract** | How AI/dev tools behave while working | `AGENTS.md` + child `AGENTS.md` | Fix-at-source, evidence-before-rewrite, read owning contracts, never bypass gates |
| **Architecture** | What components exist and their boundaries | `docs/ARCHITECTURE.md` | PostgreSQL/raw/core/gold/DuckDB/ML/markets/research flow |
| **Table/data contracts** | Exact semantics of data structures | `docs/TABLE_CONTRACTS.md` | grain, keys, stable identity, null policy, mutation/replacement behavior |
| **Transformation ownership** | Who calculates what | `docs/SQL_OWNERSHIP.md` | single writer, SQLMesh promotion rules, canonical formula owner |
| **Feature contract** | What models may know and when | `docs/FEATURE_STORE.md` | PIT clocks, availability, readiness, immutable artifacts |
| **Metric contract** | What a statistic means and whether it is trusted | metric YAML + generated docs | citation, formula, status, validation, admission |
| **Target contract** | Exactly what is being predicted | new/expanded OpenSpec spec | `game.home_win:v1`, `player.exact_3_for_3:v1`, cutoff, censoring |
| **Market contract** | What a market quote/contract means | OpenSpec spec + table contracts | contracts, quotes, settlements, target mapping |
| **Research contract** | What makes a result reproducible | `docs/RESEARCH.md` | run IDs, artifact hashes, model version, market timestamp |
| **Decisions** | Why architecture choices were made | `docs/DECISIONS.md` | ADRs such as SQLMesh boundary, stable IDs, framing withheld |
| **Work specification** | What we are changing now | `openspec/changes/<change>/` | proposal/design/tasks/acceptance criteria |
| **Execution tracking** | Discoverability and project management | GitHub Issues/Milestones | links to OpenSpec changes, status, blockers |
| **Proof** | Whether the rule is actually satisfied | tests, SQLMesh audits, CI, doctor, audit, readiness | machine-enforced completion |
| **Evidence log** | What happened during implementation | change `results.md` / research metadata | measurements, tie-outs, migration results |

That gives us a very clean chain:

**North Star → Law → Contract → Change → Task → Test/Gate → Evidence → Done.**

That should become the mental model for the entire repository.

---

# What I would do with the “10 laws”

Keep them.

But put them **inside `openspec/project.md`**, not in a new standalone file.

I would rename them slightly from “laws” to something like:

### Project invariants — the engineering laws

And keep them concise.

Your constitution already contains many of them, but they are currently scattered between `project.md`, `AGENTS.md`, `TABLE_CONTRACTS.md`, `FEATURE_STORE.md`, and various ADRs.

The ten ideas are strong enough to deserve a permanent constitutional section:

**Raw preserves evidence. Core establishes identity. Gold contains deterministic baseball knowledge. Features preserve point-in-time truth. Targets define prediction questions. Models estimate rather than redefine facts. Numbers require evidence before trust. Every derived output has one canonical owner. Build → validate → publish. Failures must be actionable.**

I would not paste the several-paragraph version of each law into `project.md`. Put the short normative rule there, followed by links to the owning contract.

For example:

> **Raw preserves evidence.** Raw data remains source-faithful and is never modified merely to satisfy downstream expectations. Parsing, reconciliation, and interpretation happen downstream. See `TABLE_CONTRACTS.md` and `DATA_SOURCES.md`.

Then the detailed rules remain in those owning documents.

That prevents duplication.

---

# There is one important cleanup we should do at the same time

Our review exposed some **documentation drift**.

For example, `TABLE_CONTRACTS.md` currently says `gold` contains:

> “Derived statistics, point-in-time feature families, and predictions”

while the newer constitution and `FEATURE_STORE.md` say the authoritative model-ready feature layer is DuckDB `feat.*`.

Those two statements are not fully aligned.

That is precisely why this consolidation is valuable.

I would make one OpenSpec change called something like:

**`governance-convergence`**

Its purpose should **not** be to redesign the architecture.

Its purpose should be:

> Reconcile all governing documentation against the current architecture and the holistic review, eliminate contradictory rules, assign every durable rule to one authoritative owner, and convert remaining findings into executable changes.

This should be documentation/governance work first.

---

# The North Stars should exist at two levels

You need **one project North Star**, plus small subsystem North Stars.

The big project North Star belongs in `openspec/project.md`.

I would condense what we wrote to something close to:

> **North Star:** Build a trustworthy, reproducible MLB research and forecasting platform where every published statistic, feature, prediction, and market comparison can be traced from source evidence through canonical facts, validated transformations, point-in-time inputs, model artifacts, and timestamp-matched market observations.

Then each major subsystem gets one sentence at the top of its owning document.

For example, `TABLE_CONTRACTS.md`:

> **Database North Star:** Every stored row has an unambiguous grain, identity, provenance, lifecycle, and interpretation.

`FEATURE_STORE.md`:

> **Feature North Star:** A historical model receives exactly the information that would have been available at its declared prediction time—nothing from the future.

`SQL_OWNERSHIP.md`:

> **Transformation North Star:** Every derived relation and formula has exactly one canonical production owner.

`RESEARCH.md`:

> **Research North Star:** Every published experimental result can be reproduced from immutable inputs, code, features, targets, and model artifacts.

And eventually the market contract:

> **Market North Star:** Every comparison uses the exact contract semantics and executable market observation available at the prediction timestamp.

These are useful because an agent can immediately answer:

> “What is this subsystem trying to guarantee?”

without rereading thirty pages.

---

# Completion criteria should not live only in prose

This is one of the biggest upgrades I recommend.

Every important goal should eventually have **three forms**:

**Human rule:** what must be true.

**Machine check:** how we test it.

**Evidence:** what proves it happened.

For stable IDs, for example:

Human contract:

> Canonical entity IDs remain stable across equivalent conform runs.

Machine check:

```text
test_incremental_full_equivalence
test_game_ids_stable_across_conform
test_player_ids_stable_across_conform
```

Operational check:

```text
mlb audit identity
```

Evidence:

```text
openspec/changes/stable-ids-incremental-conform/results.md
```

Then “done” becomes objective.

The same pattern works everywhere.

For wOBA:

> **Rule:** weights are season-correct and the formula has one owner.
> **Machine proof:** fixture + external tie-out + SQLMesh audit.
> **Evidence:** metric catalog + test reference.
> **Done:** legacy writer deleted and SQLMesh owns the relation.

For framing:

> **Rule:** unsupported framing estimates cannot enter approved models.
> **Machine proof:** readiness rejects disabled metric.
> **Evidence:** failed external tie-out recorded.
> **Done:** either validated replacement exists or feature stays disabled.

That is much stronger than a checklist in a Markdown file.

---

# How the large review should become actual work

Do **not** create 60 unrelated GitHub issues from the 60 implementation steps I gave you.

That would turn the review into noise.

Instead, use about **7–10 capability-level OpenSpec changes**, each with its own detailed task list.

I would organize the major work approximately as:

1. **`governance-convergence`** — integrate North Star/laws, reconcile stale governing docs, establish definitions of done and ownership.
2. **`pipeline-recovery`** — already active; finish it rather than duplicate it.
3. **`stable-ids-incremental-conform`** — already exists; strengthen fingerprinting, staging, equivalence criteria and execute it.
4. **`gold-transformation-convergence`** — single writers, SQLMesh promotion, era-specific wOBA, audits, freeze `game_feature`.
5. **`canonical-event-contract`** — research/design `core.event` and remove repeated raw Retrosheet interpretation.
6. **`metric-admission-contract`** — asset type, trust state, model admission, disabled metrics and Gemini backlog policy.
7. **`target-registry`** — formal prediction-target definitions.
8. **`market-contracts-v1`** — normalized contract/quote/settlement/target mapping.
9. **`research-lineage-v1`** — immutable artifacts and reproducible research runs.
10. **`model-promotion-v1`** — chronological evaluation, calibration, baseline/champion promotion.

Some of those may already overlap existing changes/specs. **Before creating any of them, we should inventory existing OpenSpec changes and merge into existing scopes wherever possible.**

That is important. We should favor consolidation over new folders.

---

# GitHub Issues should be the index, not the specification

This is where I think GitHub can help without becoming another bureaucracy.

Use one GitHub issue for each significant OpenSpec change.

The GitHub issue should be short:

> **Goal:** Stable canonical IDs and incremental conform.
> **Spec:** `openspec/changes/stable-ids-incremental-conform/`
> **Done when:** link to acceptance section.
> **Status:** active / blocked / done.
> **Dependencies:** pipeline-recovery.

Do **not** duplicate all 40 tasks into the GitHub issue.

The tasks stay in:

```text
openspec/changes/<change>/tasks.md
```

That file is already explicitly defined by your repository as the resumable work queue.

GitHub gives us visibility.

OpenSpec gives us precision.

Tests give us truth.

That separation is excellent.

---

# I would introduce one milestone: Platform Convergence

This concept from the review is important enough to become a real project milestone.

It belongs in `openspec/project.md` immediately before aggressive Engine/model expansion.

I would define it approximately as:

> **Platform Convergence is complete when:** pipeline recovery is complete; normal doctor has zero required errors; canonical IDs are stable; incremental and full conform are equivalent; derived relations have declared ownership; known invalid metrics cannot enter approved models; the feature artifact/readiness path is reliable; ingestion provenance is complete enough to identify individual failures; backups are verifiable; and at least one representative deterministic gold model has completed the full SQLMesh promotion/parity/audit/legacy-removal lifecycle.

Notice something important:

This milestone is **not a release number**.

It is an architectural readiness gate.

That gives you a way to say:

> “We are not adding twenty new metrics yet because Platform Convergence isn't green.”

That will protect this project from feature creep.

---

# The Definition of Done should become shared infrastructure

The detailed DoD from the review is too useful to leave buried in a chat.

But again, I would not create `DEFINITION_OF_DONE_2.md`.

You already have a DoD concept in `project.md` and tool-specific one in `CLAUDE.md`.

I would enhance the shared `project.md` definition of done with a concise **contract-impact checklist**.

For every substantial change, ask:

**Did this change alter a grain, identity, source, formula, point-in-time rule, null meaning, ownership, rights classification, public interface, failure mode, or research result?**

If yes, the owning contract must be updated in the same change.

Then require whatever subset applies:

```text
tests
external tie-out
SQLMesh audit
doctor check
audit check
readiness check
EXPLAIN/ANALYZE
docs/contract update
source-rights update
artifact/version bump
```

Not every change needs every check.

The owning spec says which ones apply.

This turns documentation into part of the software rather than an afterthought.

---

# I would also formalize “rule strength”

This will help both humans and AI agents enormously.

Right now the repo has instructions, docs, ADRs, historical plans and implementation notes, and it can be difficult to know which one wins.

I recommend establishing this precedence explicitly in `project.md`:

```text
Project constitution / current OpenSpec specs
        ↓
Accepted ADRs and subsystem contracts
        ↓
Active OpenSpec change design
        ↓
AGENTS operational instructions
        ↓
implementation/docs
        ↓
archived plans and historical notes
```

But with one caveat:

**Reality wins over stale documentation.**

If code/data proves a contract is no longer true, the correct response is not silently ignore the contract. It is:

> identify the discrepancy → determine which behavior is correct → repair the owning contract and implementation together.

Your `CLAUDE.md` already says something very close to this. I would make it a shared project principle rather than only Claude behavior.

---

# `mlb doctor`, `audit`, and `readiness` should encode different contracts

This distinction from our review is important enough to formalize in documentation.

I would define:

**Doctor asks:** “Is the installation operational?”

Examples: database reachable, migrations current, required artifacts exist, ingestion job healthy, backup evidence recent.

**Audit asks:** “Is the data internally correct according to its contracts?”

Examples: duplicates, FKs, impossible values, source coverage, identity inconsistencies, formula/domain invariants.

**Readiness asks:** “Can this dataset legitimately answer this research/model question?”

Examples: PIT leakage, required feature coverage, null explanations, target compatibility, source/rights eligibility.

That gives every check an obvious home.

It also solves the current problem where optional GBM models and experimental metrics can make the whole installation look unhealthy.

---

# We should add one more concept: contract IDs

Not immediately everywhere, but I think this will eventually be very valuable.

Important invariants could receive stable identifiers such as:

```text
ID-01 Stable canonical identity
PIT-01 No future information
SQL-01 Single production writer
MET-01 Cited formula
MET-02 Production admission requires validation
SRC-01 Raw source fidelity
OPS-01 Build-validate-publish
RES-01 Reproducible research run
MKT-01 Timestamp-aligned executable quote
```

Then tests, doctor output, specs and issues can reference them.

For example:

```text
FAIL PIT-01:
feat.game.home_starter_xxx became available after prediction cutoff.
```

Or:

```text
Gold model promotion satisfies SQL-01 and MET-01.
```

This would make the platform easier for both humans and agents to reason about.

I would introduce the scheme slowly rather than renumbering the entire repository now.

---

# The final governance flow I want for this project

When somebody proposes something like:

> “Let's add a pitcher fatigue metric.”

The project should naturally force this sequence:

**Goal:** Why do we need it?

**North Star:** Which project capability does it advance?

**Contract:** What exactly is fatigue? What is the grain? What time is it available? What is NULL?

**Evidence:** Is it a published statistic, a project-derived feature, or an experimental hypothesis?

**Ownership:** What one implementation calculates it?

**OpenSpec:** What change introduces it?

**Tasks:** What must be implemented?

**Tests:** What would prove the calculation is correct?

**Readiness:** Is it allowed in a prediction?

**Research:** Does it improve chronological out-of-sample performance?

**Promotion:** If useful, approve it. If not, preserve the negative result.

That is the process that will stop another “135 Gemini metrics” situation from ever happening again.

---

## What I recommend we do next

I think we should now perform a **governance-convergence pass on the repository**.

Specifically, I would take the holistic review and the North Star blueprint we just produced, compare each important statement against `openspec/project.md`, `AGENTS.md`, `TABLE_CONTRACTS.md`, `SQL_OWNERSHIP.md`, `FEATURE_STORE.md`, `RESEARCH.md`, `DECISIONS.md`, the existing OpenSpec specs, and active changes, and produce a concrete disposition for every finding:

**already governed → strengthen existing wording → move to correct owner → contradiction to resolve → create/change OpenSpec work → turn into automated gate → archive as historical rationale.**

That would give us a **zero-loss migration of the review into the repository** rather than merely pasting another giant document into it.

And there are three improvements I would prioritize during that pass: reconcile the old `gold`/DuckDB feature contract contradiction, establish the Platform Convergence gate in the constitution, and make every remaining review finding traceable to either an existing OpenSpec change or a named future change. Once that mapping exists, essentially nothing from these reviews can fall through the cracks.
