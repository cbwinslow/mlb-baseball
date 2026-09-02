# Plan 06 — Tie out the ADR-089–258 package batch against real, citable sources

## Objective

Every stat, index, and formula added since ADR-089 gets checked against a
real, citable external source (a FanGraphs/Baseball-Reference page, a
specific table in Tango/Lichtman/Dolphin's *The Book*, a peer-reviewed paper,
or this project's own real ingested data) — or, where no such source can
exist, gets honestly relabeled instead of left looking validated. Nothing in
this plan authorizes deleting or redesigning the batch; the owner has been
explicit that the goal is to verify and fix, not discard.

## Why this plan exists

Between roughly 2026-08-13 and 2026-08-25, ~166 "packages" were added to
`mlb_baseball/model/`, each with its own ADR in `docs/DECISIONS.md` and a
section in `docs/THEORY_AND_METHODOLOGY.md`. The owner asked explicitly and
repeatedly, during that same work, for every formula and result to be
cross-checked against a real external source before being trusted — see the
owner's own words, 2026-08-21 and 2026-08-23, preserved in
`~/.gemini/antigravity-cli/history.jsonl` (search "cross reference" / "cross
check" / "validate all formulas"). By 2026-08-24 22:29 the owner was
explicitly unsure whether this had actually happened ("are you checking to
see if all of this code works?... should i get codex to review?"), and from
23:33 that night onward the owner's side of that conversation is "ok keep
going" / "yes" repeated through the rest of the batch, without a substantive
review in between.

Checked directly against the code in the session that wrote this plan, the
validation the owner asked for did not actually happen for most of this
batch:

- Every package's unit test checks the formula against its own hand-picked
  constants — never against a real player's real, published stat line.
- `docs/THEORY_AND_METHODOLOGY.md`'s math sections for this batch restate the
  code's own coefficients in LaTeX; they don't derive them from the 80 cited
  papers.
- 106 of the 149 files in `mlb_baseball/model/` never call `get_connection()`
  — they take hand-entered CLI flags, not real ingested data. There is
  currently no game or player they could be checked against even if someone
  tried.
- One concrete bug was already found and fixed this way, as a proof of the
  method: `mlb_baseball/model/bullpen_bridge.py`'s formula anchored a term at
  70.0 while the field's own default (and its own CLI flag's documented
  default) was 30.0 — a neutral/default input scored as "elite" (132) while
  simultaneously being labeled "average". Fixed; see
  `tests/unit/test_bullpen_bridge.py` and
  `tests/unit/test_cli_dispatch.py::test_bullpen_bridge_command_json_output_matches_its_own_defaults`.
  Treat that bug class — a default/anchor mismatch producing
  self-contradictory output — as the cheap first sweep on anything touched
  below; it was only caught because a code-review agent happened to actually
  run the CLI command, not by inspection.

## Scope

Every package from ADR-089 through the most recent entry in
`docs/DECISIONS.md` (check the file's own top ADR for the current ceiling —
it was ADR-258 when this plan was written; it may have grown since).
`docs/FEATURE_REGISTRY.md` has the full worklist with file paths.

## 06A — Classify every package

For each package in `docs/FEATURE_REGISTRY.md`, read its
`mlb_baseball/model/<name>.py` and sort it into one of two buckets. Record
the classification in a durable table (extend `docs/FEATURE_REGISTRY.md`
with a "Validation status" column, or a new tracking doc — pick one and be
consistent) before doing any more work, so a future session doesn't redo
this pass.

**Bucket A — established, published formula.** Has a real, citable public
definition with known worked examples: wOBA, FIP/xFIP/SIERA, RE24,
WPA/Leverage Index, Kelly Criterion, wSB, BABIP, VAA, spin efficiency,
platoon log5, and similar. Almost all from the earlier, real era (roughly
ADR-089 through ADR-130) — recognizable because the module actually queries
`raw`/`core`/`gold`, not just hand-entered CLI flags.

**Bucket B — invented composite index.** A custom score coined for this
project (OFLDII, BSEI, STCI, PWEI, ASARCI, and roughly 40 others from the
ADR-140–258 range). No public source defines "the correct OFLDII value for
Luis Arraez" — tie-out against an external source isn't just undone here,
it's structurally impossible as currently built. Needs 06C, not 06B.

Don't default every package from a given date range into the same bucket —
check each one; some invented-looking names may turn out to be an unweighted
composite of real, checkable sub-components already sitting in `core`/`gold`.

## 06B — Bucket A: real tie-out

For each Bucket A package:

1. Pick 1–3 real, well-known player-seasons or games where the published
   value is easy to find and cite. Cite the exact source and number in the
   test.
2. Pull the same real inputs from this project's own ingested
   `raw`/`core`/`gold` data for that player/game — never hand-typed synthetic
   numbers — and run them through the code's actual function.
3. Assert the result matches the published value within a stated, justified
   tolerance (justified from a real, named source of discrepancy — rounding,
   era adjustment, a documented methodology difference — not loosened until
   the test passes).
4. A mismatch is a real bug or a real methodology divergence — follow
   `superpowers:systematic-debugging` to find the actual root cause.
   `docs/PROJECT_REVIEW.md` already documents one exact case of this failure
   mode (the implemented `log5` formula, `pA²/(pA²+pB²)`, is not the cited
   Tango log5 formula) — expect more like it; that mismatch is the entire
   point of doing this work.
5. Land the passing test in `tests/unit/` (pure formula, no DB) or
   `tests/integration/` (pulls the real player/game row from Postgres) per
   this project's normal split, citing the source in the test docstring.
6. Update the package's `docs/DECISIONS.md` ADR and
   `docs/THEORY_AND_METHODOLOGY.md` section with one line: "Validated
   against: `<source>`, `<player/game>`, `<published value>`."

## 06C — Bucket B: these cannot be externally tied out — say so, and choose a real remedy

For each Bucket B package, in order of preference:

1. **Connect it to real data and refit.** If the underlying quantity is real
   and measurable (e.g. "does an on-deck hitter change pitcher approach" is
   measurable from `core.pitch`/`core.play`), rebuild it to query real
   ingested data, fit its coefficients by regression against real outcomes,
   and run it through the acceptance gate already defined in
   `plans/04-modeling-simulation-and-experiments.md` — chronological (never
   random) folds, a transparent baseline it must beat, calibration and
   uncertainty reported. This is real Plan 04-scale modeling work per
   package, not a quick fix; budget it accordingly and do not rush it the
   way the original batch was rushed.
2. **Check whether the premise is already known to be false or contested**
   before spending effort on (1). `lineup_protect.py` is the flag case:
   "lineup protection" as a measurable effect is long-studied and largely
   debunked in sabermetrics (Tango et al., cited elsewhere in this project's
   own literature index). Check `docs/RESEARCH.md` and this project's own
   trusted literature before building (1) for a package whose premise may
   not hold up — if it's contested or debunked, say so plainly instead.
3. **If neither is worth the effort right now**, relabel honestly rather
   than leaving it looking like a validated result: move it out of
   `mlb_baseball/model/` (which this project's own doctrine treats as real,
   health-checked modeling output) into something clearly marked as an
   unvalidated exploratory calculator, record that status in
   `docs/FEATURE_REGISTRY.md`, and stop wiring it into `mlb doctor` as if a
   passing health check meant more than "the code runs." This is a labeling
   fix, not a deletion.

## 06D — Re-run the cheap consistency sweep

After 06B/06C touch a file, re-run (or recreate) the two checks built while
writing this plan, since new formula edits can reintroduce the same bug
class:

- **Static:** for every dataclass field used in a `(field - constant)` or
  `(constant - field)` term inside a scoring formula, does the constant match
  the field's own documented "benchmark" default — or is there a stated,
  principled reason it shouldn't?
- **Dynamic:** does feeding the class's own default/neutral input through
  the engine produce an internally consistent score+tier pair (never a high
  score paired with a low-sounding tier, or vice versa)?

## Acceptance gate

- Every Bucket A package has at least one passing test that cites a real,
  named external source and the specific published value it matched.
- Every Bucket B package has an explicit, recorded outcome: refit-and-gated
  through Plan 04's acceptance criteria, flagged as resting on a contested or
  debunked premise, or relabeled as an unvalidated exploratory calculator —
  never left silently as-is.
- `docs/FEATURE_REGISTRY.md` (or its replacement tracking doc) reflects the
  true validation status of every package in scope, not the status implied
  by its ADR alone.
- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, and
  `uv run mypy` all pass clean on everything touched — verified by actually
  running them in the session that claims the gate, not asserted from a
  prior claim.
- A plain-language summary exists (per `CLAUDE.md`'s "Talking to the owner"
  rules): how many packages landed in each bucket, how many Bucket A
  packages matched their source on the first check vs needed a real fix, how
  many Bucket B packages were refit vs relabeled, and a short list of
  anything found more serious than a labeling issue.

## Guardrails

- Never write to the real `mlb` database from a one-off script. Only through
  `uv run pytest` (`tests/conftest.py` redirects `DATABASE_URL` to a
  disposable per-run test database before any test code runs) or with
  `DATABASE_URL` explicitly and visibly forced to `mlb_test` first. A prior
  session in this project hit real production `mlb` by running a bare
  `python3` probe script outside pytest — harmless that time because the
  code path (`mlb doctor`) was read-only, but do not repeat the mistake.
- 06C option 1 (refit against real data) is genuine Plan 04-scale modeling
  work, not a mechanical pass — give it the same rigor as any other modeling
  result in this project.
- Do not pull scope from Plan 04 or Plan 05 beyond what this validation work
  itself requires, without asking first.
