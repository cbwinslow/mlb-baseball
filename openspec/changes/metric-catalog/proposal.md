## Why

`mlb_baseball/model/` holds ~155 files (~27,600 lines, 45 integration test
files) implementing real, mostly-published sabermetrics — WAR, wOBA/wRC+,
comprehensive baserunning value, catcher framing, win probability/leverage,
Elo, park factors, pitch tunneling, and more — much of it already wired into
production (`gold.game_feature` alone carries 289 columns / ~218k rows sourced
from this code). None of it is indexed anywhere: each metric's citation lives
only in a scattered numbered decision (`docs/DECISIONS.md`, referenced by code
comments like `(CAT-02, ADR-045)`), and there is no single page or table a
researcher — or the owner — can browse to see what exists, where it lives, and
whether it has been validated against a known-good published value.

This invisibility has a second, compounding cost: `openspec/project.md`
currently gates *all* of `model/` behind "Phase B — the Engine (internal).
SPECULATIVE... do not start." But the project's own stated public/private line
is "a metric ships once published (formula + citation) — code and SQL almost
always ship; only tuned artifacts, configs, and non-baseline backtest results
stay internal." Most of `model/` is reimplemented public literature, not tuned
proprietary edge, so a large share of it has been mis-filed as private by
directory rather than by the rule that actually governs it. That mis-filing is
the direct, verifiable reason the public-facing database has looked, to an
outside reader, like "what you'd get from pybaseball" — the differentiated
work is real, it is simply not visible.

Phase B's own first planned step (already written in the ladder) is exactly
this: "Engine triage + a `meta.metric` registry table — classify the ~110
'Engine' composite packages." This proposal pulls that inventory forward now,
reframed as pure documentation — no new modeling, no tuned parameters, no
backtest results — so it does not require Phase B's entry gate ("Phase A's
feature store is stable and versioned") and does not touch a SPECULATIVE area
in the sense `project.md`'s merge protocol means to block (owner-authorized
here explicitly). It is the single highest-leverage way to make two months of
real work visible, and it is the "cited, browsable applied-research layer" the
owner has been asking for — built from what already exists, not from new work.

## What Changes

- **One clarifying sentence in `openspec/project.md`**: a metric whose formula
  comes from published, citable literature is Phase A / public material
  regardless of which directory it currently lives in; only tuned parameters,
  blends/ensembles, ranked feature-selection results, and non-baseline
  backtest results are Phase B / internal. This is a restatement of the
  existing public/private rule, not a new one — it corrects an inconsistent
  application of it.
- **A per-metric YAML catalog** (one small file per metric, schema-validated,
  living beside — not replacing — the code) with mandatory fields: `name`,
  a plain-English `definition`, `formula` (or a pointer to the `.sql`/`.py`
  that computes it), `citation` (source + year), `grain`, `layer`
  (`gold`/`feat`/`model`), `status` (`published` / `validated` /
  `implemented-untested` / `negative-result` / `archived`), and `visibility`
  (`public` / `internal`) per the rule above. `validated` requires a passing
  tie-out test against an independent published value within a documented
  tolerance — this is not a self-certification field.
- **A CI check** that fails when a `model/` module (or a named `gold`
  statistic) has no catalog entry — the drift guard that keeps the catalog
  from going stale the way the ADR-cross-reference approach did.
- **Two generated views of the same source of truth**: (a) a public MkDocs
  page listing every `visibility: public` entry with its plain-English
  definition and citation, sorted with `validated` entries first; (b) a
  `meta.metric` PostgreSQL table (loaded from the YAML by a small script) so
  a SQL user can join metadata against `gold`/`model` output directly.
- **A first-pass inventory of all ~155 `model/` modules**, each triaged in the
  sense already planned by `project.md`'s Phase B step 1 (keep / validate /
  rebuild-on-demand / archive-as-negative-result), but recorded as a catalog
  entry rather than gating on Phase B's start.

**Explicitly not in this change:** no new metric, no modeling change, no
tuned parameter, no backtest, no feature-store/harness change, no touching
`feat.*`. This is an inventory and a documentation pipeline over what already
exists and already runs.

## Capabilities

### New Capabilities

- `metric-catalog`: every implemented statistic/metric in this project has
  exactly one machine-readable, cited, status-honest catalog entry; a public
  subset renders on the docs site; the full set is queryable via
  `meta.metric` in PostgreSQL; CI enforces the catalog cannot silently drift
  out of sync with the code.

### Modified Capabilities

_None._ (The `openspec/project.md` gate-wording clarification is a
constitution edit, not a capability spec delta — see Impact.)

## Impact

- **`openspec/project.md`**: one clarifying sentence in the Phase A/B
  boundary section (see What Changes); Phase B's step-1 line is marked done
  once this ships, since the inventory it asked for now exists.
- **New**: a metrics YAML directory (exact location decided in `design.md`),
  a loader script (`mlb_baseball/sql/...` + a small Python loader — no SQL
  strings in Python, per the existing rule), a migration for `meta.metric`,
  a CI script (`scripts/check_metric_catalog.py` or similar), a MkDocs page
  generator, and a `mlb catalog` CLI verb.
- **Read, not modified**: all 155 files under `mlb_baseball/model/`, plus
  the named statistics already in `gold`/`feat` — this change inventories
  them, it does not change their code or their computed values.
- **Docs**: `docs/DECISIONS.md` gets one ADR recording the gate clarification
  and the catalog decision; `docs/DATA_DICTIONARY.md` cross-links to the new
  public catalog page instead of duplicating citations.
- **No production data change.** `meta.metric` is new and additive; nothing
  currently shipped is altered.
