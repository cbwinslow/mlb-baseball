## Context

See `proposal.md` - Why. Relevant current state:

- `mlb_baseball/model/` has ~155 modules; citations, when they exist, live only
  as ADR cross-references in docstrings/comments (`(CAT-02, ADR-045)`), pointing
  into `docs/DECISIONS.md`'s ~300-entry chronological log — not a lookup table.
- Some metrics already have a real external tie-out (e.g. the FanGraphs Guts!
  constants conform, the Baseball-Reference bulk cross-check, the MLB-box-score
  play-by-play tie-out). Most have only formula-correctness tests: a test
  hand-derives the expected value by the same arithmetic the code uses, which
  proves the implementation matches its own spec, not that it matches an
  independent published number. This distinction is load-bearing for the
  `validated` vs `implemented-untested` status split in the spec — collapsing
  it would make the catalog dishonest in exactly the way it exists to prevent.
- `openspec/project.md`'s Phase B step 1 already names this exact inventory as
  a planned, gated future step. This design pulls it forward as documentation
  only (see proposal's Impact).
- Existing conventions this design must follow: no SQL strings in Python
  (`scripts/lint_sql_ownership.py`), named `.sql` resources under
  `mlb_baseball/sql/`, `meta.*` as the existing home for cross-cutting
  operational tables, MkDocs Material as the adopted docs-site tool.

## Goals / Non-Goals

**Goals:**
- Prove the catalog pattern end-to-end (schema → CI check → `meta.metric` →
  docs page) with a first batch of well-evidenced entries.
- Make the public/internal line mechanical and auditable, not a judgment call
  repeated ad hoc per file.
- Leave a repeatable, boundedly-sized procedure for triaging the remaining
  modules in later batches — this change does not attempt all ~155 in one PR.

**Non-Goals:**
- Triaging every one of the ~155 `model/` modules in this change (see Risks).
- Any change to a metric's formula, tuned parameter, or computed value.
- Building the full MkDocs page design/navigation — a minimal generated page
  is enough to prove the pattern; visual polish is a follow-up.
- Deciding Phase B's broader "keep / add-harness / rebuild-on-demand /
  archive" disposition for every module — this change only classifies
  `visibility` and validation `status`, which is a narrower question.

## Decisions

**1. One YAML file per metric, under `mlb_baseball/metrics/<name>.yaml`.**
Alternative considered: a single big YAML/JSON file. Rejected — 155+ entries
in one file is an unreviewable diff and a merge-conflict magnet across
batched PRs; one file per metric gives small, independent, git-blamable
reviews, matching how `mlb_baseball/sql/*.sql` already does one file per
named resource.

Schema (validated by a small `jsonschema`-based check, not invented tooling):
```yaml
name: catcher_framing_runs
definition: >
  Plain-English, 1-3 sentences, no unexplained jargon.
formula: mlb_baseball/model/framing.py::compute   # or an inline formula string
citation: "Judge, FanGraphs Called Strikes Above Average methodology, 2016"
grain: player-season          # or game, career, team-season, etc.
layer: model                  # gold | feat | model
status: implemented-untested  # published | validated | implemented-untested | negative-result | archived
visibility: internal          # public | internal
test_ref: tests/integration/test_model_framing.py::test_...  # required if status: validated
notes: >
  Optional - known limitations, open questions, why status/visibility is what it is.
```

**2. `visibility` is derived from a rule, checked, not asserted freely.**
The CI check flags (does not silently accept) any entry whose `citation`
looks like it names a real public source (matches a small allow-list of
known publications/sites already cited elsewhere in the repo, e.g. in
`docs/DECISIONS.md`) but is marked `visibility: internal`, or the reverse —
an entry with no real citation marked `public`. This is a lint, not a
hard gate (judgment calls exist), but it makes drift visible in review
instead of silent.

**3. `status: validated` requires a named, currently-passing, non-self-
referential test.** The CI check parses `test_ref`, confirms the test exists,
and (best-effort, via a static check for a hardcoded comparison value or a
call into a documented external fixture) flags a `validated` entry whose test
only hand-derives its own expected value in the test body — that pattern is
`implemented-untested`'s test, not `validated`'s, per this change's own
distinction (see Context). A human (or reviewing agent) makes the final call;
the check narrows the review, it does not replace it.

**4. `meta.metric` is generated, not hand-maintained.** A migration creates
the table (id `text PRIMARY KEY` = the YAML `name`, remaining fields as typed
columns, `visibility`/`status` as `text` with a `CHECK` constraint enumerating
the allowed values, `loaded_at timestamptz`). A loader script
(`mlb_baseball/catalog.py`, mirroring existing loader patterns) reads every
`mlb_baseball/metrics/*.yaml`, validates against the schema, and
`TRUNCATE`+`INSERT`s via a named `mlb_baseball/sql/meta_metric_upsert.sql` —
same idempotent full-rebuild pattern as every other `gold`/`meta` build in
this project, wired into `mlb report` (or a new `mlb catalog` verb — decided
in tasks.md) so it never drifts from the YAML source of truth.

**5. The public docs page is generated from `meta.metric` filtered to
`visibility = 'public'`**, sorted `validated` before `implemented-untested`
before `published`, each with a plain-English blurb and citation link. A
minimal Markdown generator is enough for this change; MkDocs Material
navigation/styling integration is a follow-up, not blocked by this change.

**6. Established libraries, not invented ones.** Schema validation uses
`jsonschema` or `pydantic` (either is already an ecosystem-standard choice;
pick whichever has less new-dependency footprint given what's already in
`pyproject.toml` — check before adding). YAML parsing uses `PyYAML` (already
a transitive dependency of several tools in this stack; confirm before
treating it as new). No bespoke DSL, no adopted "metrics catalog" product
(DataHub/Cube/dbt Semantic Layer) — all are built for teams, not one person's
repo, and would be new infra to operate for a problem a few hundred lines of
project-owned code already solves. This follows the project's "established
solutions first" rule while still not overbuilding for a team of one.

## Risks / Trade-offs

- **[Risk] Attempting all ~155 modules in one PR produces an unreviewable
  diff and stalls.** → Mitigation: this change ships tooling + a first batch
  of ~15-20 high-confidence, already-evidenced metrics (FanGraphs Guts!
  constants, park factors, WAR, wOBA/wRC+, comprehensive baserunning,
  catcher framing, Elo, win probability/leverage — chosen because their
  citation and validation status are already known from this session's
  research, not guessed). The remaining modules are triaged in later,
  independently-sized batches (tracked in `openspec/project.md`'s NEXT queue,
  not re-litigated per batch in this file).
- **[Risk] A batch-triage pass mis-classifies `visibility` for a metric that
  is actually tuned/proprietary despite citing a real paper.** → Mitigation:
  the CI lint (Decision 2) surfaces the ambiguous cases for human review;
  default to `internal` when genuinely unsure — the cost of under-claiming
  public is much lower than the cost of leaking Engine IP.
  publishing something that shouldn't be.
- **[Risk] `status: validated` gets over-claimed because a formula-
  correctness test looks superficially like a tie-out.** → Mitigation:
  Decision 3's check plus an explicit spec requirement (see
  `specs/metric-catalog/spec.md`) that `validated` names an external,
  independently-sourced comparison value, not a value the test itself
  derives.
- **[Trade-off] One YAML file per metric is more files to manage than one
  big table.** Accepted — matches the project's existing one-file-per-named-
  resource convention and keeps batched PRs reviewable.

## Migration Plan

1. Add the YAML schema + `mlb_baseball/metrics/` directory + `mlb_baseball/catalog.py` loader + `meta_metric_upsert.sql`.
2. Migration: `CREATE TABLE meta.metric` (additive, no data loss possible — table is new).
3. CI check script + pre-commit/CI wiring (advisory first merge, then required once the first batch is in, so it does not block unrelated PRs mid-migration).
4. First batch of ~15-20 flagship entries, hand-written with real evidence.
5. Generate `meta.metric` rows + the first cut of the public docs page from that batch; verify against the spec's scenarios.
6. Record the remaining-module triage as a tracked, batched NEXT-queue item in `openspec/project.md` (not blocked on this change's archive).
Rollback: `DROP TABLE meta.metric`; delete the YAML directory and loader. No other system depends on either yet, so rollback has no downstream effect.

## Open Questions

- Exact split of "loader in `mlb report`" vs. a new standalone `mlb catalog`
  verb — either is fine; resolved in `tasks.md` rather than blocking this
  design (does not change the spec or the schema).
- Whether the CI catalog-completeness check ships as a required check
  immediately or advisory-then-required after the first full pass — a rollout
  sequencing detail, not a design-level decision.
